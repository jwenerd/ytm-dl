"""Lazy-man cadence evaluator, archive rotator, and index generator for AI listening reports."""

import glob
import logging
import os
from datetime import UTC, date, datetime, timedelta

import yaml

from src.reports.aggregator import (
    assemble_report_context,
)
from src.reports.generator import generate_report
from src.util import get_user_timezone

logger = logging.getLogger(__name__)


def read_reports_meta(meta_path: str) -> dict:
    """Reads output/meta/reports.yaml or returns default empty dictionary."""
    if not os.path.isfile(meta_path):
        return {}
    try:
        with open(meta_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError) as e:
        logger.warning("Could not read reports meta from %s: %s", meta_path, e)
        return {}


def write_reports_meta(meta_path: str, meta: dict) -> None:
    """Writes metadata to output/meta/reports.yaml."""
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(meta, f, sort_keys=True, indent=2)


def get_target_period_info(cadence: str, now_dt: datetime) -> tuple[str, date, str]:
    """
    Computes the (period_key, target_date, archive_subpath) for a given cadence.
    - daily: target is yesterday in local time. Key: 'YYYY-MM-DD'. Archive: 'archive/daily/YYYY/YYYY-MM-DD.md'
    - weekly: target is previous Monday-Sunday week. Key: 'YYYY-Www'. Archive: 'archive/weekly/YYYY/YYYY-Www.md'
    - monthly: target is previous month. Key: 'YYYY-MM'. Archive: 'archive/monthly/YYYY/YYYY-MM.md'
    """
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=UTC)

    tz = get_user_timezone()
    now_local = now_dt.astimezone(tz)
    cadence = cadence.lower()

    if cadence == "daily":
        target = now_local.date() - timedelta(days=1)
        period_key = target.strftime("%Y-%m-%d")
        archive_path = os.path.join("archive", "daily", str(target.year), f"{period_key}.md")
        return period_key, target, archive_path

    if cadence == "weekly":
        # Target is the last completed week (evaluated on Monday or subsequent days)
        # Shift back 7 days from current week's Monday
        monday_this_week = now_local.date() - timedelta(days=now_local.date().weekday())
        target_day_in_prev_week = monday_this_week - timedelta(days=3)  # Midpoint of prev week
        year, week, _ = target_day_in_prev_week.isocalendar()
        period_key = f"{year}-W{week:02d}"
        archive_path = os.path.join("archive", "weekly", str(year), f"{period_key}.md")
        return period_key, target_day_in_prev_week, archive_path

    if cadence == "monthly":
        # Target is the previous calendar month
        first_of_this_month = now_local.date().replace(day=1)
        target_day_in_prev_month = first_of_this_month - timedelta(days=1)
        period_key = target_day_in_prev_month.strftime("%Y-%m")
        archive_path = os.path.join(
            "archive", "monthly", str(target_day_in_prev_month.year), f"{period_key}.md"
        )
        return period_key, target_day_in_prev_month, archive_path

    msg = f"Unknown cadence: {cadence}"
    raise ValueError(msg)


def should_run_cadence(
    cadence: str,
    meta: dict,
    now_dt: datetime,
    refresh_nocturnal: bool = False,
) -> tuple[bool, str, date]:
    """
    Evaluates whether the specified cadence is due to run.
    Returns (should_run, period_key, target_date).
    If refresh_nocturnal is True and it's early morning (< 4am local), allows refreshing
    the newly generated daily report if new plays were added.
    """
    period_key, target_date, _ = get_target_period_info(cadence, now_dt)
    cadence_meta = meta.get(cadence) or {}
    last_period = cadence_meta.get("last_period")

    # If never run or last recorded period is older than target period
    if not last_period or str(last_period) < period_key:
        return True, period_key, target_date

    # If already ran for this period, but we are in nocturnal hours (< 4am local)
    # and new history was added, allow refreshing the daily report
    if refresh_nocturnal and cadence.lower() == "daily" and str(last_period) == period_key:
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=UTC)
        now_local = now_dt.astimezone(get_user_timezone())
        if now_local.hour < 4:
            return True, period_key, target_date

    return False, period_key, target_date


def rotate_and_write_report(
    output_dir: str,
    cadence: str,
    period_key: str,
    content: str,
    meta: dict,
    meta_path: str,
    now_dt: datetime,
) -> None:
    """
    Writes content to output/reports/{cadence}.md and also saves it to the archive path.
    Updates output/meta/reports.yaml with last_period and last_generated_at.
    """
    reports_dir = os.path.join(output_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    # 1. Live file
    live_file = os.path.join(reports_dir, f"{cadence}.md")
    with open(live_file, "w", encoding="utf-8") as f:
        f.write(content)

    # 2. Archive file
    _, _, archive_rel_path = get_target_period_info(cadence, now_dt)
    archive_file = os.path.join(reports_dir, archive_rel_path)
    os.makedirs(os.path.dirname(archive_file), exist_ok=True)
    with open(archive_file, "w", encoding="utf-8") as f:
        f.write(content)

    # 3. Update meta
    meta[cadence] = {
        "last_period": period_key,
        "last_generated_at": now_dt.isoformat(),
        "live_file": f"reports/{cadence}.md",
        "archive_file": f"reports/{archive_rel_path}",
    }
    write_reports_meta(meta_path, meta)


def update_reports_readme(output_dir: str) -> None:
    """
    Generates output/reports/README.md with links to current reports and an archive catalog.
    """
    reports_dir = os.path.join(output_dir, "reports")
    if not os.path.isdir(reports_dir):
        return

    lines = [
        "# 🎧 Listening Reports & Discovery Radar",
        "",
        "Automated musicological field logs and algorithmic discovery radars generated by `ytm-dl`.",
        "",
        "## 📌 Active Reports",
        "",
        "| Cadence | Current Report | Description |",
        "| :--- | :--- | :--- |",
        "| **Daily** | [daily.md](daily.md) | Yesterday's listening pulse & 3 fresh radar suggestions |",
        "| **Weekly** | [weekly.md](weekly.md) | Weekly macro shifts, top rotations & weekend discovery queue |",
        "| **Monthly** | [monthly.md](monthly.md) | Comprehensive monthly retrospective & curated mixtape |",
        "",
        "## 🏛️ Archive",
        "",
    ]

    for cad in ["daily", "weekly", "monthly"]:
        archive_glob = os.path.join(reports_dir, "archive", cad, "**", "*.md")
        files = sorted(glob.glob(archive_glob, recursive=True), reverse=True)
        if files:
            lines.append(f"### {cad.capitalize()} Archive")
            lines.append("")
            lines.append("| Period | Report Link |")
            lines.append("| :--- | :--- |")
            for f in files:
                rel = os.path.relpath(f, reports_dir)
                period_name = os.path.splitext(os.path.basename(f))[0]
                lines.append(f"| {period_name} | [{period_name}]({rel}) |")
            lines.append("")

    readme_path = os.path.join(reports_dir, "README.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")


def run_reports(
    output_dir: str = "output",
    force_cadence: str | None = None,
    api_key: str | None = None,
    target_date: date | None = None,
    now_dt: datetime | None = None,
    refresh_nocturnal: bool = False,
) -> list[str]:
    """
    Evaluates cadences and generates due reports.
    If force_cadence is provided ('daily', 'weekly', 'monthly', or 'all'), generates them unconditionally.
    Returns list of cadences generated.
    """
    if now_dt is None:
        now_dt = datetime.now(UTC)

    meta_path = os.path.join(output_dir, "meta", "reports.yaml")
    meta = read_reports_meta(meta_path)

    cadences_to_check = (
        ["daily", "weekly", "monthly"]
        if not force_cadence or force_cadence.lower() == "all"
        else [force_cadence.lower()]
    )

    generated_cadences = []

    for cad in cadences_to_check:
        is_forced = bool(force_cadence and force_cadence.lower() in (cad, "all"))
        should_run, period_key, computed_target = should_run_cadence(
            cad, meta, now_dt, refresh_nocturnal=refresh_nocturnal
        )

        if is_forced or should_run:
            use_date = target_date if target_date else computed_target
            logger.info("Generating %s report for period: %s", cad, period_key)

            ctx = assemble_report_context(output_dir, cad, use_date)
            content = generate_report(ctx, api_key=api_key)

            rotate_and_write_report(
                output_dir=output_dir,
                cadence=cad,
                period_key=period_key,
                content=content,
                meta=meta,
                meta_path=meta_path,
                now_dt=now_dt,
            )
            generated_cadences.append(cad)

    if generated_cadences:
        update_reports_readme(output_dir)

    return generated_cadences
