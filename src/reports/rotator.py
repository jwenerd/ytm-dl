"""Lazy-man cadence evaluator, archive rotator, and index generator for AI listening reports."""

import glob
import logging
import os
from datetime import UTC, date, datetime, timedelta

import yaml

from src.reports.aggregator import assemble_report_context
from src.reports.generator import generate_report
from src.reports.playlist import (
    extract_featured_entity_ids,
    extract_playlist_video_ids,
    inject_playlist_banner,
    sync_daily_radar_playlist,
)
from src.util import get_effective_listening_date, get_user_timezone

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


def get_target_period_info(
    cadence: str,
    now_dt: datetime,
    use_effective_date: bool = False,
) -> tuple[str, date, str]:
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
    anchor_date = (
        get_effective_listening_date(now_dt, tz=tz) if use_effective_date else now_local.date()
    )
    cadence = cadence.lower()

    if cadence == "daily":
        target = anchor_date - timedelta(days=1)
        period_key = target.strftime("%Y-%m-%d")
        archive_path = os.path.join("archive", "daily", str(target.year), f"{period_key}.md")
        return period_key, target, archive_path

    if cadence == "weekly":
        monday_this_week = anchor_date - timedelta(days=anchor_date.weekday())
        target_day_in_prev_week = monday_this_week - timedelta(days=3)
        year, week, _ = target_day_in_prev_week.isocalendar()
        period_key = f"{year}-W{week:02d}"
        archive_path = os.path.join("archive", "weekly", str(year), f"{period_key}.md")
        return period_key, target_day_in_prev_week, archive_path

    if cadence == "monthly":
        first_of_this_month = anchor_date.replace(day=1)
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
    Automatic weekly and monthly checks respect the 4 AM effective listening-day cutoff.
    Returns (should_run, period_key, target_date).
    """
    use_effective = cadence.lower() in ("weekly", "monthly")
    period_key, target_date, _ = get_target_period_info(
        cadence, now_dt, use_effective_date=use_effective
    )
    cadence_meta = meta.get(cadence) or {}
    last_period = cadence_meta.get("last_period")

    if not last_period or str(last_period) < period_key:
        return True, period_key, target_date

    if refresh_nocturnal and cadence.lower() == "daily" and str(last_period) == period_key:
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=UTC)
        now_local = now_dt.astimezone(get_user_timezone())
        if now_local.hour < 4:
            return True, period_key, target_date

    return False, period_key, target_date


def _get_prior_excluded_ids(meta: dict, current_period: str) -> set[str]:
    """
    Returns featured entity IDs from prior periods while never excluding picks from
    `current_period` itself (safe across nocturnal refreshes or forced same-day reruns).
    """
    excluded: set[str] = set()
    by_period = meta.get("recent_radar_by_period")
    if isinstance(by_period, dict):
        for period, ids in by_period.items():
            if str(period) != current_period and isinstance(ids, list):
                excluded.update(str(i) for i in ids if i)
    elif (meta.get("daily") or {}).get("last_period") != current_period:
        excluded.update(str(i) for i in (meta.get("recent_radar_ids") or []) if i)
    return excluded


def _record_period_picks(
    meta: dict,
    period_key: str,
    featured_ids: list[str],
    max_periods: int = 7,
) -> None:
    """Persists featured picks keyed by period (retaining the latest `max_periods` days)."""
    raw_by_period = meta.get("recent_radar_by_period")
    by_period: dict[str, list[str]] = dict(raw_by_period) if isinstance(raw_by_period, dict) else {}
    by_period[period_key] = featured_ids

    trimmed_keys = sorted(by_period.keys(), reverse=True)[:max_periods]
    trimmed = {k: by_period[k] for k in trimmed_keys}
    meta["recent_radar_by_period"] = trimmed

    flat: list[str] = []
    for k in trimmed_keys:
        for item_id in trimmed[k]:
            if item_id not in flat:
                flat.append(item_id)
    meta["recent_radar_ids"] = flat[:50]


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

    live_file = os.path.join(reports_dir, f"{cadence}.md")
    with open(live_file, "w", encoding="utf-8") as f:
        f.write(content)

    if len(period_key) >= 4 and period_key[:4].isdigit():
        archive_rel_path = os.path.join("archive", cadence, period_key[:4], f"{period_key}.md")
    else:
        _, _, archive_rel_path = get_target_period_info(cadence, now_dt)
    archive_file = os.path.join(reports_dir, archive_rel_path)
    os.makedirs(os.path.dirname(archive_file), exist_ok=True)
    with open(archive_file, "w", encoding="utf-8") as f:
        f.write(content)

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
        "# 🎧 Listening Reports & Crate-Digger Radar",
        "",
        "Automated crate-digger listening logs, resurfaced gems, and rolling radar picks generated by `ytm-dl`.",
        "",
        "## 📌 Active Reports",
        "",
        "| Cadence | Current Report | Description |",
        "| :--- | :--- | :--- |",
        "| **Daily** | [daily.md](daily.md) | Yesterday's spin, rolling radar picks, resurfaced like & full LP/set |",
        "| **Weekly** | [weekly.md](weekly.md) | Weekly crate digest, top rotations & weekend radar queue |",
        "| **Monthly** | [monthly.md](monthly.md) | Monthly crate retrospective, new artist discoveries & deep cuts |",
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
    sync_playlist: bool = True,
) -> list[str]:
    """
    Evaluates cadences and generates due reports.
    Periods with zero listening activity (total_tracks == 0) are skipped.
    For daily reports, syncs the rolling 25-track YTM Daily Radar playlist and
    tracks featured songs, albums, and sets per period to avoid day-over-day repetition.
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
            if is_forced:
                period_key, computed_target, _ = get_target_period_info(
                    cad, now_dt, use_effective_date=False
                )
            use_date = target_date if target_date else computed_target
            effective_key = (
                use_date.strftime("%Y-%m-%d") if (cad == "daily" and target_date) else period_key
            )
            recent_ids = _get_prior_excluded_ids(meta, effective_key) if cad == "daily" else None
            ctx = assemble_report_context(output_dir, cad, use_date, excluded_radar_ids=recent_ids)
            if ctx["telemetry"]["total_tracks"] == 0:
                logger.info(
                    "Skipping %s report for period %s: no listening activity",
                    cad,
                    effective_key,
                )
                continue

            logger.info("Generating %s report for period: %s", cad, effective_key)
            content = generate_report(ctx, api_key=api_key)

            if cad == "daily":
                picked_song_ids = extract_playlist_video_ids(content, ctx)
                if sync_playlist:
                    playlist_url = sync_daily_radar_playlist(picked_song_ids, effective_key, meta)
                    if playlist_url:
                        content = inject_playlist_banner(content, playlist_url)
                featured_all_ids = extract_featured_entity_ids(content, picked_song_ids)
                if featured_all_ids:
                    _record_period_picks(meta, effective_key, featured_all_ids)

            rotate_and_write_report(
                output_dir=output_dir,
                cadence=cad,
                period_key=effective_key,
                content=content,
                meta=meta,
                meta_path=meta_path,
                now_dt=now_dt,
            )
            generated_cadences.append(cad)

    if generated_cadences:
        update_reports_readme(output_dir)

    return generated_cadences
