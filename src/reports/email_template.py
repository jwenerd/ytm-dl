"""HTML email template generator for YTM-DL listening reports.

Produces an Editorial Zine / Vinyl OBI Strip dark-themed HTML email compatible
with Gmail (mobile and desktop), Apple Mail, and standard email clients, rotating
color palettes via `src/reports/palettes.py`.
"""

import html
import re
from typing import Any

from src.reports.palettes import (
    EMAIL_THEMES,
    EmailTheme,
    select_email_theme,
)

__all__ = [
    "EMAIL_THEMES",
    "EmailTheme",
    "markdown_to_email_html",
    "select_email_theme",
]

_PLAYLIST_URL_RE = re.compile(r"https://music\.youtube\.com/playlist\?list=[A-Za-z0-9_-]+")
_COMPACT_STATS_RE = re.compile(
    r"(\d+)\s+plays\s*·\s*([^·]+?)\s*·\s*(\d+)\s+artists\s*·\s*(\d+)\s+new\s+artists",
    re.IGNORECASE,
)
_SPIN_LINE_RE = re.compile(r"^\*\*The Spin:?\*\*:?\s*(.+)$", re.IGNORECASE)


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _format_inline(text: str, theme: EmailTheme | None = None) -> str:
    """Formats markdown inline styles (bold, italic, code, links) using theme tokens."""
    t = theme or EMAIL_THEMES[0]
    out = _escape(text)

    out = re.sub(
        r"`([^`]+)`",
        (
            r'<code style="font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; '
            rf'font-size: 12px; background: {t["code_bg"]}; padding: 2px 6px; border-radius: 4px; color: {t["code_fg"]};">\1</code>'
        ),
        out,
    )

    out = re.sub(
        r"\[([^\]]+)\]\((https?://[^\)]+)\)",
        rf'<a href="\2" style="color: {t["link"]}; text-decoration: none; border-bottom: 1px dotted {t["link"]};">\1</a>',
        out,
    )

    out = re.sub(
        r"\*\*([^*]+)\*\*",
        rf'<strong style="font-weight: 600; color: {t["text_primary"]};">\1</strong>',
        out,
    )

    return re.sub(
        r"\*([^*]+)\*",
        rf'<em style="font-style: italic; color: {t["text_italic"]};">\1</em>',
        out,
    )


def _render_obi_ledger(
    telemetry: dict[str, Any],
    theme: EmailTheme,
    playlist_url: str | None = None,
) -> str:
    """
    Renders a single-line Vinyl OBI / Editorial Zine ledger bar bounded by thin hairlines,
    with an inline 'Play Crate' pill button on the right (zero KPI boxes).
    """
    has_stats = bool(telemetry and telemetry.get("total_tracks") is not None)
    if not has_stats and not playlist_url:
        return ""

    ledger_left = ""
    if has_stats:
        tracks = _escape(str(telemetry.get("total_tracks", 0)))
        dur = _escape(str(telemetry.get("total_duration_display", "0m"))).upper()
        artists = _escape(str(telemetry.get("unique_artists_count", 0)))
        new_art = int(telemetry.get("new_artists_count", 0) or 0)
        new_badge = (
            f' <span style="color: {theme["secondary"]};">({new_art} FIRST-TIMERS)</span>'
            if new_art > 0
            else ""
        )
        sep = f'<span style="color: {theme["border"]}; padding: 0 7px;">/</span>'
        ledger_left = (
            f'<span style="color: {theme["text_primary"]}; font-weight: 700;">{tracks}</span> SPINS'
            f"{sep}"
            f'<span style="color: {theme["text_primary"]}; font-weight: 700;">{dur}</span>'
            f"{sep}"
            f'<span style="color: {theme["text_primary"]}; font-weight: 700;">{artists}</span> ARTISTS{new_badge}'
        )

    cta_td = ""
    if playlist_url:
        safe_url = _escape(playlist_url)
        cta_td = f"""
        <td align="right" valign="middle" style="padding-left: 12px; white-space: nowrap;">
          <a href="{safe_url}" style="display: inline-block; background: {theme["cta_bg"]}; color: {theme["cta_text"]}; font-size: 11px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; text-decoration: none; padding: 6px 12px; border-radius: 999px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            &#9654; Play Crate &#8599;
          </a>
        </td>"""

    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top: 1px solid {theme["border"]}; border-bottom: 1px solid {theme["border"]}; background-color: {theme["obi_bg"]};">
      <tr>
        <td valign="middle" style="padding: 11px 24px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 11px; letter-spacing: 0.06em; color: {theme["text_muted"]}; line-height: 1.5;">
          {ledger_left}
        </td>
        {cta_td}
        <td width="16" style="font-size: 1px; line-height: 1px;">&nbsp;</td>
      </tr>
    </table>
    """


def _render_callout_card(
    quote_lines: list[str],
    theme: EmailTheme,
    index: int = 0,
) -> str:
    """Renders a Markdown blockquote (`> `) as a left-bordered editorial crate callout card."""
    joined = " ".join(ln.strip() for ln in quote_lines if ln.strip())
    if not joined:
        return ""
    accents = theme["callout_accents"]
    accent = accents[index % len(accents)]
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin: 14px 0;">
      <tr>
        <td style="background-color: {theme["callout_bg"]}; border: 1px solid {theme["border"]}; border-left: 3px solid {accent}; border-radius: 0 8px 8px 0; padding: 13px 16px; font-size: 13.5px; line-height: 1.6; color: {theme["text_body"]}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
          {_format_inline(joined, theme)}
        </td>
      </tr>
    </table>
    """


def _parse_table(lines: list[str], theme: EmailTheme | None = None) -> str:
    """Parses markdown table lines into styled HTML table."""
    if not lines:
        return ""
    t = theme or EMAIL_THEMES[0]

    rows = []
    for line in lines:
        raw_cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(raw_cells)

    if len(rows) < 2:
        return ""

    headers = rows[0]
    data_rows = rows[2:] if all(re.match(r"^:?-+:?$", c) for c in rows[1]) else rows[1:]

    th_cells = "".join(
        f'<th style="background: {t["obi_bg"]}; color: {t["text_muted"]}; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; padding: 10px 12px; text-align: left; border-bottom: 1px solid {t["border"]};">{_format_inline(h, t)}</th>'
        for h in headers
    )

    tr_elements = []
    for i, row in enumerate(data_rows):
        bg = t["callout_bg"] if i % 2 == 0 else t["card_bg"]
        td_cells = "".join(
            f'<td style="padding: 10px 12px; border-bottom: 1px solid {t["border"]}; font-size: 13px; color: {t["text_body"]}; vertical-align: top;">{_format_inline(c, t)}</td>'
            for c in row
        )
        tr_elements.append(f'<tr style="background: {bg};">{td_cells}</tr>')

    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width: 100%; border-collapse: collapse; margin: 16px 0; border: 1px solid {t["border"]}; border-radius: 8px; overflow: hidden;">
      <thead>
        <tr>{th_cells}</tr>
      </thead>
      <tbody>
        {"".join(tr_elements)}
      </tbody>
    </table>
    """


def _is_telemetry_bullet(item_text: str) -> bool:
    """Checks if a bullet is a raw telemetry line already shown in the OBI ledger bar."""
    plain = item_text.replace("*", "").strip()
    prefixes = (
        "Stats:",
        "Total Tracks",
        "Auditory Duration:",
        "Unique Artists:",
        "Distinct Artists:",
        "New Artists:",
    )
    return plain.startswith(prefixes)


def markdown_to_email_html(
    md_content: str,
    context: dict[str, Any] | None = None,
    theme_index: int | None = None,
) -> str:
    """
    Converts a Markdown listening report into an Editorial Zine / Vinyl OBI HTML email.
    Selects a palette from `src.reports.palettes` using `(day_of_month - 1) % len(EMAIL_THEMES)`.
    """
    lines = md_content.splitlines()

    doc_title = "Daily Listening Log"
    kicker_label = "CRATE LOG"
    subtitle = "Crate-Digger Daily"
    spin_headline = ""
    has_h1 = False
    playlist_url = (context or {}).get("playlist_url") or ""
    period_hint = str((context or {}).get("period_label") or "")

    for ln in lines[:5]:
        if ln.strip().startswith("# "):
            period_hint = f"{period_hint} {ln.strip()}"
            break

    theme = select_email_theme(period_hint=period_hint, theme_index=theme_index)

    table_buffer: list[str] = []
    list_buffer: list[str] = []
    quote_buffer: list[str] = []
    callout_idx = 0
    html_parts: list[str] = []

    def flush_list():
        nonlocal list_buffer
        if list_buffer:
            items = "".join(
                f'<li style="margin-bottom: 11px; line-height: 1.6; color: {theme["text_body"]};">{_format_inline(item, theme)}</li>'
                for item in list_buffer
            )
            html_parts.append(
                f'<ul style="margin: 8px 0 18px 18px; padding: 0; list-style-type: disc;">{items}</ul>'
            )
            list_buffer = []

    def flush_table():
        nonlocal table_buffer
        if table_buffer:
            html_parts.append(_parse_table(table_buffer, theme))
            table_buffer = []

    def flush_quote():
        nonlocal quote_buffer, callout_idx
        if quote_buffer:
            html_parts.append(_render_callout_card(quote_buffer, theme, callout_idx))
            callout_idx += 1
            quote_buffer = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("# ") and not has_h1:
            has_h1 = True
            title_text = stripped[2:].strip()
            clean_title = re.sub(r"[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]+", "", title_text)
            clean_title = re.sub(r"^[\W_]+", "", clean_title).strip()
            doc_title = clean_title or title_text
            if ":" in doc_title:
                left, right = doc_title.split(":", 1)
                kicker_label = f"{left.strip().upper()}  //  {right.strip()}"
            else:
                kicker_label = doc_title.upper()
            continue

        if stripped.startswith("*Recorded via ytm-dl") or (
            stripped.startswith("*") and stripped.endswith("*") and "ytm-dl" in stripped
        ):
            raw_sub = stripped.strip("*").strip()
            subtitle = raw_sub.split("|")[-1].strip() if "|" in raw_sub else raw_sub
            continue

        if "Play Rolling Daily Radar Playlist" in stripped:
            m_url = _PLAYLIST_URL_RE.search(stripped)
            if m_url and not playlist_url:
                playlist_url = m_url.group(0)
            continue

        spin_match = _SPIN_LINE_RE.match(stripped)
        if spin_match and not spin_headline:
            spin_headline = spin_match.group(1).strip().strip("*").strip()
            continue

        if stripped.startswith(("## 1. Session Telemetry", "## 1. Macro Analysis")):
            continue

        if stripped.startswith(">"):
            flush_list()
            flush_table()
            quote_text = stripped[1:].strip()
            if quote_text:
                quote_buffer.append(quote_text)
            else:
                flush_quote()
            continue
        if quote_buffer:
            flush_quote()

        if stripped.startswith("|") and stripped.endswith("|"):
            flush_list()
            table_buffer.append(stripped)
            continue
        if table_buffer:
            flush_table()

        if stripped.startswith(("- ", "* ")):
            item_text = stripped[2:].strip()
            if not _is_telemetry_bullet(item_text):
                list_buffer.append(item_text)
            continue
        if list_buffer:
            flush_list()

        if stripped.startswith("## "):
            h2_text = stripped[3:].strip()
            html_parts.append(
                f'<h2 style="margin: 26px 0 12px 0; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: {theme["secondary"]}; border-bottom: 1px solid {theme["border"]}; padding-bottom: 7px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;">{_format_inline(h2_text, theme)}</h2>'
            )
            continue

        if stripped.startswith("### "):
            h3_text = stripped[4:].strip()
            html_parts.append(
                f"<h3 style=\"margin: 18px 0 8px 0; font-size: 13px; font-weight: 600; color: {theme['link']}; text-transform: uppercase; letter-spacing: 0.04em; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;\">{_format_inline(h3_text, theme)}</h3>"
            )
            continue

        if stripped:
            html_parts.append(
                f"<p style=\"margin: 6px 0 16px 0; font-size: 15px; line-height: 1.65; color: {theme['text_primary']}; font-family: Georgia, 'Iowan Old Style', 'Apple Garamond', Baskerville, serif;\">{_format_inline(stripped, theme)}</p>"
            )

    flush_quote()
    flush_list()
    flush_table()

    telemetry = context.get("telemetry", {}) if context else _extract_telemetry_from_lines(lines)
    obi_ledger_html = _render_obi_ledger(telemetry, theme=theme, playlist_url=playlist_url)
    masthead_headline = spin_headline or doc_title
    body_content = "".join(html_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark">
  <title>{_escape(doc_title)}</title>
</head>
<body data-theme="{theme["id"]}" style="margin: 0; padding: 0; background-color: {theme["outer_bg"]}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: {theme["outer_bg"]}; padding: 24px 10px;">
    <tr>
      <td align="center">
        <!-- Main Zine / Vinyl Sleeve Container -->
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width: 640px; background-color: {theme["card_bg"]}; border: 1px solid {theme["border"]}; border-top: 4px solid {theme["primary"]}; border-radius: 4px; overflow: hidden; box-shadow: 0 12px 32px rgba(0,0,0,0.6);">
          <!-- Editorial Masthead -->
          <tr>
            <td style="padding: 24px 24px 18px 24px; background-color: {theme["card_bg"]};">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 11px; font-weight: 700; letter-spacing: 0.1em; color: {theme["primary"]}; text-transform: uppercase;">
                    {_escape(kicker_label)}
                  </td>
                  <td align="right" style="font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 10px; letter-spacing: 0.08em; color: {theme["text_muted"]}; text-transform: uppercase;">
                    {_escape(subtitle)}
                  </td>
                </tr>
              </table>
              <h1 style="margin: 12px 0 2px 0; font-size: 22px; font-weight: 700; color: {theme["text_primary"]}; line-height: 1.32; letter-spacing: -0.01em; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                {_format_inline(masthead_headline, theme)}
              </h1>
            </td>
          </tr>

          <!-- Vinyl OBI Strip Ledger Bar -->
          <tr>
            <td style="padding: 0;">
              {obi_ledger_html}
            </td>
          </tr>

          <!-- Editorial Body -->
          <tr>
            <td style="padding: 22px 24px 24px 24px;">
              {body_content}
            </td>
          </tr>

          <!-- Colophon Footer -->
          <tr>
            <td style="padding: 14px 24px; background: {theme["footer_bg"]}; border-top: 1px solid {theme["border"]};">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 11px; color: {theme["text_muted"]};">
                    ytm-dl crate log · {_escape(theme["id"].replace("_", "-"))}
                  </td>
                  <td align="right" style="font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 11px;">
                    <a href="https://github.com/jwenerd/ytm-dl" style="color: {theme["link"]}; text-decoration: none;">archives &#8599;</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _extract_telemetry_from_lines(lines: list[str]) -> dict[str, Any]:
    """Fallback extractor for telemetry stats directly from markdown lines."""
    telemetry: dict[str, Any] = {
        "total_tracks": 0,
        "total_duration_display": "0m",
        "unique_artists_count": 0,
        "new_artists_count": 0,
    }

    for line in lines:
        s = line.strip()
        compact = _COMPACT_STATS_RE.search(s)
        if compact:
            telemetry["total_tracks"] = int(compact.group(1))
            telemetry["total_duration_display"] = compact.group(2).strip()
            telemetry["unique_artists_count"] = int(compact.group(3))
            telemetry["new_artists_count"] = int(compact.group(4))
            return telemetry

        if "Total Tracks Observed" in s or "Total Tracks" in s:
            m = re.search(r"(\d+)", s)
            if m:
                telemetry["total_tracks"] = int(m.group(1))
        elif "Auditory Duration" in s or "Duration" in s:
            m = re.search(r":\s*(\d+m|\d+h\s*\d+m|[\d\w\s]+)", s)
            if m:
                telemetry["total_duration_display"] = m.group(1).strip()
        elif "Unique Artists" in s or "Distinct Artists" in s:
            m = re.search(r"(\d+)", s)
            if m:
                telemetry["unique_artists_count"] = int(m.group(1))
        elif "New Artists" in s:
            m = re.search(r"(\d+)", s)
            if m:
                telemetry["new_artists_count"] = int(m.group(1))

    return telemetry
