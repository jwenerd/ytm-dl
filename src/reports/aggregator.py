"""Data aggregation and candidate recommendation extraction for AI listening reports."""

import csv
import os
import re
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

LONG_LISTEN_SHELVES = [
    ("home/long_listens.csv", "long_listens"),
    ("home/live_performances.csv", "live_performances"),
]

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


def extract_radar_candidates(
    output_dir: str,
    start_dt: datetime,
    end_dt: datetime,
    history_artists: set[str],
    played_video_ids: set[str],
    excluded_ids: set[str] | None = None,
    max_candidates: int = 8,
) -> list[dict]:
    """
    Extracts, ranks, and prioritizes song recommendation candidates from the 5 target shelves.
    Filters out non-song items (playlists/albums) and recently pitched radar IDs.
    """
    candidates = []
    skip_ids = played_video_ids | (excluded_ids or set())

    for rel_path, shelf_name in CANDIDATE_SHELVES:
        filepath = os.path.join(output_dir, rel_path)
        rows = read_csv_rows(filepath)
        for row in rows:
            item_type = (row.get("type") or "").strip().lower()
            if item_type and item_type != "song":
                continue

            vid = (row.get("videoId") or row.get("id") or "").strip()
            if not vid or vid in skip_ids:
                continue

            title = (row.get("title") or "").strip()
            artists = clean_artist_display(row.get("artists") or row.get("description") or "")
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

            split_cand_artists = clean_and_split_artists(artists)
            is_known_artist = any(a.lower() in history_artists for a in split_cand_artists)

            candidates.append(
                {
                    "id": vid,
                    "title": title,
                    "artists": artists,
                    "url": ytm_watch_url(vid),
                    "shelf": shelf_name,
                    "first_seen": row.get("first_seen", ""),
                    "times_recommended": times_rec,
                    "latest_position": position,
                    "is_new": is_new,
                    "is_known_artist": is_known_artist,
                }
            )

    candidates.sort(
        key=lambda c: (
            not c["is_new"],
            c["latest_position"],
            -c["times_recommended"],
        )
    )

    unique_candidates = []
    seen_keys = set()
    for cand in candidates:
        key = (cand["title"].lower(), cand["artists"].lower())
        if key not in seen_keys and cand["id"] not in seen_keys:
            seen_keys.add(key)
            seen_keys.add(cand["id"])
            unique_candidates.append(cand)
            if len(unique_candidates) >= max_candidates:
                break

    return unique_candidates


def extract_forgotten_favorites(
    output_dir: str,
    all_history: list[dict[str, str]],
    all_likes: list[dict[str, str]],
    target_date: date,
    excluded_ids: set[str] | None = None,
    max_candidates: int = 3,
) -> list[dict]:
    """
    Finds 'Liked & Forgotten' or buried archival gems unplayed in the last 60 days.
    Sources from older liked_songs.csv (>=90 days old), home/forgotten_favorites.csv, and mixes/archive_mix.csv.
    """
    recent_cutoff = target_date - timedelta(days=60)
    liked_age_cutoff = target_date - timedelta(days=90)
    skip_ids = set(excluded_ids or set())

    recent_vids: set[str] = set()
    last_played_by_vid: dict[str, str] = {}
    for row in all_history:
        vid = (row.get("videoId") or "").strip()
        ts = parse_iso_timestamp(row.get("played_at"))
        if not vid or not ts:
            continue
        play_date = ts.date()
        if play_date > target_date:
            continue
        date_str = play_date.strftime("%Y-%m-%d")
        if vid not in last_played_by_vid or date_str > last_played_by_vid[vid]:
            last_played_by_vid[vid] = date_str
        if play_date >= recent_cutoff:
            recent_vids.add(vid)

    candidates: list[dict] = []

    # 1. Older liked songs unplayed in the last 60 days
    for row in all_likes:
        vid = (row.get("videoId") or "").strip()
        title = (row.get("title") or "").strip()
        if not vid or not title or vid in recent_vids or vid in skip_ids:
            continue
        liked_dt = parse_iso_timestamp(row.get("liked_at"))
        if not liked_dt or liked_dt.date() > liked_age_cutoff:
            continue
        artists = clean_artist_display(row.get("artists", ""))
        liked_str = liked_dt.date().strftime("%Y-%m-%d")
        last_spun = last_played_by_vid.get(vid)
        note = f"Liked {liked_str}" + (
            f", last spun {last_spun}" if last_spun else ", unplayed since"
        )
        candidates.append(
            {
                "id": vid,
                "title": title,
                "artists": artists,
                "url": ytm_watch_url(vid),
                "source": "liked_songs",
                "note": note,
            }
        )
        if len(candidates) >= max_candidates * 2:
            break

    # 2. Supplement from home/forgotten_favorites.csv and mixes/archive_mix.csv
    for rel_path, shelf_name in [
        ("home/forgotten_favorites.csv", "forgotten_favorites"),
        ("mixes/archive_mix.csv", "archive_mix"),
    ]:
        rows = read_csv_rows(os.path.join(output_dir, rel_path))
        for row in rows:
            item_type = (row.get("type") or "").strip().lower()
            if item_type and item_type != "song":
                continue
            vid = (row.get("videoId") or row.get("id") or "").strip()
            title = (row.get("title") or "").strip()
            if not vid or not title or vid in recent_vids or vid in skip_ids:
                continue
            artists = clean_artist_display(row.get("artists", ""))
            last_spun = last_played_by_vid.get(vid)
            note = f"Last spun {last_spun}" if last_spun else f"From {shelf_name}"
            candidates.append(
                {
                    "id": vid,
                    "title": title,
                    "artists": artists,
                    "url": ytm_watch_url(vid),
                    "source": shelf_name,
                    "note": note,
                }
            )

    unique: list[dict] = []
    seen: set[str] = set()
    for cand in candidates:
        dedup_key = f"{cand['title'].lower()}::{cand['artists'].lower()}"
        if cand["id"] not in seen and dedup_key not in seen:
            seen.add(cand["id"])
            seen.add(dedup_key)
            unique.append(cand)
            if len(unique) >= max_candidates:
                break

    return unique


def extract_long_form_picks(
    output_dir: str,
    played_video_ids: set[str],
    excluded_ids: set[str] | None = None,
    max_albums: int = 3,
    max_sets: int = 3,
) -> dict[str, list[dict]]:
    """
    Extracts candidate front-to-back Full Albums (home/albums_for_you.csv) and
    Long Sets / Live Performances (home/long_listens.csv, home/live_performances.csv).
    """
    skip_ids = played_video_ids | (excluded_ids or set())

    albums: list[dict] = []
    seen_albums: set[str] = set()
    for row in read_csv_rows(os.path.join(output_dir, "home/albums_for_you.csv")):
        item_type = (row.get("type") or "").strip().lower()
        if item_type and item_type != "album":
            continue
        aid = (row.get("id") or "").strip()
        title = (row.get("title") or "").strip()
        if not aid or not title or aid in skip_ids or aid in seen_albums:
            continue
        seen_albums.add(aid)
        albums.append(
            {
                "id": aid,
                "title": title,
                "artists": clean_artist_display(row.get("artists", "")),
                "url": ytm_entity_url(aid),
            }
        )
        if len(albums) >= max_albums:
            break

    long_sets: list[dict] = []
    seen_sets: set[str] = set()
    for rel_path, shelf_name in LONG_LISTEN_SHELVES:
        for row in read_csv_rows(os.path.join(output_dir, rel_path)):
            item_type = (row.get("type") or "").strip().lower()
            if item_type and item_type not in ("video", "song"):
                continue
            vid = (row.get("videoId") or row.get("id") or "").strip()
            title = (row.get("title") or "").strip()
            if not vid or not title or vid in skip_ids or vid in seen_sets:
                continue
            seen_sets.add(vid)
            long_sets.append(
                {
                    "id": vid,
                    "title": title,
                    "artists": clean_artist_display(row.get("artists", "")),
                    "shelf": shelf_name,
                    "url": ytm_watch_url(vid),
                }
            )
            if len(long_sets) >= max_sets:
                break
        if len(long_sets) >= max_sets:
            break

    return {"albums": albums, "long_sets": long_sets}


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
