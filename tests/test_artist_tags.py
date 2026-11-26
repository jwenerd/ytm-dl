"""Unit tests for src/reports/artist_tags.py."""

import json
import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import requests

from src.reports.artist_tags import (
    collect_catalog_artists,
    enrich_artist_tags,
    fetch_artist_tags_batch,
    read_artist_tags,
    run_enrich_cli,
    write_artist_tags,
)


def _write_history(output_dir: str, entries: list[tuple[str, int]]) -> None:
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "history.csv"), "w", encoding="utf-8") as f:
        f.write("title,artists,album,duration_seconds,videoId,played_at\n")
        vid = 1
        for artist, count in entries:
            for _ in range(count):
                f.write(f'Track {vid},"{artist}",Album,200,v{vid},2026-11-24T00:00:00Z\n')
                vid += 1


def test_read_write_artist_tags_and_corrupt_yaml(tmp_path):
    meta_path = os.path.join(str(tmp_path), "meta", "artist_tags.yaml")
    default = read_artist_tags(meta_path)
    assert default["artists"] == {}
    assert default["meta"]["schema_version"] == 1

    store = {
        "artists": {
            "phish": {
                "name": "Phish",
                "primary_genre": "Jam Band",
                "subgenres": ["Progressive Rock"],
                "era": "1980s",
                "country": "US",
                "moods": ["improvisational"],
                "is_uploader": False,
                "source": "manual",
                "tagged_at": "2026-11-26",
            }
        }
    }
    now = datetime(2026, 11, 26, 8, 0, tzinfo=UTC)
    write_artist_tags(meta_path, store, now_dt=now)
    loaded = read_artist_tags(meta_path)
    assert loaded["meta"]["total_tagged"] == 1
    assert loaded["meta"]["updated_at"] == "2026-11-26T08:00:00+00:00"
    assert loaded["artists"]["phish"]["primary_genre"] == "Jam Band"

    # Non-dict YAML and malformed YAML both fall back safely
    with open(meta_path, "w") as f:
        f.write("- just a list\n")
    assert read_artist_tags(meta_path)["artists"] == {}

    with open(meta_path, "w") as f:
        f.write(":::invalid: [")
    assert read_artist_tags(meta_path)["artists"] == {}


def test_collect_catalog_artists_threshold_and_cleaning(tmp_path):
    output_dir = str(tmp_path)
    _write_history(
        output_dir,
        [
            ("Phish", 6),
            ("1.2M views, Le Mellotron, Bonobo", 5),
            ("One Off Stray", 2),
        ],
    )

    qualifying = collect_catalog_artists(output_dir, min_plays=5)
    assert qualifying == [
        ("phish", "Phish", 6),
        ("bonobo", "Bonobo", 5),
        ("le mellotron", "Le Mellotron", 5),
    ]


@patch("src.reports.artist_tags.time.sleep")
@patch("src.reports.artist_tags.requests.post")
def test_fetch_artist_tags_batch_success_retry_and_errors(mock_post, mock_sleep):
    assert fetch_artist_tags_batch([], "key") == []
    assert fetch_artist_tags_batch(["Phish"], "") == []

    # 429 retry then success with genre normalization & list trimming
    resp_429 = MagicMock(status_code=429)
    resp_ok = MagicMock(status_code=200)
    resp_ok.raise_for_status.return_value = None
    resp_ok.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                [
                                    {
                                        "name": "Phish",
                                        "primary_genre": "jam band",
                                        "subgenres": ["Prog", "Funk", "Rock", "Extra"],
                                        "era": "1980s",
                                        "country": "US",
                                        "moods": ["Playful", "Jammy"],
                                        "is_uploader": False,
                                    },
                                    {
                                        "name": "UnknownWeird",
                                        "primary_genre": "Made Up Genre",
                                        "subgenres": [],
                                        "era": "",
                                        "country": "",
                                        "moods": [],
                                        "is_uploader": False,
                                    },
                                ]
                            )
                        }
                    ]
                }
            }
        ]
    }
    mock_post.side_effect = [resp_429, resp_ok]

    tags = fetch_artist_tags_batch(["Phish", "UnknownWeird"], api_key="k", max_retries=1)
    assert len(tags) == 2
    assert tags[0]["primary_genre"] == "Jam Band"
    assert len(tags[0]["subgenres"]) == 3
    assert tags[0]["moods"] == ["playful", "jammy"]
    assert tags[1]["primary_genre"] == "Other"
    assert tags[1]["era"] == "Unknown"
    mock_sleep.assert_called_once()

    # Missing parts -> []
    resp_empty = MagicMock(status_code=200)
    resp_empty.raise_for_status.return_value = None
    resp_empty.json.return_value = {"candidates": [{"content": {"parts": []}}]}
    mock_post.side_effect = [resp_empty]
    assert fetch_artist_tags_batch(["Phish"], api_key="k", max_retries=0) == []

    # Non-list JSON -> []
    resp_dict = MagicMock(status_code=200)
    resp_dict.raise_for_status.return_value = None
    resp_dict.json.return_value = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
    mock_post.side_effect = [resp_dict]
    assert fetch_artist_tags_batch(["Phish"], api_key="k", max_retries=0) == []

    # JSONDecodeError retries once then succeeds
    resp_bad_json = MagicMock(status_code=200)
    resp_bad_json.raise_for_status.return_value = None
    resp_bad_json.json.return_value = {"candidates": [{"content": {"parts": [{"text": "[{bad"}]}}]}
    mock_post.side_effect = [resp_bad_json, resp_ok]
    assert len(fetch_artist_tags_batch(["Phish", "UnknownWeird"], api_key="k", max_retries=1)) == 2

    # RequestException with retry exhausted -> []
    mock_post.side_effect = [
        requests.RequestException("timeout"),
        requests.RequestException("timeout2"),
    ]
    assert fetch_artist_tags_batch(["Phish"], api_key="k", max_retries=1) == []


@patch("src.reports.artist_tags.time.sleep")
@patch("src.reports.artist_tags.fetch_artist_tags_batch")
def test_enrich_artist_tags_batching_checkpointing_and_cli(
    mock_fetch, mock_sleep, tmp_path, monkeypatch
):
    output_dir = str(tmp_path)
    _write_history(output_dir, [("Phish", 10), ("Bonobo", 8), ("loscil", 6), ("Stray", 2)])

    # Seed manual override for Phish -> must never be overwritten or re-queried
    meta_path = os.path.join(output_dir, "meta", "artist_tags.yaml")
    write_artist_tags(
        meta_path,
        {
            "artists": {
                "phish": {
                    "name": "Phish",
                    "primary_genre": "Jam Band",
                    "subgenres": ["Vermont Prog"],
                    "era": "1980s",
                    "country": "US",
                    "moods": ["improvisational"],
                    "is_uploader": False,
                    "source": "manual",
                    "tagged_at": "2026-11-20",
                }
            }
        },
    )

    # Missing API key returns cleanly without calling Gemini
    monkeypatch.setattr("src.reports.artist_tags.get_google_ai_api_key", lambda: None)
    no_key_res = enrich_artist_tags(output_dir=output_dir, min_plays=5, api_key=None)
    assert no_key_res == {"tagged": 0, "remaining": 2, "total_cached": 1}
    mock_fetch.assert_not_called()

    # Run with batch_size=1 so 2 uncached artists run across 2 checkpointed batches + sleep
    mock_fetch.side_effect = [
        [
            {
                "name": "Bonobo",
                "primary_genre": "Electronic & Downtempo",
                "subgenres": ["Trip-Hop"],
                "era": "2000s",
                "country": "GB",
                "moods": ["warm"],
                "is_uploader": False,
            }
        ],
        [
            {
                "name": "loscil",
                "primary_genre": "Ambient",
                "subgenres": ["Drone"],
                "era": "2000s",
                "country": "CA",
                "moods": ["meditative"],
                "is_uploader": False,
            }
        ],
    ]
    res = enrich_artist_tags(
        output_dir=output_dir,
        min_plays=5,
        max_artists=None,
        batch_size=1,
        api_key="test-key",
        delay_seconds=0.1,
        now_dt=datetime(2026, 11, 26, 12, 0, tzinfo=UTC),
    )
    assert res == {"tagged": 2, "remaining": 0, "total_cached": 3}
    mock_sleep.assert_called_once_with(0.1)

    saved = read_artist_tags(meta_path)
    assert saved["artists"]["phish"]["source"] == "manual"
    assert saved["artists"]["bonobo"]["primary_genre"] == "Electronic & Downtempo"
    assert saved["artists"]["loscil"]["country"] == "CA"

    # CLI entrypoint invokes enrich_artist_tags cleanly when already cached
    monkeypatch.setattr("src.reports.artist_tags.get_google_ai_api_key", lambda: "test-key")
    cli_res = run_enrich_cli(["--output-dir", output_dir, "--min-plays", "5", "--all"])
    assert cli_res == {"tagged": 0, "remaining": 0, "total_cached": 3}
