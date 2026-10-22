"""HTML email template generator for YTM-DL daily listening reports.

Produces inline-styled, responsive, dark-themed HTML emails compatible
with Gmail (mobile and desktop), Apple Mail, and standard email clients.
"""

import html
import re
from typing import Any


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _format_inline(text: str) -> str:
    """Formats markdown inline styles (bold, italic, code, links) to inline-styled HTML."""
    # Escape HTML first
    out = _escape(text)

    # Inline code: `code`
    out = re.sub(
        r"`([^`]+)`",
        r'<code style="font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; background: rgba(110,118,129,0.2); padding: 2px 6px; border-radius: 4px; color: #79c0ff;">\1</code>',
        out,
    )

    # Bold: **text**
    out = re.sub(
        r"\*\*([^*]+)\*\*",
        r'<strong style="font-weight: 600; color: #f0f6fc;">\1</strong>',
        out,
    )

    # Italic: *text* or _text_
    out = re.sub(
        r"\*([^*]+)\*",
        r'<em style="font-style: italic; color: #d29922;">\1</em>',
        out,
    )

    # Links: [text](url)
    return re.sub(
        r"\[([^\]]+)\]\((https?://[^\)]+)\)",
        r'<a href="\2" style="color: #58a6ff; text-decoration: none; border-bottom: 1px dotted #58a6ff;">\1</a>',
        out,
    )


def _render_stats_grid(telemetry: dict[str, Any]) -> str:
    """Renders a responsive 4-cell metric card grid."""
    if not telemetry:
        return ""

    cards = [
        ("TRACKS", str(telemetry.get("total_tracks", 0)), "#58a6ff"),
        ("DURATION", str(telemetry.get("total_duration_display", "0m")), "#3fb950"),
        ("ARTISTS", str(telemetry.get("unique_artists_count", 0)), "#bc8cff"),
        ("LIBRARY", f"{telemetry.get('library_ratio_pct', 0)}%", "#d29922"),
    ]

    card_tds = []
    for label, val, color in cards:
        card_tds.append(
            f"""<td style="width: 25%; padding: 4px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background: #161b22; border: 1px solid #30363d; border-radius: 8px; text-align: center; padding: 12px 6px;">
                <tr>
                  <td style="font-size: 10px; font-weight: 700; letter-spacing: 0.08em; color: #8b949e; text-transform: uppercase; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                    {label}
                  </td>
                </tr>
                <tr>
                  <td style="font-size: 20px; font-weight: 700; color: {color}; padding-top: 4px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                    {_escape(val)}
                  </td>
                </tr>
              </table>
            </td>"""
        )

    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 24px; border-collapse: separate;">
      <tr>
        {"".join(card_tds)}
      </tr>
    </table>
    """


def _parse_table(lines: list[str]) -> str:
    """Parses markdown table lines into styled HTML table."""
    if not lines:
        return ""

    rows = []
    for line in lines:
        raw_cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(raw_cells)

    if len(rows) < 2:
        return ""

    headers = rows[0]
    # Check if row 1 is separator (e.g. :---)
    data_rows = rows[2:] if all(re.match(r"^:?-+:?$", c) for c in rows[1]) else rows[1:]

    th_cells = "".join(
        f'<th style="background: #21262d; color: #8b949e; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; padding: 10px 12px; text-align: left; border-bottom: 1px solid #30363d;">{_format_inline(h)}</th>'
        for h in headers
    )

    tr_elements = []
    for i, row in enumerate(data_rows):
        bg = "#161b22" if i % 2 == 0 else "#0d1117"
        td_cells = "".join(
            f'<td style="padding: 10px 12px; border-bottom: 1px solid #21262d; font-size: 13px; color: #c9d1d9; vertical-align: top;">{_format_inline(c)}</td>'
            for c in row
        )
        tr_elements.append(f'<tr style="background: {bg};">{td_cells}</tr>')

    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width: 100%; border-collapse: collapse; margin: 16px 0; border: 1px solid #30363d; border-radius: 8px; overflow: hidden;">
      <thead>
        <tr>{th_cells}</tr>
      </thead>
      <tbody>
        {"".join(tr_elements)}
      </tbody>
    </table>
    """


def markdown_to_email_html(md_content: str, context: dict[str, Any] | None = None) -> str:
    """
    Converts a Markdown listening report into a fully inline-styled HTML email.
    If context is provided, enriches header with stats grid and metadata.
    """
    lines = md_content.splitlines()

    title = "Daily Listening Log"
    subtitle = "Recorded via ytm-dl | Cadence: Daily Observation"
    date_str = ""

    # Detect title and subtitle from lines
    table_buffer: list[str] = []
    list_buffer: list[str] = []
    html_parts: list[str] = []

    def flush_list():
        nonlocal list_buffer
        if list_buffer:
            items = "".join(
                f'<li style="margin-bottom: 6px; line-height: 1.5; color: #c9d1d9;">{_format_inline(item)}</li>'
                for item in list_buffer
            )
            html_parts.append(
                f'<ul style="margin: 8px 0 16px 20px; padding: 0; list-style-type: disc;">{items}</ul>'
            )
            list_buffer = []

    def flush_table():
        nonlocal table_buffer
        if table_buffer:
            html_parts.append(_parse_table(table_buffer))
            table_buffer = []

    for line in lines:
        stripped = line.strip()

        # Capture title
        if stripped.startswith("# ") and not date_str:
            title_text = stripped[2:].strip()
            title = title_text
            # Try to grab date
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", title_text)
            if date_match:
                date_str = date_match.group(0)
            continue

        # Capture subtitle
        if stripped.startswith("*Recorded via ytm-dl") or (
            stripped.startswith("*") and stripped.endswith("*") and "ytm-dl" in stripped
        ):
            subtitle = stripped.strip("*").strip()
            continue

        # Skip section 1 if we're rendering stats grid from context
        # (Session Telemetry section is replaced by rich stats grid)
        if stripped.startswith("## 1. Session Telemetry") or stripped.startswith(
            "## 1. Macro Analysis"
        ):
            continue

        # If line is in table
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_list()
            table_buffer.append(stripped)
            continue
        if table_buffer:
            flush_table()

        # List items
        if stripped.startswith("- ") or stripped.startswith("* "):
            item_text = stripped[2:].strip()
            # If item contains catalog anchor or telemetry bullets in Session Telemetry, skip if already handled
            list_buffer.append(item_text)
            continue
        if list_buffer:
            flush_list()

        # Headings
        if stripped.startswith("## "):
            h2_text = stripped[3:].strip()
            html_parts.append(
                f"<h2 style=\"margin: 28px 0 12px 0; font-size: 17px; font-weight: 600; color: #f0f6fc; border-bottom: 1px solid #30363d; padding-bottom: 8px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;\">{_format_inline(h2_text)}</h2>"
            )
            continue

        if stripped.startswith("### "):
            h3_text = stripped[4:].strip()
            html_parts.append(
                f"<h3 style=\"margin: 20px 0 8px 0; font-size: 14px; font-weight: 600; color: #79c0ff; text-transform: uppercase; letter-spacing: 0.04em; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;\">{_format_inline(h3_text)}</h3>"
            )
            continue

        # Regular paragraphs
        if stripped:
            html_parts.append(
                f"<p style=\"margin: 8px 0 14px 0; font-size: 14px; line-height: 1.6; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;\">{_format_inline(stripped)}</p>"
            )

    flush_list()
    flush_table()

    # Build stats grid
    telemetry = context.get("telemetry", {}) if context else _extract_telemetry_from_lines(lines)
    stats_html = _render_stats_grid(telemetry)

    body_content = "".join(html_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_escape(title)}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #090d16; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: #090d16; padding: 24px 12px;">
    <tr>
      <td align="center">
        <!-- Main Card Container -->
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width: 620px; background-color: #0d1117; border: 1px solid #30363d; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 24px rgba(0,0,0,0.5);">
          <!-- Header Banner -->
          <tr>
            <td style="padding: 24px 24px 16px 24px; background: linear-gradient(180deg, #161b22 0%, #0d1117 100%); border-bottom: 1px solid #21262d;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <span style="display: inline-block; background: rgba(244, 63, 94, 0.15); color: #f43f5e; border: 1px solid rgba(244, 63, 94, 0.3); font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; padding: 4px 10px; border-radius: 12px; margin-bottom: 10px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                      YTM-DL LISTENING LOG
                    </span>
                    <h1 style="margin: 4px 0 6px 0; font-size: 22px; font-weight: 700; color: #f0f6fc; line-height: 1.3; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                      {_escape(title)}
                    </h1>
                    <div style="font-size: 12px; color: #8b949e; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                      {_escape(subtitle)}
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Content Area -->
          <tr>
            <td style="padding: 24px;">
              {stats_html}
              {body_content}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding: 16px 24px; background: #090d16; border-top: 1px solid #21262d; text-align: center;">
              <p style="margin: 0; font-size: 11px; color: #8b949e; line-height: 1.4; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                Automated musicological field report dispatched via <strong>ytm-dl</strong>.
                <br>
                <a href="https://github.com/jwenerd/ytm-dl" style="color: #58a6ff; text-decoration: none;">View repository &amp; archives</a>
              </p>
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
        "library_ratio_pct": 0,
    }

    for line in lines:
        s = line.strip()
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
        elif "Library Ratio" in s:
            m = re.search(r"(\d+)%", s)
            if m:
                telemetry["library_ratio_pct"] = int(m.group(1))

    return telemetry
