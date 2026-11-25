"""Telemetry metrics, cadence date windows, and metadata hygiene for AI listening reports."""

import csv
import os
import re
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta

from src.util import get_user_timezone

_VIEW_COUNT_RE = re.compile(r"^\d+(?:\.\d+)?[KMB]?\s+views$", re.IGNORECASE)


def ytm_watch_url(video_id: str | None) -> str:
    """Returns a direct YouTube Music watch URL for a videoId."""
    vid = (video_id or "").strip()
    return f"https://music.youtube.com/watch?v={vid}" if vid else ""


def ytm_entity_url(entity_id: str | None) -> str:
    """Returns an appropriate YouTube Music URL for an album, playlist, or video ID."""
    eid = (entity_id or "").strip()
    if not eid:
        return ""
    if eid.startswith(("MPREb_", "FEmusic_", "UC")):
        return f"https://music.youtube.com/browse/{eid}"
    if eid.startswith(("PL", "OLAK5uy_", "RDCLAK5uy_")):
        return f"https://music.youtube.com/playlist?list={eid}"
    if eid.startswith("VL") and len(eid) > 2:
        return f"https://music.youtube.com/playlist?list={eid[2:]}"
    return ytm_watch_url(eid)


def clean_and_split_artists(artist_str: str | None) -> list[str]:
    """
    Splits comma-separated artist strings into clean individual artist names,
    filtering out scraped YouTube view-count artifacts (e.g., '1.2M views').
    """
    if not artist_str:
        return []
    parts = [p.strip() for p in artist_str.split(",")]
    cleaned: list[str] = []
    seen_lower: set[str] = set()
    for part in parts:
        if not part or _VIEW_COUNT_RE.match(part):
            continue
        low = part.lower()
        if low not in seen_lower:
            seen_lower.add(low)
            cleaned.append(part)
    return cleaned


def clean_artist_display(artist_str: str | None) -> str:
    """Returns a cleaned comma-joined artist display string without view-count noise."""
    parts = clean_and_split_artists(artist_str)
    return ", ".join(parts) if parts else (artist_str or "").strip()


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


def get_cadence_dates(cadence: str, target_date: date) -> tuple[date, date]:
    """Returns (start_date, end_date) inclusive calendar dates for a cadence."""
    cadence = cadence.lower()
    if cadence == "daily":
        return target_date, target_date
    if cadence == "weekly":
        start_date = target_date - timedelta(days=target_date.weekday())
        return start_date, start_date + timedelta(days=6)
    if cadence == "monthly":
        start_date = target_date.replace(day=1)
        if start_date.month == 12:
            next_m = start_date.replace(year=start_date.year + 1, month=1)
        else:
            next_m = start_date.replace(month=start_date.month + 1)
        return start_date, next_m - timedelta(days=1)
    msg = f"Unsupported cadence: {cadence}. Expected 'daily', 'weekly', or 'monthly'."
    raise ValueError(msg)


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

    start_date, end_date = get_cadence_dates(cadence, target)
    start_local = datetime.combine(start_date, time(4, 0), tzinfo=tz)
    next_day_after_end = end_date + timedelta(days=1)
    end_local = datetime.combine(next_day_after_end, time(4, 0), tzinfo=tz) - timedelta(
        microseconds=1
    )
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def format_period_label(
    cadence: str, start_dt: datetime, end_dt: datetime, target_date: date | None = None
) -> str:
    """Returns a clean display label for the period (e.g., '2026-10-18' or '2026-W42')."""
    cadence = cadence.lower()
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
    """Filters history rows for a cadence window by matching played_at calendar date."""
    start_date, end_date = get_cadence_dates(cadence, target_date)
    filtered = []
    for row in rows:
        ts = parse_iso_timestamp(row.get("played_at"))
        if ts and start_date <= ts.date() <= end_date:
            filtered.append(row)
    return filtered


def aggregate_listening_telemetry(
    history_slice: list[dict[str, str]],
    liked_songs_slice: list[dict[str, str]] | None = None,
    prior_artists: set[str] | None = None,
) -> dict:
    """Computes telemetry metrics from a slice of history and liked songs."""
    total_tracks = len(history_slice)
    if total_tracks == 0:
        return {
            "total_tracks": 0,
            "total_seconds": 0,
            "total_duration_display": "0m",
            "unique_artists_count": 0,
            "unique_albums_count": 0,
            "new_artists_count": 0,
            "new_artists": [],
            "top_artists": [],
            "top_tracks": [],
            "repeat_tracks": [],
            "version_collisions": [],
            "catalog_anchor": None,
            "live_track_count": 0,
            "liked_plays_count": 0,
            "new_likes": [],
        }

    total_seconds = 0
    artists_counter: Counter[str] = Counter()
    artist_display_by_lower: dict[str, str] = {}
    albums_counter: Counter[str] = Counter()
    tracks_counter: Counter[tuple[str, str]] = Counter()
    track_vid_map: dict[tuple[str, str], str] = {}
    title_versions_map: dict[str, dict[str, set[str]]] = {}
    live_track_count = 0
    liked_plays_count = 0

    for row in history_slice:
        try:
            sec = int(row.get("duration_seconds") or 0)
        except ValueError:
            sec = 0
        total_seconds += sec

        raw_artist = row.get("artists", "")
        split_names = clean_and_split_artists(raw_artist)
        for name in split_names:
            low = name.lower()
            canonical = artist_display_by_lower.setdefault(low, name)
            artists_counter[canonical] += 1

        artist_display = clean_artist_display(raw_artist)

        album_str = row.get("album", "").strip()
        if album_str:
            albums_counter[album_str] += 1

        title = row.get("title", "").strip()
        vid = (row.get("videoId") or "").strip()
        track_key = (title, artist_display)
        tracks_counter[track_key] += 1
        if vid and track_key not in track_vid_map:
            track_vid_map[track_key] = vid

        if title and artist_display:
            norm_title = title.lower()
            entry = title_versions_map.setdefault(
                norm_title, {"display_title": title, "artists": set()}
            )
            entry["artists"].add(artist_display)

        lower_title = title.lower()
        lower_album = album_str.lower()
        if "live" in lower_title or "live" in lower_album or "concert" in lower_album:
            live_track_count += 1

        if (row.get("likeStatus") or "").upper() == "LIKE":
            liked_plays_count += 1

    repeat_tracks = [
        {
            "title": t[0],
            "artist": t[1],
            "count": count,
            "videoId": track_vid_map.get(t, ""),
            "url": ytm_watch_url(track_vid_map.get(t, "")),
        }
        for t, count in tracks_counter.most_common()
        if count >= 2
    ]

    top_artists = [
        {"artist": artist, "count": count} for artist, count in artists_counter.most_common(10)
    ]
    top_tracks = [
        {
            "title": t[0],
            "artist": t[1],
            "count": count,
            "videoId": track_vid_map.get(t, ""),
            "url": ytm_watch_url(track_vid_map.get(t, "")),
        }
        for t, count in tracks_counter.most_common(10)
    ]

    version_collisions = [
        {"title": info["display_title"], "artists": sorted(info["artists"])}
        for info in title_versions_map.values()
        if len(info["artists"]) >= 2
    ]

    new_artists: list[str] = []
    if prior_artists is not None:
        new_artists = [
            artist
            for artist, _ in artists_counter.most_common()
            if artist.lower() not in prior_artists
        ]

    catalog_anchor = None
    if top_artists:
        pct = round((top_artists[0]["count"] / total_tracks) * 100)
        catalog_anchor = (
            f"{top_artists[0]['artist']} ({pct}% of session, {top_artists[0]['count']} plays)"
        )

    new_likes = []
    if liked_songs_slice:
        for row in liked_songs_slice:
            vid = (row.get("videoId") or "").strip()
            new_likes.append(
                {
                    "title": row.get("title", ""),
                    "artist": clean_artist_display(row.get("artists", "")),
                    "album": row.get("album", ""),
                    "videoId": vid,
                    "url": ytm_watch_url(vid),
                }
            )

    return {
        "total_tracks": total_tracks,
        "total_seconds": total_seconds,
        "total_duration_display": format_duration(total_seconds),
        "unique_artists_count": len(artists_counter),
        "unique_albums_count": len(albums_counter),
        "new_artists_count": len(new_artists),
        "new_artists": new_artists[:10],
        "top_artists": top_artists,
        "top_tracks": top_tracks,
        "repeat_tracks": repeat_tracks,
        "version_collisions": version_collisions,
        "catalog_anchor": catalog_anchor,
        "live_track_count": live_track_count,
        "liked_plays_count": liked_plays_count,
        "new_likes": new_likes,
    }
