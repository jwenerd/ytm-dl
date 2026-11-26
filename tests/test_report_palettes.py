"""Unit tests for src/reports/palettes.py."""

from src.reports.email_template import markdown_to_email_html
from src.reports.palettes import (
    EMAIL_THEMES,
    select_email_theme,
)


def test_email_themes_catalog_integrity():
    assert len(EMAIL_THEMES) == 10
    ids = {t["id"] for t in EMAIL_THEMES}
    assert len(ids) == 10
    outer_bgs = {t["outer_bg"] for t in EMAIL_THEMES}
    assert len(outer_bgs) == 10

    for theme in EMAIL_THEMES:
        assert len(theme["callout_accents"]) >= 3
        assert theme["primary"].startswith("#")
        assert theme["card_bg"].startswith("#")


def test_select_email_theme_modulo_across_month():
    total = len(EMAIL_THEMES)
    for day in range(1, 32):
        selected = select_email_theme(f"2026-11-{day:02d}")
        assert selected["id"] == EMAIL_THEMES[(day - 1) % total]["id"]

    # Explicit index override wraps cleanly
    assert select_email_theme("2026-11-24", theme_index=7)["id"] == "pacific_cumbia_teal"
    assert select_email_theme("2026-11-24", theme_index=17)["id"] == "pacific_cumbia_teal"

    # Weekly ISO label modulo (W47 -> (47 - 1) % 10 == 6 -> bordeaux_velvet)
    assert select_email_theme("2026-W47")["id"] == EMAIL_THEMES[46 % total]["id"]

    # Monthly YYYY-MM label modulo (2026-10 -> (10 - 1) % 10 == 9 -> tokyo_kissaten_olive)
    assert select_email_theme("2026-10")["id"] == EMAIL_THEMES[9 % total]["id"]

    # Monthly full month-name label (October 2026 -> 9 -> tokyo_kissaten_olive, November 2026 -> 0 -> crimson_wax)
    assert (
        select_email_theme("Monthly Crate Retrospective: October 2026")["id"]
        == EMAIL_THEMES[9 % total]["id"]
    )
    assert select_email_theme("November 2026")["id"] == EMAIL_THEMES[10 % total]["id"]

    # Default fallback
    assert select_email_theme("Unparsed Label")["id"] == EMAIL_THEMES[0]["id"]


def test_all_ten_palettes_render_cleanly_in_email_html():
    for day in range(1, 11):
        expected = EMAIL_THEMES[day - 1]
        md = (
            f"# Daily Listening Log: 2026-11-{day:02d}\n"
            f"- **Stats**: 12 plays · 45m · 6 artists · 2 new artists\n\n"
            f"**The Spin:** Day {day} spin.\n\n"
            f"> **Note:** Callout card.\n\n"
            f"## Today's Radar\n"
            f"- **[Track](https://music.youtube.com/watch?v=v1)** — Artist\n"
        )
        html = markdown_to_email_html(md)
        assert f'data-theme="{expected["id"]}"' in html
        assert expected["outer_bg"] in html
        assert expected["card_bg"] in html
        assert expected["obi_bg"] in html
        assert expected["primary"] in html
        assert expected["secondary"] in html
        assert expected["link"] in html
