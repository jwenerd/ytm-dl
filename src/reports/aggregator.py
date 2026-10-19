"""Data aggregation and candidate recommendation extraction for AI listening reports."""

import csv
import os
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta

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
    - daily: full 24h window for target_date (default yesterday).
    - weekly: Monday 00:00:00 to Sunday 23:59:59 UTC of the target week.
    - monthly: 1st of month 00:00:00 to last second of month.
    """
    now = datetime.now(UTC)
    if target_date is None:
        target = now.date() - timedelta(days=1)
    elif isinstance(target_date, datetime):
        target = target_date.astimezone(UTC).date()
    else:
        target = target_date

    cadence = cadence.lower()
    if cadence == "daily":
        start = datetime.combine(target, time.min, tzinfo=UTC)
        end = datetime.combine(target, time.max, tzinfo=UTC)
        return start, end

    if cadence == "weekly":
        # Target week: Monday to Sunday
        start_of_week = target - timedelta(days=target.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        start = datetime.combine(start_of_week, time.min, tzinfo=UTC)
        end = datetime.combine(end_of_week, time.max, tzinfo=UTC)
        return start, end

    if cadence == "monthly":
        start_of_month = target.replace(day=1)
        # Find last day of month
        if start_of_month.month == 12:
            next_month = start_of_month.replace(year=start_of_month.year + 1, month=1)
        else:
            next_month = start_of_month.replace(month=start_of_month.month + 1)
        last_day = next_month - timedelta(days=1)
        start = datetime.combine(start_of_month, time.min, tzinfo=UTC)
        end = datetime.combine(last_day, time.max, tzinfo=UTC)
        return start, end

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
            "temporal_distribution": {"morning": 0, "afternoon": 0, "evening": 0, "night": 0},
            "new_likes": [],
        }

    total_seconds = 0
    artists_counter: Counter[str] = Counter()
    albums_counter: Counter[str] = Counter()
    tracks_counter: Counter[tuple[str, str]] = Counter()
    in_library_count = 0
    temporal_dist = {"morning": 0, "afternoon": 0, "evening": 0, "night": 0}

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

        # Library status
        if row.get("inLibrary", "").lower() in ("true", "1"):
            in_library_count += 1

        # Temporal binning (UTC hour)
        dt = parse_iso_timestamp(row.get("played_at"))
        if dt:
            hour = dt.hour
            if 6 <= hour < 12:
                temporal_dist["morning"] += 1
            elif 12 <= hour < 18:
                temporal_dist["afternoon"] += 1
            elif 18 <= hour < 24:
                temporal_dist["evening"] += 1
            else:
                temporal_dist["night"] += 1

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
        "temporal_distribution": temporal_dist,
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
    start_dt, end_dt = get_cadence_window(cadence, target_date)

    # 1. Read history
    history_path = os.path.join(output_dir, "history.csv")
    all_history = read_csv_rows(history_path)
    history_slice = filter_rows_by_timestamp(all_history, "played_at", start_dt, end_dt)

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
        "period_label": format_period_label(cadence, start_dt, end_dt),
        "telemetry": telemetry,
        "radar_candidates": radar_candidates,
    }


def format_period_label(cadence: str, start_dt: datetime, end_dt: datetime) -> str:
    """Returns a clean display label for the period (e.g., '2026-10-18' or '2026-W42')."""
    if cadence == "daily":
        return start_dt.strftime("%Y-%m-%d")
    if cadence == "weekly":
        year, week, _ = start_dt.isocalendar()
        return f"{year}-W{week:02d} ({start_dt.strftime('%b %d')} - {end_dt.strftime('%b %d')})"
    if cadence == "monthly":
        return start_dt.strftime("%B %Y")
    return start_dt.strftime("%Y-%m-%d")
