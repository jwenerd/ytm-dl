"""GitHub-native Markdown charts (24-week heatmap and 2026+ monthly trends) for output/README.md."""

import contextlib
import glob
import math
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta

from src.reports.telemetry import parse_iso_timestamp, read_csv_rows
from src.util import get_user_timezone

_MONTH_FILE_RE = re.compile(r"^(\d{4})-(\d{2})\.csv$")
_WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def load_monthly_history_stats(output_dir: str, min_year: int = 2026) -> list[dict]:
    """
    Aggregates plays, hours, and active days per month from `output/history/YYYY-MM.csv`
    for all months with year >= `min_year`, sorted chronologically.
    """
    history_dir = os.path.join(output_dir, "history")
    matched: list[tuple[int, int, str]] = []

    for filepath in glob.glob(os.path.join(history_dir, "*.csv")):
        m = _MONTH_FILE_RE.match(os.path.basename(filepath))
        if not m:
            continue
        year, month = int(m.group(1)), int(m.group(2))
        if year < min_year:
            continue
        matched.append((year, month, filepath))

    matched.sort(key=lambda item: (item[0], item[1]))

    stats: list[dict] = []
    for year, month, filepath in matched:
        rows = read_csv_rows(filepath)
        total_seconds = 0
        active_dates: set[date] = set()
        for row in rows:
            with contextlib.suppress(ValueError):
                total_seconds += int(row.get("duration_seconds") or 0)
            ts = parse_iso_timestamp(row.get("played_at"))
            if ts:
                active_dates.add(ts.date())

        stats.append(
            {
                "month": f"{year:04d}-{month:02d}",
                "label": date(year, month, 1).strftime("%b %y"),
                "plays": len(rows),
                "hours": round(total_seconds / 3600, 1),
                "active_days": len(active_dates),
            }
        )
    return stats


def _resolve_heatmap_bounds(weeks: int, end_date: date | None) -> tuple[date, date]:
    """Returns (start_monday, end_date) covering `weeks` Monday-aligned columns."""
    today = end_date or datetime.now(get_user_timezone()).date()
    current_week_monday = today - timedelta(days=today.weekday())
    start_date = current_week_monday - timedelta(weeks=weeks - 1)
    return start_date, today


def load_daily_play_counts(
    output_dir: str,
    weeks: int = 24,
    end_date: date | None = None,
) -> dict[date, int]:
    """
    Reads only the monthly `history/YYYY-MM.csv` partitions overlapping the last `weeks`
    weeks and returns a `{date: play_count}` dictionary.
    """
    start_date, today = _resolve_heatmap_bounds(weeks, end_date)
    counts: Counter[date] = Counter()

    cursor = start_date.replace(day=1)
    end_month = today.replace(day=1)
    while cursor <= end_month:
        rel_name = f"{cursor.year:04d}-{cursor.month:02d}.csv"
        filepath = os.path.join(output_dir, "history", rel_name)
        for row in read_csv_rows(filepath):
            ts = parse_iso_timestamp(row.get("played_at"))
            if ts:
                play_day = ts.date()
                if start_date <= play_day <= today:
                    counts[play_day] += 1

        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)

    return dict(counts)


def _heatmap_cell(count: int | None) -> str:
    """Maps daily play count to a compact intensity emoji cell."""
    if count is None:
        return "▫️"
    if count == 0:
        return "⬛"
    if count < 10:
        return "🟩"
    if count < 30:
        return "🟨"
    if count < 60:
        return "🟧"
    return "🟥"


def _compute_streaks(
    daily_counts: dict[date, int],
    start_date: date,
    end_date: date,
) -> tuple[int, int]:
    """Computes (current_streak_days, best_streak_days) within [start_date, end_date]."""
    best_streak = 0
    running = 0
    day = start_date
    while day <= end_date:
        if daily_counts.get(day, 0) > 0:
            running += 1
            best_streak = max(best_streak, running)
        else:
            running = 0
        day += timedelta(days=1)

    current_streak = 0
    cursor = end_date
    if daily_counts.get(cursor, 0) == 0:
        cursor = end_date - timedelta(days=1)
    while cursor >= start_date and daily_counts.get(cursor, 0) > 0:
        current_streak += 1
        cursor -= timedelta(days=1)

    return current_streak, best_streak


def render_activity_heatmap(
    daily_counts: dict[date, int],
    weeks: int = 24,
    end_date: date | None = None,
) -> str:
    """Renders a 7-row (Mon-Sun) x N-week GitHub Markdown listening activity heatmap."""
    start_date, today = _resolve_heatmap_bounds(weeks, end_date)
    total_days = (today - start_date).days + 1
    total_plays = sum(v for d, v in daily_counts.items() if start_date <= d <= today)
    active_days = sum(1 for d, v in daily_counts.items() if start_date <= d <= today and v > 0)
    current_streak, best_streak = _compute_streaks(daily_counts, start_date, today)

    lines = [
        f"### 🔥 Listening Activity (Last {weeks} Weeks)",
        "",
        (
            f"**{total_plays:,} plays** · **{active_days}/{total_days} active days** · "
            f"Current streak: **{current_streak}d** · Best streak: **{best_streak}d**"
        ),
        "",
        f"| Day | {start_date} → {today} |",
        "| :--- | :--- |",
    ]

    for wd, label in enumerate(_WEEKDAY_LABELS):
        cells = []
        for w in range(weeks):
            cell_date = start_date + timedelta(days=w * 7 + wd)
            if cell_date > today:
                cells.append(_heatmap_cell(None))
            else:
                cells.append(_heatmap_cell(daily_counts.get(cell_date, 0)))
        lines.append(f"| {label} | {''.join(cells)} |")

    lines.append("")
    lines.append("*Legend: ⬛ 0 · 🟩 1–9 · 🟨 10–29 · 🟧 30–59 · 🟥 60+ · ▫️ upcoming*")
    return "\n".join(lines)


def render_monthly_trend_charts(monthly_stats: list[dict]) -> str:
    """
    Renders GitHub-native Mermaid `xychart-beta` diagrams for 2026+ Monthly Hours & Plays,
    plus a collapsible details table with exact counts.
    """
    if not monthly_stats:
        return ""

    max_hours = max(1, math.ceil(max(s["hours"] for s in monthly_stats) * 1.15))
    max_plays = max(10, math.ceil(max(s["plays"] for s in monthly_stats) * 1.15))

    labels_str = ", ".join(f'"{s["label"]}"' for s in monthly_stats)
    hours_str = ", ".join(str(s["hours"]) for s in monthly_stats)
    plays_str = ", ".join(str(s["plays"]) for s in monthly_stats)

    lines = [
        "### 📈 Monthly Trend (2026+)",
        "",
        "```mermaid",
        "xychart-beta",
        '    title "Monthly Listening Hours (2026+)"',
        f"    x-axis [{labels_str}]",
        f'    y-axis "Hours" 0 --> {max_hours}',
        f"    bar [{hours_str}]",
        f"    line [{hours_str}]",
        "```",
        "",
        "```mermaid",
        "xychart-beta",
        '    title "Monthly Plays (2026+)"',
        f"    x-axis [{labels_str}]",
        f'    y-axis "Plays" 0 --> {max_plays}',
        f"    bar [{plays_str}]",
        "```",
        "",
        "<details>",
        "<summary>Monthly Breakdown</summary>",
        "",
        "| Month | Plays | Hours | Active Days |",
        "| :--- | ---: | ---: | ---: |",
    ]
    for s in monthly_stats:
        lines.append(f"| {s['month']} | {s['plays']:,} | {s['hours']}h | {s['active_days']} |")
    lines.append("")
    lines.append("</details>")
    return "\n".join(lines)


def build_readme_charts_markdown(
    output_dir: str,
    weeks: int = 24,
    min_year: int = 2026,
    end_date: date | None = None,
) -> str:
    """Builds the combined Markdown charts section for `output/README.md`."""
    daily_counts = load_daily_play_counts(output_dir, weeks=weeks, end_date=end_date)
    monthly_stats = load_monthly_history_stats(output_dir, min_year=min_year)

    if not daily_counts and not monthly_stats:
        return ""

    sections: list[str] = []
    if daily_counts:
        sections.append(render_activity_heatmap(daily_counts, weeks=weeks, end_date=end_date))
    if monthly_stats:
        sections.append(render_monthly_trend_charts(monthly_stats))

    return "\n\n".join(sections)
