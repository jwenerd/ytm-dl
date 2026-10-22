"""Unit tests for HTML email template generation and report rotation."""

from src.reports.email_template import markdown_to_email_html


def test_markdown_to_email_html_with_context():
    sample_md = """# 🎧 Daily Listening Log: 2026-10-20
*Recorded via ytm-dl | Cadence: Daily Observation*

## 1. Session Telemetry
- Total Tracks Observed: 42
- Auditory Duration: 2h 15m
- Unique Artists: 12 (8 albums)
- Library Ratio: 75%

## 2. Musicological Notes
### Field Observations
- **Primary Anchor**: Centered around Dorothy Ashby.
- **Repeat Loop**: *Soul Vibrations* (3x).

### Narrative Synthesis
Playback centered predominantly on harp jazz and instrumental soul.

## 3. Dynamic Field Spotlight
- **Sonic Timbre**: Warm acoustic production featuring Dorothy Ashby's jazz harp.

## 4. Algorithmic Suggestions Radar
| Track | Artist | Shelf Source | Impressions | Position | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Wax and Wane | Dorothy Ashby | `your_daily_discover` | 2x | #1 | ✨ New Arrival |
| Afro-Harping | Dorothy Ashby | `discover_mix` | 1x | #3 | 🔁 Recurring |
"""

    context = {
        "cadence": "daily",
        "period_label": "2026-10-20",
        "telemetry": {
            "total_tracks": 42,
            "total_duration_display": "2h 15m",
            "unique_artists_count": 12,
            "unique_albums_count": 8,
            "library_ratio_pct": 75,
            "catalog_anchor": "Dorothy Ashby",
        },
        "radar_candidates": [],
    }

    html = markdown_to_email_html(sample_md, context=context)

    # Verify key structure
    assert "<!DOCTYPE html>" in html
    assert "Daily Listening Log: 2026-10-20" in html
    assert "YTM-DL LISTENING LOG" in html

    # Verify stat cards
    assert "TRACKS" in html
    assert "42" in html
    assert "DURATION" in html
    assert "2h 15m" in html
    assert "ARTISTS" in html
    assert "12" in html
    assert "LIBRARY" in html
    assert "75%" in html

    # Verify table parsing
    assert "<table" in html
    assert "Wax and Wane" in html
    assert "Afro-Harping" in html
    assert "your_daily_discover" in html

    # Verify inline formatting
    assert '<strong style="font-weight: 600; color: #f0f6fc;">Primary Anchor</strong>' in html
    assert '<em style="font-style: italic; color: #d29922;">Soul Vibrations</em>' in html


def test_markdown_to_email_html_fallback_stats_extraction():
    sample_md = """# 🎧 Daily Listening Log: 2026-10-19
*Recorded via ytm-dl | Cadence: Daily Observation*

## 1. Session Telemetry
- Total Tracks Observed: 15
- Auditory Duration: 48m
- Unique Artists: 5 (3 albums)
- Library Ratio: 60%

## 2. Musicological Notes
Some notes here.
"""
    # No context provided: extracts from markdown directly
    html = markdown_to_email_html(sample_md, context=None)

    assert "15" in html
    assert "48m" in html
    assert "5" in html
    assert "60%" in html
