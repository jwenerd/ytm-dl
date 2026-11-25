"""Report context assembler facade combining telemetry metrics and shelf candidates."""

import os
from datetime import UTC, date, datetime, timedelta

from src.reports.candidates import (
    CANDIDATE_SHELVES,
    LONG_LISTEN_SHELVES,
    extract_forgotten_favorites,
    extract_long_form_picks,
    extract_radar_candidates,
)
from src.reports.telemetry import (
    aggregate_listening_telemetry,
    clean_and_split_artists,
    clean_artist_display,
    filter_history_for_cadence,
    filter_rows_by_timestamp,
    format_duration,
    format_period_label,
    get_cadence_dates,
    get_cadence_window,
    parse_iso_timestamp,
    read_csv_rows,
    ytm_entity_url,
    ytm_watch_url,
)
from src.util import get_user_timezone

__all__ = [
    "CANDIDATE_SHELVES",
    "LONG_LISTEN_SHELVES",
    "aggregate_listening_telemetry",
    "assemble_report_context",
    "clean_and_split_artists",
    "clean_artist_display",
    "extract_forgotten_favorites",
    "extract_long_form_picks",
    "extract_radar_candidates",
    "filter_history_for_cadence",
    "filter_rows_by_timestamp",
    "format_duration",
    "format_period_label",
    "get_cadence_dates",
    "get_cadence_window",
    "parse_iso_timestamp",
    "read_csv_rows",
    "ytm_entity_url",
    "ytm_watch_url",
]


def assemble_report_context(
    output_dir: str,
    cadence: str,
    target_date: date | datetime | None = None,
    excluded_radar_ids: set[str] | None = None,
) -> dict:
    """
    Assembles the full context dictionary needed by the prompt builder and report generator.
    """
    tz = get_user_timezone()
    if target_date is None:
        target = (datetime.now(tz) - timedelta(days=1)).date()
    elif isinstance(target_date, datetime):
        if target_date.tzinfo is None:
            target_date = target_date.replace(tzinfo=UTC)
        target = target_date.astimezone(tz).date()
    else:
        target = target_date

    start_date, _ = get_cadence_dates(cadence, target)
    start_dt, end_dt = get_cadence_window(cadence, target)

    # 1. Read history and separate prior artist catalog from active slice
    history_path = os.path.join(output_dir, "history.csv")
    all_history = read_csv_rows(history_path)
    history_slice = filter_history_for_cadence(all_history, cadence, target)

    prior_artists: set[str] = set()
    all_history_artists: set[str] = set()
    for row in all_history:
        names = [a.lower() for a in clean_and_split_artists(row.get("artists"))]
        all_history_artists.update(names)
        ts = parse_iso_timestamp(row.get("played_at"))
        if ts and ts.date() < start_date:
            prior_artists.update(names)

    # 2. Read liked songs
    liked_path = os.path.join(output_dir, "liked_songs.csv")
    all_likes = read_csv_rows(liked_path)
    liked_slice = filter_rows_by_timestamp(all_likes, "liked_at", start_dt, end_dt)

    # 3. Compute telemetry
    telemetry = aggregate_listening_telemetry(
        history_slice, liked_slice, prior_artists=prior_artists
    )

    # 4. Extract candidates (Radar, Liked & Forgotten, Full Album + Long Set)
    played_video_ids = {
        (row.get("videoId") or "").strip() for row in history_slice if row.get("videoId")
    }

    radar_candidates = extract_radar_candidates(
        output_dir=output_dir,
        start_dt=start_dt,
        end_dt=end_dt,
        history_artists=all_history_artists,
        played_video_ids=played_video_ids,
        excluded_ids=excluded_radar_ids,
        max_candidates=8,
    )

    radar_ids = {c["id"] for c in radar_candidates}
    forgotten_candidates = extract_forgotten_favorites(
        output_dir=output_dir,
        all_history=all_history,
        all_likes=all_likes,
        target_date=target,
        excluded_ids=(excluded_radar_ids or set()) | radar_ids | played_video_ids,
        max_candidates=3,
    )

    long_form_picks = extract_long_form_picks(
        output_dir=output_dir,
        played_video_ids=played_video_ids,
        excluded_ids=excluded_radar_ids,
        max_albums=3,
        max_sets=3,
    )

    return {
        "cadence": cadence.lower(),
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "period_label": format_period_label(cadence, start_dt, end_dt, target),
        "telemetry": telemetry,
        "radar_candidates": radar_candidates,
        "forgotten_candidates": forgotten_candidates,
        "long_form_picks": long_form_picks,
    }
