"""Unit tests for src/reports/prompt.py and src/reports/generator.py"""

from unittest.mock import MagicMock, patch

import requests

from src.reports.generator import (
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
            "top_artists": [{"artist": "Grateful Dead", "count": 10}],
            "top_tracks": [{"title": "Shakedown Street", "artist": "Grateful Dead", "count": 2}],
            "repeat_tracks": [{"title": "Shakedown Street", "artist": "Grateful Dead", "count": 2}],
            "library_ratio_pct": 75.0,
            "catalog_anchor": "Grateful Dead (67% of session, 10 plays)",
            "live_track_count": 0,
            "new_likes": [{"title": "Honky Cat", "artist": "Elton John", "album": "Honky Chateau"}],
        },
        "radar_candidates": [
            {
                "id": "vid-1",
                "title": "GREEN",
                "artists": "Hiroshi Yoshimura",
                "shelf": "your_daily_discover",
                "first_seen": "2026-10-18T08:00:00Z",
                "times_recommended": 1,
                "latest_position": 1,
                "is_new": True,
                "is_known_artist": False,
            }
        ],
    }


def test_clean_markdown_fences():
    raw1 = "```markdown\n# Header\nContent\n```"
    assert clean_markdown_fences(raw1) == "# Header\nContent\n"

    raw2 = "```\n# Header\nContent\n```"
    assert clean_markdown_fences(raw2) == "# Header\nContent\n"

    raw3 = "# Header\nContent"
    assert clean_markdown_fences(raw3) == "# Header\nContent\n"


def test_get_google_ai_api_key_from_env_var(monkeypatch):
    monkeypatch.setenv("GOOGLE_AI_API_KEY", "test-key-123")
    assert get_google_ai_api_key() == "test-key-123"


def test_get_google_ai_api_key_from_file(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_AI_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('export GOOGLE_AI_API_KEY="file-secret-key-456"\n')

    assert get_google_ai_api_key(str(env_file)) == "file-secret-key-456"

    # Without export and without quotes
    env_file.write_text("GOOGLE_AI_API_KEY=raw-key-789\n")
    assert get_google_ai_api_key(str(env_file)) == "raw-key-789"

    # Missing
    env_file.write_text("OTHER_KEY=123\n")
    assert get_google_ai_api_key(str(env_file)) is None


def test_build_report_prompt():
    for cadence in ["daily", "weekly", "monthly"]:
        ctx = sample_context(cadence)
        prompt = build_report_prompt(ctx)
        assert "Grateful Dead" in prompt
        assert "GREEN" in prompt
        assert cadence.upper() in prompt


def test_generate_fallback_report():
    for cadence in ["daily", "weekly", "monthly"]:
        ctx = sample_context(cadence)
        fallback = generate_fallback_report(ctx)
        assert "Grateful Dead" in fallback
        assert "GREEN" in fallback
        assert "## 1." in fallback


def test_generate_report_fallback_when_no_api_key(monkeypatch):
    monkeypatch.setattr("src.reports.generator.get_google_ai_api_key", lambda: None)
    ctx = sample_context("daily")
    report = generate_report(ctx, api_key=None)
    assert "# Daily Listening Log" in report
    assert "GREEN" in report


@patch("src.reports.generator.requests.post")
def test_generate_report_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "```markdown\n# Daily Listening Log: 2026-10-18\nAI content\n```"}
                    ]
                }
            }
        ]
    }
    mock_resp.raise_for_status.return_value = None
    mock_post.return_value = mock_resp

    ctx = sample_context("daily")
    report = generate_report(ctx, api_key="valid-key")
    assert "# Daily Listening Log: 2026-10-18" in report
    assert "AI content" in report
    mock_post.assert_called_once()


@patch("src.reports.generator.requests.post")
def test_generate_report_handles_request_exception(mock_post):
    mock_post.side_effect = requests.RequestException("Network error")
    ctx = sample_context("daily")
    report = generate_report(ctx, api_key="valid-key")
    # Should fall back cleanly without raising
    assert "# Daily Listening Log" in report
    assert "Grateful Dead" in report
