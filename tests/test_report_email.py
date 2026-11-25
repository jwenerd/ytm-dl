"""Unit tests for Editorial Zine / Vinyl OBI HTML email template."""

from src.reports.email_template import (
    EMAIL_THEMES,
    _parse_table,
    _render_callout_card,
    _render_obi_ledger,
    markdown_to_email_html,
)


def test_markdown_to_email_html_obi_strip_and_modulo_palette():
    # 2026-11-24 -> (24 - 1) % 10 == 3 ('dub_studio_forest')
    sample_md = """# 🎧 Daily Listening Log: 2026-11-24
*Recorded via ytm-dl | Crate-Digger Daily*

**[▶ Play Rolling Daily Radar Playlist](https://music.youtube.com/playlist?list=PLd8VL-RVFUnw)**

- **Stats**: 44 plays · 4h 17m · 25 artists · 8 new artists

**The Spin:** Heavy analog synth-funk grooves swerved hard into 70s outlaw country.

Warm 4-hour run anchored by Octave Cat before taking a sharp detour into classic honky-tonk.

## On the Turntable
- **Heavy Rotation:** Octave Cat (14) · The Disco Biscuits (4)

> **⚡ Double-Take:** Caught two takes on *The World Is Waiting for the Sunrise*.
>
> **🔗 Lineage:** Octave Cat bridges Lotus and Dopapod.

> **🌱 First-Timer:** Seun Kuti entered the crates today.

### Bonus Subhead
| Track | Artist | Shelf |
| :--- | :--- | :--- |
| `quick_picks` | **[Sweet Echo](https://music.youtube.com/watch?v=v1)** | Ezra Collective |
"""

    html = markdown_to_email_html(sample_md, context=None)

    assert 'data-theme="dub_studio_forest"' in html
    assert "#060e0b" in html
    assert "#0b1713" in html
    assert "<title>Daily Listening Log: 2026-11-24</title>" in html
    assert "DAILY LISTENING LOG  //  2026-11-24" in html
    assert "LIBRARY" not in html

    h1_block = html.split("<h1")[1].split("</h1>")[0]
    assert "Heavy analog synth-funk grooves swerved hard into 70s outlaw country." in h1_block

    assert "44</span> SPINS" in html
    assert "4H 17M</span>" in html
    assert "25</span> ARTISTS" in html
    assert "(8 FIRST-TIMERS)" in html
    assert "https://music.youtube.com/playlist?list=PLd8VL-RVFUnw" in html
    assert "Play Crate" in html
    assert "44 plays · 4h 17m" not in html
    assert "Warm 4-hour run anchored by Octave Cat" in html
    assert "Bonus Subhead" in html
    assert "<table" in html


def test_markdown_to_email_html_fallbacks_and_new_palettes():
    legacy_md = """# Weekly Crate Digest
*ytm-dl weekly*

## 1. Session Telemetry
- Total Tracks Observed: 15
- Auditory Duration: 48m
- Unique Artists: 5
- New Artists: 2

## Notes
Plain paragraph.
> Trailing quote at EOF
"""
    html_legacy = markdown_to_email_html(legacy_md, context=None)
    assert "WEEKLY CRATE DIGEST" in html_legacy
    assert "15</span> SPINS" in html_legacy
    assert "48M</span>" in html_legacy
    assert "(2 FIRST-TIMERS)" in html_legacy
    assert "Trailing quote at EOF" in html_legacy

    # 2026-11-18 -> (18 - 1) % 10 == 7 ('pacific_cumbia_teal') + colon outside **The Spin**:
    ctx = {
        "period_label": "2026-11-18",
        "playlist_url": "https://music.youtube.com/playlist?list=PL_CTX",
        "telemetry": {
            "total_tracks": 10,
            "total_duration_display": "35m",
            "unique_artists_count": 4,
            "new_artists_count": 0,
        },
    }
    html_ctx = markdown_to_email_html(
        "# Monthly Crate\n**The Spin**: Outside colon headline.\n", context=ctx
    )
    assert 'data-theme="pacific_cumbia_teal"' in html_ctx
    assert "Outside colon headline." in html_ctx
    assert "PL_CTX" in html_ctx
    assert "FIRST-TIMERS" not in html_ctx

    assert _render_obi_ledger({}, EMAIL_THEMES[0], playlist_url=None) == ""
    assert _render_callout_card(["   "], EMAIL_THEMES[0]) == ""
    assert _parse_table([]) == ""
    assert _parse_table(["| Only One Row |"]) == ""
