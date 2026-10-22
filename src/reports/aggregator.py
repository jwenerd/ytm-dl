"""Data aggregation and candidate recommendation extraction for AI listening reports."""

import csv
import os
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta

from src.util import get_user_timezone

CANDIDATE_SHELVES = [
    ("home/your_daily_discover.csv", "your_daily_discover"),
    ("mixes/discover_mix.csv", "discover_mix"),
    ("home/new_releases.csv", "new_releases"),
    ("home/quick_picks.csv", "quick_picks"),
    ("home/mixed_for_you.csv", "mixed_for_you"),
]


def parse_iso_timestamp(ts_str: str | None) -> datetime | None:
    """Parses ISO timestamp string into a timezone-aware UTC datetime."""
    if not ts_str:
        return None
    try:
        cleaned = ts_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (ValueError, TypeError):
        return None


def format_duration(seconds: int) -> str:
    """Formats duration in seconds to human readable 'Xh Ym' or 'Ym'."""
    if seconds <= 0:
        return "0m"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m" if minutes > 0 else f"{hours}h"
    return f"{minutes}m"


def read_csv_rows(filepath: str) -> list[dict[str, str]]:
    """Reads a CSV file into a list of row dictionaries."""
    if not os.path.isfile(filepath):
        return []
    try:
        with open(filepath, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except (OSError, csv.Error):
        return []


def get_cadence_window(
    cadence: str, target_date: date | datetime | None = None
) -> tuple[datetime, datetime]:
    """
    Returns (start_dt, end_dt) in UTC for the requested cadence.
    - daily: 04:00 local on target_date to 04:00 local on next day (converted to UTC).
    - weekly: Monday 04:00 local of target week to following Monday 04:00 local (in UTC).
    - monthly: 1st of month 04:00 local to 1st of next month 04:00 local (in UTC).
    """
    tz = get_user_timezone()
    now_local = datetime.now(tz)

    if target_date is None:
        target = now_local.date() - timedelta(days=1)
    elif isinstance(target_date, datetime):
        if target_date.tzinfo is None:
            target_date = target_date.replace(tzinfo=UTC)
        target = target_date.astimezone(tz).date()
    else:
        target = target_date

    cadence = cadence.lower()
    if cadence == "daily":
        start_local = datetime.combine(target, time(4, 0), tzinfo=tz)
        end_local = start_local + timedelta(days=1) - timedelta(microseconds=1)
        return start_local.astimezone(UTC), end_local.astimezone(UTC)

    if cadence == "weekly":
        start_of_week = target - timedelta(days=target.weekday())
        start_local = datetime.combine(start_of_week, time(4, 0), tzinfo=tz)
        end_local = start_local + timedelta(days=7) - timedelta(microseconds=1)
        return start_local.astimezone(UTC), end_local.astimezone(UTC)

    if cadence == "monthly":
        start_of_month = target.replace(day=1)
        if start_of_month.month == 12:
            next_month = start_of_month.replace(year=start_of_month.year + 1, month=1)
        else:
            next_month = start_of_month.replace(month=start_of_month.month + 1)
        start_local = datetime.combine(start_of_month, time(4, 0), tzinfo=tz)
        end_local = datetime.combine(next_month, time(4, 0), tzinfo=tz) - timedelta(microseconds=1)
        return start_local.astimezone(UTC), end_local.astimezone(UTC)

    msg = f"Unsupported cadence: {cadence}. Expected 'daily', 'weekly', or 'monthly'."
    raise ValueError(msg)


def filter_rows_by_timestamp(
    rows: list[dict[str, str]],
    ts_field: str,
    start_dt: datetime,
    end_dt: datetime,
) -> list[dict[str, str]]:
    """Filters a list of dictionaries by a timestamp field within [start_dt, end_dt]."""
    filtered = []
    for row in rows:
        ts = parse_iso_timestamp(row.get(ts_field))
        if ts and start_dt <= ts <= end_dt:
            filtered.append(row)
    return filtered


def filter_history_for_cadence(
    rows: list[dict[str, str]],
    cadence: str,
    target_date: date,
) -> list[dict[str, str]]:
    """
    Filters history rows for a cadence window by matching played_at calendar date.
    """
    cadence = cadence.lower()
    if cadence == "daily":
        start_date = target_date
        end_date = target_date
    elif cadence == "weekly":
        start_date = target_date - timedelta(days=target_date.weekday())
        end_date = start_date + timedelta(days=6)
    elif cadence == "monthly":
        start_date = target_date.replace(day=1)
        if start_date.month == 12:
            next_m = start_date.replace(year=start_date.year + 1, month=1)
        else:
            next_m = start_date.replace(month=start_date.month + 1)
        end_date = next_m - timedelta(days=1)
    else:
        start_date = target_date
        end_date = target_date

    filtered = []
    for row in rows:
        ts = parse_iso_timestamp(row.get("played_at"))
        if not ts:
            continue
        if start_date <= ts.date() <= end_date:
            filtered.append(row)
    return filtered


def aggregate_listening_telemetry(
    history_slice: list[dict[str, str]],
    liked_songs_slice: list[dict[str, str]] | None = None,
) -> dict:
    """Computes comprehensive telemetry metrics from a slice of history and liked songs."""
    total_tracks = len(history_slice)
    if total_tracks == 0:
        return {
            "total_tracks": 0,
            "total_seconds": 0,
            "total_duration_display": "0m",
            "unique_artists_count": 0,
            "unique_albums_count": 0,
            "top_artists": [],
            "top_tracks": [],
            "repeat_tracks": [],
            "library_ratio_pct": 0,
            "catalog_anchor": None,
            "live_track_count": 0,
            "new_likes": [],
        }

    total_seconds = 0
    artists_counter: Counter[str] = Counter()
    albums_counter: Counter[str] = Counter()
    tracks_counter: Counter[tuple[str, str]] = Counter()
    in_library_count = 0
    live_track_count = 0

    for row in history_slice:
        # Duration
        try:
            sec = int(row.get("duration_seconds") or 0)
        except ValueError:
            sec = 0
        total_seconds += sec

        # Artists
        artist_str = row.get("artists", "").strip()
        if artist_str:
            artists_counter[artist_str] += 1

        # Albums
        album_str = row.get("album", "").strip()
        if album_str:
            albums_counter[album_str] += 1

        # Tracks
        title = row.get("title", "").strip()
        tracks_counter[(title, artist_str)] += 1

        # Live performance detection
        lower_title = title.lower()
        lower_album = album_str.lower()
        if "live" in lower_title or "live" in lower_album or "concert" in lower_album:
            live_track_count += 1

        # Library status
        if row.get("inLibrary", "").lower() in ("true", "1"):
            in_library_count += 1

    # Top repeated tracks (played >= 2 times)
    repeat_tracks = [
        {"title": t[0], "artist": t[1], "count": count}
        for t, count in tracks_counter.most_common()
        if count >= 2
    ]

    top_artists = [
        {"artist": artist, "count": count} for artist, count in artists_counter.most_common(10)
    ]
    top_tracks = [
        {"title": t[0], "artist": t[1], "count": count}
        for t, count in tracks_counter.most_common(10)
    ]

    library_ratio = round((in_library_count / total_tracks) * 100, 1)

    catalog_anchor = None
    if top_artists:
        pct = round((top_artists[0]["count"] / total_tracks) * 100)
        catalog_anchor = (
            f"{top_artists[0]['artist']} ({pct}% of session, {top_artists[0]['count']} plays)"
        )

    new_likes = []
    if liked_songs_slice:
        for row in liked_songs_slice:
            new_likes.append(
                {
                    "title": row.get("title", ""),
                    "artist": row.get("artists", ""),
                    "album": row.get("album", ""),
                }
            )

    return {
        "total_tracks": total_tracks,
        "total_seconds": total_seconds,
        "total_duration_display": format_duration(total_seconds),
        "unique_artists_count": len(artists_counter),
        "unique_albums_count": len(albums_counter),
        "top_artists": top_artists,
        "top_tracks": top_tracks,
        "repeat_tracks": repeat_tracks,
        "library_ratio_pct": library_ratio,
        "catalog_anchor": catalog_anchor,
        "live_track_count": live_track_count,
        "new_likes": new_likes,
    }


def extract_radar_candidates(
    output_dir: str,
    start_dt: datetime,
    end_dt: datetime,
    history_artists: set[str],
    played_video_ids: set[str],
    max_candidates: int = 10,
) -> list[dict]:
    """
    Extracts, ranks, and prioritizes recommendation candidates from the 5 target shelves.
    Prioritizes items that were first seen or active during [start_dt, end_dt] and have not
    already been played in the recent session.
    """
    candidates = []

    for rel_path, shelf_name in CANDIDATE_SHELVES:
        filepath = os.path.join(output_dir, rel_path)
        rows = read_csv_rows(filepath)
        for row in rows:
            vid = row.get("videoId") or row.get("id") or ""
            if vid and vid in played_video_ids:
                # User already played this track during the observation period
                continue

            title = row.get("title") or ""
            artists = row.get("artists") or row.get("description") or ""
            if not title:
                continue

            first_seen_dt = parse_iso_timestamp(row.get("first_seen"))
            last_seen_dt = parse_iso_timestamp(row.get("last_seen"))

            try:
                times_rec = int(row.get("times_recommended") or 1)
            except ValueError:
                times_rec = 1

            try:
                position = int(row.get("latest_position") or 999)
            except ValueError:
                position = 999

            is_new = bool(first_seen_dt and start_dt <= first_seen_dt <= end_dt)
            is_active = bool(last_seen_dt and last_seen_dt >= start_dt)

            if not (is_new or is_active or times_rec >= 3):
                continue

            # Check if user already knows this artist from history
            is_known_artist = bool(artists and artists.strip().lower() in history_artists)

            candidates.append(
                {
                    "id": vid,
                    "title": title,
                    "artists": artists,
                    "shelf": shelf_name,
                    "first_seen": row.get("first_seen", ""),
                    "times_recommended": times_rec,
                    "latest_position": position,
                    "is_new": is_new,
                    "is_known_artist": is_known_artist,
                }
            )

    # Sort candidates:
    # 1. New to shelf first
    # 2. Shelf position (lower is higher ranking)
    # 3. Frequency of recommendation
    candidates.sort(
        key=lambda c: (
            not c["is_new"],  # True (0) before False (1)
            c["latest_position"],
            -c["times_recommended"],
        )
    )

    # Deduplicate by (title, artists)
    unique_candidates = []
    seen_keys = set()
    for cand in candidates:
        key = (cand["title"].strip().lower(), cand["artists"].strip().lower())
        if key not in seen_keys:
            seen_keys.add(key)
            unique_candidates.append(cand)
            if len(unique_candidates) >= max_candidates:
                break

    return unique_candidates


def assemble_report_context(
    output_dir: str,
    cadence: str,
    target_date: date | datetime | None = None,
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

    start_dt, end_dt = get_cadence_window(cadence, target)

    # 1. Read history
    history_path = os.path.join(output_dir, "history.csv")
    all_history = read_csv_rows(history_path)
    history_slice = filter_history_for_cadence(all_history, cadence, target)

    # 2. Read liked songs
    liked_path = os.path.join(output_dir, "liked_songs.csv")
    all_likes = read_csv_rows(liked_path)
    liked_slice = filter_rows_by_timestamp(all_likes, "liked_at", start_dt, end_dt)

    # 3. Compute telemetry
    telemetry = aggregate_listening_telemetry(history_slice, liked_slice)

    # 4. Extract radar candidates
    history_artists = {
        row["artists"].strip().lower()
        for row in all_history
        if row.get("artists") and row["artists"].strip()
    }
    played_video_ids = {row.get("videoId") for row in history_slice if row.get("videoId")}

    radar_candidates = extract_radar_candidates(
        output_dir=output_dir,
        start_dt=start_dt,
        end_dt=end_dt,
        history_artists=history_artists,
        played_video_ids=played_video_ids,
        max_candidates=8,
    )

    return {
        "cadence": cadence.lower(),
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "period_label": format_period_label(cadence, start_dt, end_dt, target),
        "telemetry": telemetry,
        "radar_candidates": radar_candidates,
    }


def format_period_label(
    cadence: str, start_dt: datetime, end_dt: datetime, target_date: date | None = None
) -> str:
    """Returns a clean display label for the period (e.g., '2026-10-18' or '2026-W42')."""
    if cadence == "daily":
        if target_date:
            return target_date.strftime("%Y-%m-%d")
        tz = get_user_timezone()
        return start_dt.astimezone(tz).strftime("%Y-%m-%d")
    if cadence == "weekly":
        tz = get_user_timezone()
        local_start = start_dt.astimezone(tz)
        local_end = end_dt.astimezone(tz)
        year, week, _ = local_start.isocalendar()
        return (
            f"{year}-W{week:02d} ({local_start.strftime('%b %d')} - {local_end.strftime('%b %d')})"
        )
    if cadence == "monthly":
        tz = get_user_timezone()
        return start_dt.astimezone(tz).strftime("%B %Y")
    return start_dt.strftime("%Y-%m-%d")
