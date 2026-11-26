"""Unit tests for src/reports/prompt.py and src/reports/generator.py"""

from unittest.mock import MagicMock, patch

import requests

from src.reports.generator import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_THINKING_LEVEL,
    GEMINI_API_URL,
    clean_markdown_fences,
    generate_report,
    get_google_ai_api_key,
)
from src.reports.prompt import (
    build_report_prompt,
    generate_fallback_report,
)


def sample_context(cadence="daily"):
    return {
        "cadence": cadence,
        "period_label": "2026-10-18",
        "telemetry": {
            "total_tracks": 15,
            "total_seconds": 3600,
            "total_duration_display": "1h",
            "unique_artists_count": 3,
            "unique_albums_count": 2,
            "new_artists_count": 1,
            "new_artists": ["Hiroshi Yoshimura"],
            "top_artists": [{"artist": "Grateful Dead", "count": 10}],
            "top_tracks": [
                {
                    "title": "Shakedown Street",
                    "artist": "Grateful Dead",
                    "count": 2,
                    "videoId": "vid-shake",
                    "url": "https://music.youtube.com/watch?v=vid-shake",
                }
            ],
            "repeat_tracks": [
                {
                    "title": "Shakedown Street",
                    "artist": "Grateful Dead",
                    "count": 2,
                    "videoId": "vid-shake",
                    "url": "https://music.youtube.com/watch?v=vid-shake",
                }
            ],
            "version_collisions": [],
            "catalog_anchor": "Grateful Dead (67% of session, 10 plays)",
            "live_track_count": 0,
            "liked_plays_count": 2,
            "new_likes": [
                {
                    "title": "Honky Cat",
                    "artist": "Elton John",
                    "album": "Honky Chateau",
                    "videoId": "vid-honky",
                    "url": "https://music.youtube.com/watch?v=vid-honky",
                }
            ],
        },
        "radar_candidates": [
            {
                "id": "vid-1",
                "title": "GREEN",
                "artists": "Hiroshi Yoshimura",
                "url": "https://music.youtube.com/watch?v=vid-1",
                "shelf": "your_daily_discover",
                "first_seen": "2026-10-18T08:00:00Z",
                "times_recommended": 1,
                "latest_position": 1,
                "is_new": True,
                "is_known_artist": False,
            }
        ],
        "forgotten_candidates": [
            {
                "id": "vid-fg",
                "title": "Body And Soul",
                "artists": "Ryo Fukui",
                "url": "https://music.youtube.com/watch?v=vid-fg",
                "source": "liked_songs",
                "note": "Liked 2026-01-10, unplayed since",
            }
        ],
        "long_form_picks": {
            "albums": [
                {
                    "id": "MPREb_1",
                    "title": "Sixteen Oceans",
                    "artists": "Four Tet",
                    "url": "https://music.youtube.com/browse/MPREb_1",
                }
            ],
            "long_sets": [
                {
                    "id": "vid-set",
                    "title": "In Dub Live [FULL ALBUM]",
                    "artists": "Hallucinogen",
                    "url": "https://music.youtube.com/watch?v=vid-set",
                }
            ],
        },
    }


def test_clean_markdown_fences():
    assert clean_markdown_fences("```markdown\n# Header\nContent\n```") == "# Header\nContent\n"
    assert clean_markdown_fences("```\n# Header\nContent\n```") == "# Header\nContent\n"
    assert clean_markdown_fences("# Header\nContent") == "# Header\nContent\n"


def test_get_google_ai_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_AI_API_KEY", "test-key-123")
    assert get_google_ai_api_key() == "test-key-123"

    monkeypatch.delenv("GOOGLE_AI_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('export GOOGLE_AI_API_KEY="file-secret-key-456"\n')
    assert get_google_ai_api_key(str(env_file)) == "file-secret-key-456"

    env_file.write_text("GOOGLE_AI_API_KEY=raw-key-789\n")
    assert get_google_ai_api_key(str(env_file)) == "raw-key-789"

    env_file.write_text("OTHER_KEY=123\n")
    assert get_google_ai_api_key(str(env_file)) is None


def test_build_report_prompt_crate_digger():
    for cadence in ["daily", "weekly", "monthly"]:
        ctx = sample_context(cadence)
        ctx["milestones"] = [
            {
                "category": "artist_plays",
                "entity": "Grateful Dead",
                "threshold": 500,
                "date": "2026-10-18",
            }
        ]
        ctx["obsessions"] = {
            "window_14d_plays": 42,
            "tracks_on_repeat": [{"title": "Shakedown Street", "plays_7d": 5}],
            "artist_signals": [],
            "album_binges": [],
            "taste_phases": [],
        }
        prompt = build_report_prompt(ctx)
        assert "record-store clerk" in prompt
        assert "Library Ratio" not in prompt
        assert "new artists" in prompt
        assert "Liked & Forgotten" in prompt
        assert "Full Album" in prompt
        assert "Long Spin" in prompt
        assert "Milestones & Obsessions" in prompt
        assert '"obsessions"' in prompt
        assert cadence.upper() in prompt


def test_generate_fallback_report_all_branches():
    for cadence in ["daily", "weekly", "monthly"]:
        ctx = sample_context(cadence)
        ctx["milestones"] = [
            {
                "category": "artist_plays",
                "entity": "Grateful Dead",
                "threshold": 500,
                "date": "2026-10-18",
            }
        ]
        fallback = generate_fallback_report(ctx)
        assert "Library Ratio" not in fallback
        assert "1 new artists" in fallback
        assert "[GREEN](https://music.youtube.com/watch?v=vid-1)" in fallback
        assert "**Liked & Forgotten:**" in fallback
        assert "**Full Album:**" in fallback
        assert "**Long Spin:**" in fallback
        assert "Milestone Unlocked" in fallback

    # Collision branch + live branch + zero-activity branch
    ctx_col = sample_context("daily")
    ctx_col["telemetry"]["version_collisions"] = [
        {"title": "Sunrise", "artists": ["Chet Atkins", "George Lewis"]}
    ]
    fb_col = generate_fallback_report(ctx_col)
    assert "Sunrise" in fb_col

    ctx_live = sample_context("daily")
    ctx_live["telemetry"]["repeat_tracks"] = []
    ctx_live["telemetry"]["live_track_count"] = 3
    fb_live = generate_fallback_report(ctx_live)
    assert "3 live concert" in fb_live

    ctx_empty = {
        "cadence": "daily",
        "period_label": "2026-10-18",
        "telemetry": {
            "total_tracks": 0,
            "total_duration_display": "0m",
            "unique_artists_count": 0,
            "new_artists_count": 0,
            "top_artists": [],
            "repeat_tracks": [],
            "version_collisions": [],
            "live_track_count": 0,
            "new_likes": [],
        },
        "radar_candidates": [],
        "forgotten_candidates": [],
        "long_form_picks": {"albums": [], "long_sets": []},
    }
    fb_empty = generate_fallback_report(ctx_empty)
    assert "Quiet turntable" in fb_empty
    assert "No fresh radar tracks" in fb_empty


def test_generate_report_fallback_and_api(monkeypatch):
    monkeypatch.setattr("src.reports.generator.get_google_ai_api_key", lambda: None)
    ctx = sample_context("daily")
    report = generate_report(ctx, api_key=None)
    assert "# Daily Listening Log" in report

    with patch("src.reports.generator.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {"thought": True, "text": "Internal reasoning should be skipped."},
                            {
                                "text": "```markdown\n# Daily Listening Log: 2026-10-18\nCrate spin\n```"
                            },
                        ]
                    },
                }
            ]
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        ok_report = generate_report(ctx, api_key="valid-key")
        assert "Crate spin" in ok_report
        assert "Internal reasoning" not in ok_report
        assert "gemini-4-hydrogen" in GEMINI_API_URL
        assert mock_post.call_args.args[0] == GEMINI_API_URL
        sent_payload = mock_post.call_args.kwargs["json"]
        assert sent_payload["generationConfig"]["maxOutputTokens"] == DEFAULT_MAX_OUTPUT_TOKENS
        assert DEFAULT_MAX_OUTPUT_TOKENS == 16384
        assert DEFAULT_THINKING_LEVEL == "medium"
        assert sent_payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "medium"}

    # MAX_TOKENS truncation falls back cleanly to deterministic report
    with patch("src.reports.generator.requests.post") as mock_trunc:
        trunc_resp = MagicMock()
        trunc_resp.json.return_value = {
            "candidates": [
                {
                    "finishReason": "MAX_TOKENS",
                    "content": {"parts": [{"text": "# Daily Listening Log: Truncated..."}]},
                }
            ]
        }
        trunc_resp.raise_for_status.return_value = None
        mock_trunc.return_value = trunc_resp

        fallback_on_trunc = generate_report(ctx, api_key="valid-key")
        assert "Truncated..." not in fallback_on_trunc
        assert "## On the Turntable" in fallback_on_trunc

    with patch("src.reports.generator.requests.post") as mock_err:
        mock_err.side_effect = requests.RequestException("Network error")
        err_report = generate_report(ctx, api_key="valid-key")
        assert "# Daily Listening Log" in err_report
