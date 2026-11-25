"""Unit tests for src/reports/telemetry.py."""

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from src.reports.telemetry import (
    aggregate_listening_telemetry,
    clean_and_split_artists,
    clean_artist_display,
    filter_rows_by_timestamp,
    format_duration,
    format_period_label,
    get_cadence_window,
    parse_iso_timestamp,
    read_csv_rows,
    ytm_entity_url,
    ytm_watch_url,
)


def test_url_and_artist_helpers():
    assert ytm_watch_url(None) == ""
    assert ytm_watch_url("") == ""
    assert ytm_watch_url("abc123XYZ") == "https://music.youtube.com/watch?v=abc123XYZ"

    assert ytm_entity_url("") == ""
    assert ytm_entity_url("MPREb_album1") == "https://music.youtube.com/browse/MPREb_album1"
    assert ytm_entity_url("PLlist1") == "https://music.youtube.com/playlist?list=PLlist1"
    assert ytm_entity_url("VLPLlist2") == "https://music.youtube.com/playlist?list=PLlist2"
    assert ytm_entity_url("vid999") == "https://music.youtube.com/watch?v=vid999"

    assert clean_and_split_artists(None) == []
    assert clean_and_split_artists("1.2M views, Le Mellotron, Bonobo, bonobo") == [
        "Le Mellotron",
        "Bonobo",
    ]
    assert clean_artist_display("850K views, Acid Pauli") == "Acid Pauli"
    assert clean_artist_display("1.2M views") == "1.2M views"


def test_parse_iso_timestamp_and_csv_errors(tmp_path):
    dt = parse_iso_timestamp("2026-10-18T20:44:59Z")
    assert dt == datetime(2026, 10, 18, 20, 44, 59, tzinfo=UTC)
    assert parse_iso_timestamp("2026-10-18T20:44:59") == dt
    assert parse_iso_timestamp("2026-10-18T20:44:59+00:00") == dt
    assert parse_iso_timestamp("") is None
    assert parse_iso_timestamp(None) is None
    assert parse_iso_timestamp("invalid-date") is None

    assert read_csv_rows(str(tmp_path / "missing.csv")) == []

    # Handles OSError cleanly
    bad_file = tmp_path / "bad.csv"
    bad_file.write_text("col\nval\n")
    with patch("builtins.open", side_effect=OSError("Permission denied")):
        assert read_csv_rows(str(bad_file)) == []


def test_format_duration_and_period_labels(monkeypatch):
    monkeypatch.setenv("YTM_TIMEZONE", "UTC")
    assert format_duration(0) == "0m"
    assert format_duration(-10) == "0m"
    assert format_duration(65) == "1m"
    assert format_duration(3600) == "1h"
    assert format_duration(3665) == "1h 01m"

    s = datetime(2026, 10, 18, 4, 0, tzinfo=UTC)
    e = datetime(2026, 10, 19, 3, 59, tzinfo=UTC)
    assert format_period_label("daily", s, e, None) == "2026-10-18"
    assert "2026-W" in format_period_label("weekly", s, e)
    assert format_period_label("monthly", s, e) == "October 2026"
    assert format_period_label("custom", s, e) == "2026-10-18"


def test_get_cadence_window_variants(monkeypatch):
    monkeypatch.setenv("YTM_TIMEZONE", "America/Denver")
    target = date(2026, 10, 18)
    start, end = get_cadence_window("daily", target)
    assert start == datetime(2026, 10, 18, 10, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 19, 9, 59, 59, 999999, tzinfo=UTC)

    monkeypatch.setenv("YTM_TIMEZONE", "UTC")
    s_none, _ = get_cadence_window("daily", None)
    assert s_none.tzinfo == UTC
    s_dt, _ = get_cadence_window("daily", datetime(2026, 10, 18, 12, 0))
    assert s_dt == datetime(2026, 10, 18, 4, 0, 0, tzinfo=UTC)

    start_w, end_w = get_cadence_window("weekly", target)
    assert start_w == datetime(2026, 10, 12, 4, 0, 0, tzinfo=UTC)
    assert end_w == datetime(2026, 10, 19, 3, 59, 59, 999999, tzinfo=UTC)

    start_m, end_m = get_cadence_window("monthly", target)
    assert start_m == datetime(2026, 10, 1, 4, 0, 0, tzinfo=UTC)
    assert end_m == datetime(2026, 11, 1, 3, 59, 59, 999999, tzinfo=UTC)

    start_dec, end_dec = get_cadence_window("monthly", date(2026, 12, 5))
    assert start_dec == datetime(2026, 12, 1, 4, 0, 0, tzinfo=UTC)
    assert end_dec == datetime(2027, 1, 1, 3, 59, 59, 999999, tzinfo=UTC)

    with pytest.raises(ValueError, match="Unsupported cadence"):
        get_cadence_window("yearly", target)


def test_filter_rows_by_timestamp():
    rows = [
        {"id": "1", "ts": "2026-10-18T10:00:00Z"},
        {"id": "2", "ts": "2026-10-18T15:00:00Z"},
        {"id": "3", "ts": "2026-10-19T02:00:00Z"},
    ]
    start = datetime(2026, 10, 18, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 10, 18, 23, 59, 59, tzinfo=UTC)
    filtered = filter_rows_by_timestamp(rows, "ts", start, end)
    assert [r["id"] for r in filtered] == ["1", "2"]


def test_aggregate_listening_telemetry():
    empty_res = aggregate_listening_telemetry([])
    assert empty_res["total_tracks"] == 0
    assert empty_res["new_artists_count"] == 0
    assert "library_ratio_pct" not in empty_res

    history_slice = [
        {
            "title": "Shakedown Street",
            "artists": "Grateful Dead",
            "album": "Merriweather 85 Live",
            "duration_seconds": "900",
            "likeStatus": "LIKE",
            "played_at": "2026-10-18T22:00:00Z",
            "videoId": "vid-1",
        },
        {
            "title": "Shakedown Street",
            "artists": "Grateful Dead",
            "album": "Merriweather 85 Live",
            "duration_seconds": "bad-int",
            "likeStatus": "INDIFFERENT",
            "played_at": "2026-10-18T22:30:00Z",
            "videoId": "vid-1",
        },
        {
            "title": "The World Is Waiting for the Sunrise",
            "artists": "Chet Atkins, Les Paul",
            "album": "Chester & Lester",
            "duration_seconds": "180",
            "likeStatus": "LIKE",
            "played_at": "2026-10-18T14:00:00Z",
            "videoId": "vid-2",
        },
        {
            "title": "The World Is Waiting for the Sunrise",
            "artists": "1.2M views, George Lewis",
            "album": "New Orleans Stompers",
            "duration_seconds": "200",
            "likeStatus": "INDIFFERENT",
            "played_at": "2026-10-18T15:00:00Z",
            "videoId": "vid-3",
        },
    ]

    likes_slice = [
        {
            "title": "Honky Cat",
            "artists": "Elton John",
            "album": "Honky Chateau",
            "videoId": "vid-like-1",
            "liked_at": "2026-10-18T20:44:59Z",
        }
    ]

    res = aggregate_listening_telemetry(
        history_slice,
        likes_slice,
        prior_artists={"grateful dead", "chet atkins"},
    )
    assert res["total_tracks"] == 4
    assert res["total_seconds"] == 1280
    assert "library_ratio_pct" not in res
    assert res["unique_artists_count"] == 4
    assert res["new_artists_count"] == 2
    assert set(res["new_artists"]) == {"Les Paul", "George Lewis"}
    assert res["live_track_count"] == 2
    assert res["liked_plays_count"] == 2
    assert res["repeat_tracks"][0]["url"] == "https://music.youtube.com/watch?v=vid-1"
    assert len(res["version_collisions"]) == 1
    assert res["version_collisions"][0]["title"] == "The World Is Waiting for the Sunrise"
    assert res["new_likes"][0]["url"] == "https://music.youtube.com/watch?v=vid-like-1"
