"""Recommendation candidate extractors (Radar, Liked & Forgotten, Full Album & Long Sets)."""

import os
from datetime import date, datetime, timedelta

from src.reports.telemetry import (
    clean_and_split_artists,
    clean_artist_display,
    parse_iso_timestamp,
    read_csv_rows,
    ytm_entity_url,
    ytm_watch_url,
)

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
    Sources from older liked_songs.csv (>=90 days old), home/forgotten_favorites.csv,
    and mixes/archive_mix.csv.
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
