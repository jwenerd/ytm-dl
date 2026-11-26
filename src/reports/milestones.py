"""Deterministic Milestones & Obsession Tracker (`output/meta/milestones.yaml` & `output/MILESTONES.md`)."""

import argparse
import hashlib
import os
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

import yaml

from src.reports.artist_tags import read_artist_tags
from src.reports.telemetry import (
    clean_and_split_artists,
    clean_artist_display,
    parse_iso_timestamp,
    read_csv_rows,
    ytm_watch_url,
)
from src.util import get_user_timezone

SCHEMA_VERSION = 1

# Unbounded tier configs: (ramp_thresholds, linear_start, step)
_TIERS: dict[str, tuple[tuple[int, ...], int, int]] = {
    "catalog_plays": ((), 1000, 1000),
    "catalog_hours": ((), 100, 100),
    "catalog_artists": ((), 100, 100),
    "artist_plays": ((25,), 50, 50),
    "artist_hours": ((), 10, 10),
    "artist_tracks": ((), 25, 25),
    "track_plays": ((), 10, 10),
    "album_plays": ((), 25, 25),
    "streak_days": ((7, 14), 30, 30),
}

_CATEGORY_CODE: dict[str, str] = {
    "catalog_plays": "CATALOG",
    "catalog_hours": "CATALOG",
    "catalog_artists": "CATALOG",
    "artist_plays": "ARTIST",
    "artist_hours": "ARTIST",
    "artist_tracks": "DEPTH",
    "track_plays": "TRACK",
    "album_plays": "ALBUM",
    "streak_days": "STREAK",
}


def _crossed_thresholds(
    prev: int,
    curr: int,
    *,
    ramp: tuple[int, ...] = (),
    linear_start: int,
    step: int,
) -> list[int]:
    if curr <= prev:
        return []
    crossed = [t for t in ramp if prev < t <= curr]
    if curr >= linear_start:
        first_idx = 0 if prev < linear_start else (prev - linear_start) // step + 1
        last_idx = (curr - linear_start) // step
        for idx in range(first_idx, last_idx + 1):
            crossed.append(linear_start + idx * step)
    return crossed


def _next_threshold(
    curr: int,
    *,
    ramp: tuple[int, ...] = (),
    linear_start: int,
    step: int,
) -> int:
    for t in ramp:
        if curr < t:
            return t
    if curr < linear_start:
        return linear_start
    idx = (curr - linear_start) // step + 1
    return linear_start + idx * step


def _crossed(tier: str, prev: int, curr: int) -> list[int]:
    ramp, linear_start, step = _TIERS[tier]
    return _crossed_thresholds(prev, curr, ramp=ramp, linear_start=linear_start, step=step)


def _next_tier(tier: str, curr: int) -> int:
    ramp, linear_start, step = _TIERS[tier]
    return _next_threshold(curr, ramp=ramp, linear_start=linear_start, step=step)


def _prev_threshold(
    curr: int,
    *,
    ramp: tuple[int, ...] = (),
    linear_start: int,
    step: int,
) -> int:
    if curr >= linear_start:
        return linear_start + ((curr - linear_start) // step) * step
    for t in reversed(ramp):
        if curr >= t:
            return t
    return 0


def _prev_tier(tier: str, curr: int) -> int:
    ramp, linear_start, step = _TIERS[tier]
    return _prev_threshold(curr, ramp=ramp, linear_start=linear_start, step=step)


def _step_ratio(tier: str, curr: int, nxt: int) -> float:
    prev = _prev_tier(tier, curr)
    return (curr - prev) / max(1, nxt - prev)


def _weekly_hash(week_seed: str, pool: str, key: str) -> str:
    return hashlib.sha256(f"{week_seed}:{pool}:{key}".encode()).hexdigest()


def _default_store() -> dict[str, Any]:
    return {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "updated_at": "",
            "first_history_date": "",
            "last_history_date": "",
            "total_unlocked": 0,
        },
        "records": {
            "longest_streak_days": 0,
            "longest_streak_end": "",
            "peak_day_plays": 0,
            "peak_day_date": "",
            "peak_week_plays": 0,
            "peak_week_label": "",
        },
        "unlocked": {},
    }


def _atomic_write_text(filepath: str, content: str) -> None:
    parent = os.path.dirname(filepath)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = f"{filepath}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, filepath)


def read_milestones(meta_path: str) -> dict[str, Any]:
    """Reads `output/meta/milestones.yaml` or returns an initialized store."""
    if not os.path.isfile(meta_path):
        return _default_store()
    try:
        with open(meta_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return _default_store()
        default = _default_store()
        meta = dict(default["meta"])
        if isinstance(data.get("meta"), dict):
            meta.update(data["meta"])
        records = dict(default["records"])
        if isinstance(data.get("records"), dict):
            records.update(data["records"])
        unlocked = data.get("unlocked")
        return {
            "meta": meta,
            "records": records,
            "unlocked": dict(unlocked) if isinstance(unlocked, dict) else {},
        }
    except (OSError, yaml.YAMLError):
        return _default_store()


def write_milestones(
    meta_path: str,
    store: dict[str, Any],
    now_dt: datetime | None = None,
) -> None:
    """Persists `output/meta/milestones.yaml` atomically."""
    ts = (now_dt or datetime.now(UTC)).isoformat()
    unlocked = store.get("unlocked") or {}
    meta = dict(store.get("meta") or {})
    meta["schema_version"] = SCHEMA_VERSION
    meta["updated_at"] = ts
    meta["total_unlocked"] = len(unlocked)
    payload = {
        "meta": meta,
        "records": dict(store.get("records") or _default_store()["records"]),
        "unlocked": unlocked,
    }
    dumped = yaml.safe_dump(payload, sort_keys=True, indent=2, allow_unicode=True)
    _atomic_write_text(meta_path, dumped)


def _safe_duration(raw: Any) -> int:
    try:
        return max(0, int(raw or 0))
    except (ValueError, TypeError):
        return 0


def _load_artist_tags_map(output_dir: str) -> dict[str, Any]:
    tags_path = os.path.join(output_dir, "meta", "artist_tags.yaml")
    tags = read_artist_tags(tags_path)
    artists = tags.get("artists")
    return dict(artists) if isinstance(artists, dict) else {}


def _uploader_keys_from_tags(tags_map: dict[str, Any]) -> set[str]:
    return {
        k for k, v in tags_map.items() if isinstance(v, dict) and bool(v.get("is_uploader", False))
    }


def _load_parsed_history(output_dir: str) -> list[tuple[date, dict[str, str]]]:
    rows = read_csv_rows(os.path.join(output_dir, "history.csv"))
    parsed: list[tuple[date, dict[str, str]]] = []
    for row in reversed(rows):
        ts = parse_iso_timestamp(row.get("played_at"))
        if ts:
            parsed.append((ts.date(), row))
    return parsed


def _record_unlock(
    unlocked: dict[str, dict[str, Any]],
    newly_unlocked: list[dict[str, Any]],
    *,
    key: str,
    category: str,
    entity: str,
    threshold: int,
    unlock_date: date,
    backfill: bool,
) -> None:
    if key in unlocked:
        return
    entry = {
        "category": category,
        "entity": entity,
        "threshold": threshold,
        "date": unlock_date.isoformat(),
        "backfilled": bool(backfill),
    }
    unlocked[key] = entry
    if not backfill:
        newly_unlocked.append({"key": key, **entry})


def _compute_streaks_and_unlock(
    daily_plays: dict[date, int],
    ref_date: date,
    unlocked: dict[str, dict[str, Any]],
    newly_unlocked: list[dict[str, Any]],
    backfill: bool,
) -> tuple[int, int, str]:
    longest_days = 0
    longest_end = ""
    prev_day: date | None = None
    streak = 0

    for d in sorted(daily_plays):
        streak = streak + 1 if prev_day is not None and (d - prev_day).days == 1 else 1
        prev_day = d
        for t in _crossed("streak_days", streak - 1, streak):
            _record_unlock(
                unlocked,
                newly_unlocked,
                key=f"streak:days:{t}",
                category="streak_days",
                entity="Listening Streak",
                threshold=t,
                unlock_date=d,
                backfill=backfill,
            )
        if streak >= longest_days:
            longest_days = streak
            longest_end = d.isoformat()

    current_streak = 0
    if ref_date in daily_plays:
        cursor = ref_date
    elif (ref_date - timedelta(days=1)) in daily_plays:
        cursor = ref_date - timedelta(days=1)
    else:
        cursor = None
    while cursor is not None and cursor in daily_plays:
        current_streak += 1
        cursor -= timedelta(days=1)

    return current_streak, longest_days, longest_end


def _find_rare_tag(
    low: str,
    tags_map: dict[str, Any],
    genre_plays: Counter[str],
    era_plays: Counter[str],
    total_plays: int,
) -> str:
    entry = tags_map.get(low)
    if not isinstance(entry, dict):
        return ""
    pg = str(entry.get("primary_genre") or "")
    if pg and pg not in ("Other", "Uploader / Channel") and genre_plays[pg] / total_plays < 0.03:
        return pg
    era = str(entry.get("era") or "")
    if era and era != "Unknown" and era_plays[era] / total_plays < 0.03:
        return era
    return ""


def _build_almost_there(
    *,
    ref_date: date,
    total_plays: int,
    total_hours: int,
    unique_artists_count: int,
    current_streak: int,
    artist_plays: Counter[str],
    artist_tracks: dict[str, set[str]],
    artist_last_date: dict[str, date],
    artist_display_by_low: dict[str, str],
    track_plays: Counter[str],
    track_last_date: dict[str, date],
    track_display_by_vid: dict[str, str],
    track_artist_low_by_vid: dict[str, str],
    tags_map: dict[str, Any],
    genre_plays: Counter[str],
    era_plays: Counter[str],
) -> list[dict[str, Any]]:
    hot_cands: list[dict[str, Any]] = []
    small_cands: list[dict[str, Any]] = []
    dusty_cands: list[dict[str, Any]] = []
    rare_cands: list[dict[str, Any]] = []
    track_cands: list[dict[str, Any]] = []

    def _make_cand(
        *,
        key: str,
        entity_key: str,
        category: str,
        tier: str,
        label: str,
        curr: int,
        nxt: int,
        noun: str,
        days_since: int,
        url: str = "",
    ) -> dict[str, Any] | None:
        if curr <= 0:
            return None
        ratio = _step_ratio(tier, curr, nxt)
        rem = nxt - curr
        suffix = noun if rem == 1 else f"{noun}s"
        prog_unit = noun if noun in ("h", "d") else ""
        rem_display = f"{rem:,}{noun}" if noun in ("h", "d") else f"{rem:,} {suffix}"
        return {
            "key": key,
            "entity_key": entity_key,
            "category": category,
            "label": label,
            "current": curr,
            "target": nxt,
            "remaining": rem,
            "ratio": ratio,
            "score": ratio / (1.0 + days_since / 14.0),
            "progress": f"{curr:,}/{nxt:,}{prog_unit}",
            "remaining_display": rem_display,
            "url": url,
        }

    for tier, key, category, curr, fmt_label, noun in (
        ("catalog_plays", "catalog:plays", "catalog", total_plays, "plays", "play"),
        ("catalog_hours", "catalog:hours", "catalog", total_hours, "h", "h"),
        (
            "catalog_artists",
            "catalog:artists",
            "catalog",
            unique_artists_count,
            "artists",
            "artist",
        ),
    ):
        nxt = _next_tier(tier, curr)
        lbl = (
            f"**Library** — {nxt:,}h" if fmt_label == "h" else f"**Library** — {nxt:,} {fmt_label}"
        )
        cand = _make_cand(
            key=key,
            entity_key=key,
            category=category,
            tier=tier,
            label=lbl,
            curr=curr,
            nxt=nxt,
            noun=noun,
            days_since=0,
        )
        if cand and cand["ratio"] >= 0.85:
            hot_cands.append(cand)

    if current_streak > 0:
        nxt_st = _next_tier("streak_days", current_streak)
        cand = _make_cand(
            key="streak:days",
            entity_key="streak:days",
            category="streak",
            tier="streak_days",
            label=f"**{nxt_st}d Streak**",
            curr=current_streak,
            nxt=nxt_st,
            noun="d",
            days_since=0,
        )
        if cand and cand["ratio"] >= 0.50:
            hot_cands.append(cand)

    for low, last_d in artist_last_date.items():
        days_since = max(0, (ref_date - last_d).days)
        display = artist_display_by_low[low]

        ap = artist_plays[low]
        nxt_ap = _next_tier("artist_plays", ap)
        cand_ap = _make_cand(
            key=f"artist_plays:{low}",
            entity_key=f"artist:{low}",
            category="artist_plays",
            tier="artist_plays",
            label=f"**{display}** — {nxt_ap:,} plays",
            curr=ap,
            nxt=nxt_ap,
            noun="play",
            days_since=days_since,
        )
        if cand_ap:
            if days_since <= 45 and (cand_ap["ratio"] >= 0.75 or cand_ap["remaining"] <= 5):
                hot_cands.append(cand_ap)
            if days_since <= 180:
                if cand_ap["target"] <= 50 and 1 <= cand_ap["remaining"] <= 3:
                    small_cands.append(cand_ap)
                if cand_ap["ratio"] >= 0.70 or cand_ap["remaining"] <= 5:
                    rare_tag = _find_rare_tag(low, tags_map, genre_plays, era_plays, total_plays)
                    if rare_tag:
                        rare_cands.append(
                            {
                                **cand_ap,
                                "remaining_display": f"{cand_ap['remaining_display']} ({rare_tag})",
                            }
                        )
            if days_since >= 90 and 1 <= cand_ap["remaining"] <= 2:
                dusty_cands.append(
                    {
                        **cand_ap,
                        "remaining_display": f"{cand_ap['remaining_display']} ({days_since}d idle)",
                    }
                )

        depth = len(artist_tracks[low])
        nxt_at = _next_tier("artist_tracks", depth)
        cand_at = _make_cand(
            key=f"artist_tracks:{low}",
            entity_key=f"artist:{low}",
            category="artist_tracks",
            tier="artist_tracks",
            label=f"**{display}** — {nxt_at:,} tracks",
            curr=depth,
            nxt=nxt_at,
            noun="track",
            days_since=days_since,
        )
        if cand_at:
            if days_since <= 45 and (cand_at["ratio"] >= 0.75 or cand_at["remaining"] <= 5):
                hot_cands.append(cand_at)
            if days_since <= 180 and cand_at["target"] == 25 and 1 <= cand_at["remaining"] <= 3:
                small_cands.append(cand_at)
            if days_since >= 90 and 1 <= cand_at["remaining"] <= 2:
                dusty_cands.append(
                    {
                        **cand_at,
                        "remaining_display": f"{cand_at['remaining_display']} ({days_since}d idle)",
                    }
                )

    for vid, last_d in track_last_date.items():
        days_since = max(0, (ref_date - last_d).days)
        tp = track_plays[vid]
        nxt_tp = _next_tier("track_plays", tp)
        p_low = track_artist_low_by_vid.get(vid, "")
        entity_key = f"artist:{p_low}" if p_low else f"track:{vid}"
        cand_tp = _make_cand(
            key=f"track_plays:{vid}",
            entity_key=entity_key,
            category="track_plays",
            tier="track_plays",
            label=f"**{track_display_by_vid[vid]}** — {nxt_tp:,} plays",
            curr=tp,
            nxt=nxt_tp,
            noun="play",
            days_since=days_since,
            url=ytm_watch_url(vid),
        )
        if cand_tp:
            if days_since <= 45 and (cand_tp["ratio"] >= 0.75 or cand_tp["remaining"] <= 5):
                hot_cands.append(cand_tp)
            if days_since <= 180 and 1 <= cand_tp["remaining"] <= 2:
                track_cands.append(cand_tp)
            if days_since >= 90 and 1 <= cand_tp["remaining"] <= 2:
                dusty_cands.append(
                    {
                        **cand_tp,
                        "remaining_display": f"{cand_tp['remaining_display']} ({days_since}d idle)",
                    }
                )

    hot_cands.sort(key=lambda item: (-item["score"], item["remaining"], item["label"].lower()))
    hot_selected: list[dict[str, Any]] = []
    cat_counts: Counter[str] = Counter()
    used_entities: set[str] = set()
    for cand in hot_cands:
        cat = cand["category"]
        cat_cap = 1 if cat == "catalog" else 2
        if cand["entity_key"] in used_entities or cat_counts[cat] >= cat_cap:
            continue
        cat_counts[cat] += 1
        used_entities.add(cand["entity_key"])
        hot_selected.append({**cand, "tag": "HOT"})
        if len(hot_selected) >= 6:
            break

    iso_year, iso_week, _ = ref_date.isocalendar()
    week_seed = f"{iso_year}-W{iso_week:02d}"
    wildcards_map: dict[str, list[dict[str, Any]]] = {
        "SMALL": small_cands,
        "DUSTY": dusty_cands,
        "RARE": rare_cands,
        "TRACK": track_cands,
    }
    pool_order = sorted(wildcards_map, key=lambda p: _weekly_hash(week_seed, "pool_order", p))
    wildcard_selected: list[dict[str, Any]] = []
    for pool in pool_order:
        eligible = [c for c in wildcards_map[pool] if c["entity_key"] not in used_entities]
        if not eligible:
            continue
        pick = min(eligible, key=lambda c: _weekly_hash(week_seed, pool, c["key"]))
        used_entities.add(pick["entity_key"])
        wildcard_selected.append({**pick, "tag": pool})
        if len(wildcard_selected) >= 3:
            break

    return hot_selected + wildcard_selected


def evaluate_milestones(
    output_dir: str,
    reference_date: date | None = None,
    backfill: bool = False,
    *,
    parsed_rows: list[tuple[date, dict[str, str]]] | None = None,
    tags_map: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """
    Replays `history.csv` chronologically to record listening milestones, peak records,
    and active progress toward upcoming linear targets.
    """
    meta_path = os.path.join(output_dir, "meta", "milestones.yaml")
    store = read_milestones(meta_path)
    unlocked = store["unlocked"]
    newly_unlocked: list[dict[str, Any]] = []

    effective_tags = _load_artist_tags_map(output_dir) if tags_map is None else tags_map
    uploader_keys = _uploader_keys_from_tags(effective_tags)
    effective_rows = _load_parsed_history(output_dir) if parsed_rows is None else parsed_rows

    total_plays = 0
    total_seconds = 0
    unique_artists: set[str] = set()
    artist_casing: dict[str, Counter[str]] = defaultdict(Counter)
    artist_plays: Counter[str] = Counter()
    artist_seconds: Counter[str] = Counter()
    artist_tracks: dict[str, set[str]] = defaultdict(set)
    artist_last_date: dict[str, date] = {}
    track_plays: Counter[str] = Counter()
    track_last_date: dict[str, date] = {}
    track_display_by_vid: dict[str, str] = {}
    track_artist_low_by_vid: dict[str, str] = {}
    album_plays: Counter[tuple[str, str]] = Counter()
    daily_plays: Counter[date] = Counter()
    weekly_plays: Counter[str] = Counter()
    genre_plays: Counter[str] = Counter()
    era_plays: Counter[str] = Counter()

    for play_date, row in effective_rows:
        dur = _safe_duration(row.get("duration_seconds"))

        prev_plays = total_plays
        total_plays += 1
        for t in _crossed("catalog_plays", prev_plays, total_plays):
            _record_unlock(
                unlocked,
                newly_unlocked,
                key=f"catalog:plays:{t}",
                category="catalog_plays",
                entity="Library",
                threshold=t,
                unlock_date=play_date,
                backfill=backfill,
            )

        prev_hours = total_seconds // 3600
        total_seconds += dur
        curr_hours = total_seconds // 3600
        for t in _crossed("catalog_hours", prev_hours, curr_hours):
            _record_unlock(
                unlocked,
                newly_unlocked,
                key=f"catalog:hours:{t}",
                category="catalog_hours",
                entity="Library",
                threshold=t,
                unlock_date=play_date,
                backfill=backfill,
            )

        split_artists = clean_and_split_artists(row.get("artists"))
        for name in split_artists:
            low = name.lower()
            artist_casing[low][name] += 1
            if low not in unique_artists:
                prev_ua = len(unique_artists)
                unique_artists.add(low)
                for t in _crossed("catalog_artists", prev_ua, prev_ua + 1):
                    _record_unlock(
                        unlocked,
                        newly_unlocked,
                        key=f"catalog:artists:{t}",
                        category="catalog_artists",
                        entity="Library",
                        threshold=t,
                        unlock_date=play_date,
                        backfill=backfill,
                    )

        title = (row.get("title") or "").strip()
        vid = (row.get("videoId") or "").strip()
        artist_display = clean_artist_display(row.get("artists"))
        track_key = vid.lower() if vid else (f"title:{title.lower()}" if title else "")

        row_genres: set[str] = set()
        row_eras: set[str] = set()
        for name in split_artists:
            low = name.lower()
            if low in uploader_keys:
                continue
            tag_entry = effective_tags.get(low)
            if isinstance(tag_entry, dict):
                pg = str(tag_entry.get("primary_genre") or "")
                era = str(tag_entry.get("era") or "")
                if pg and pg not in ("Other", "Uploader / Channel"):
                    row_genres.add(pg)
                if era and era != "Unknown":
                    row_eras.add(era)
            canonical = artist_casing[low].most_common(1)[0][0]
            artist_last_date[low] = play_date

            prev_ap = artist_plays[low]
            artist_plays[low] = prev_ap + 1
            for t in _crossed("artist_plays", prev_ap, prev_ap + 1):
                _record_unlock(
                    unlocked,
                    newly_unlocked,
                    key=f"artist:{low}:plays:{t}",
                    category="artist_plays",
                    entity=canonical,
                    threshold=t,
                    unlock_date=play_date,
                    backfill=backfill,
                )

            prev_ah = artist_seconds[low] // 3600
            artist_seconds[low] += dur
            curr_ah = artist_seconds[low] // 3600
            for t in _crossed("artist_hours", prev_ah, curr_ah):
                _record_unlock(
                    unlocked,
                    newly_unlocked,
                    key=f"artist:{low}:hours:{t}",
                    category="artist_hours",
                    entity=canonical,
                    threshold=t,
                    unlock_date=play_date,
                    backfill=backfill,
                )

            if track_key and track_key not in artist_tracks[low]:
                prev_at = len(artist_tracks[low])
                artist_tracks[low].add(track_key)
                for t in _crossed("artist_tracks", prev_at, prev_at + 1):
                    _record_unlock(
                        unlocked,
                        newly_unlocked,
                        key=f"artist:{low}:tracks:{t}",
                        category="artist_tracks",
                        entity=canonical,
                        threshold=t,
                        unlock_date=play_date,
                        backfill=backfill,
                    )

        for g in row_genres:
            genre_plays[g] += 1
        for e in row_eras:
            era_plays[e] += 1

        if vid:
            label = f"{title} — {artist_display}" if title and artist_display else (title or vid)
            track_display_by_vid[vid] = label
            if split_artists:
                track_artist_low_by_vid[vid] = split_artists[0].lower()
            track_last_date[vid] = play_date
            prev_tp = track_plays[vid]
            track_plays[vid] = prev_tp + 1
            for t in _crossed("track_plays", prev_tp, prev_tp + 1):
                _record_unlock(
                    unlocked,
                    newly_unlocked,
                    key=f"track:{vid}:{t}",
                    category="track_plays",
                    entity=label,
                    threshold=t,
                    unlock_date=play_date,
                    backfill=backfill,
                )

        album = (row.get("album") or "").strip()
        if album and split_artists:
            p_low = split_artists[0].lower()
            if p_low not in uploader_keys:
                p_name = artist_casing[p_low].most_common(1)[0][0]
                alb_key = (album.lower(), p_low)
                alb_label = f"{album} — {p_name}"
                prev_albp = album_plays[alb_key]
                album_plays[alb_key] = prev_albp + 1
                for t in _crossed("album_plays", prev_albp, prev_albp + 1):
                    _record_unlock(
                        unlocked,
                        newly_unlocked,
                        key=f"album:{album.lower()}:{p_low}:{t}",
                        category="album_plays",
                        entity=alb_label,
                        threshold=t,
                        unlock_date=play_date,
                        backfill=backfill,
                    )

        daily_plays[play_date] += 1
        iso_year, iso_week, _ = play_date.isocalendar()
        weekly_plays[f"{iso_year}-W{iso_week:02d}"] += 1

    first_date = min(daily_plays).isoformat() if daily_plays else ""
    latest_date = max(daily_plays) if daily_plays else None
    ref_date = reference_date or latest_date or datetime.now(get_user_timezone()).date()

    current_streak, longest_streak, longest_end = _compute_streaks_and_unlock(
        daily_plays, ref_date, unlocked, newly_unlocked, backfill
    )

    if daily_plays:
        peak_day_d, peak_day_n = max(daily_plays.items(), key=lambda x: (x[1], x[0]))
        peak_day_date = peak_day_d.isoformat()
    else:
        peak_day_n, peak_day_date = 0, ""

    if weekly_plays:
        peak_week_lbl, peak_week_n = max(weekly_plays.items(), key=lambda x: (x[1], x[0]))
    else:
        peak_week_n, peak_week_lbl = 0, ""

    store["records"] = {
        "longest_streak_days": longest_streak,
        "longest_streak_end": longest_end,
        "peak_day_plays": peak_day_n,
        "peak_day_date": peak_day_date,
        "peak_week_plays": peak_week_n,
        "peak_week_label": peak_week_lbl,
    }
    store["meta"]["first_history_date"] = first_date
    store["meta"]["last_history_date"] = latest_date.isoformat() if latest_date else ""

    artist_display_by_low = {
        low: counter.most_common(1)[0][0] for low, counter in artist_casing.items()
    }
    total_hours = total_seconds // 3600
    almost_there = _build_almost_there(
        ref_date=ref_date,
        total_plays=total_plays,
        total_hours=total_hours,
        unique_artists_count=len(unique_artists),
        current_streak=current_streak,
        artist_plays=artist_plays,
        artist_tracks=artist_tracks,
        artist_last_date=artist_last_date,
        artist_display_by_low=artist_display_by_low,
        track_plays=track_plays,
        track_last_date=track_last_date,
        track_display_by_vid=track_display_by_vid,
        track_artist_low_by_vid=track_artist_low_by_vid,
        tags_map=effective_tags,
        genre_plays=genre_plays,
        era_plays=era_plays,
    )

    summary_stats = {
        "total_plays": total_plays,
        "total_hours": round(total_seconds / 3600, 1),
        "unique_artists": len(unique_artists),
        "current_streak_days": current_streak,
        "first_history_date": first_date,
    }
    return store, newly_unlocked, summary_stats, almost_there


def detect_obsessions(
    output_dir: str,
    reference_date: date | None = None,
    *,
    parsed_rows: list[tuple[date, dict[str, str]]] | None = None,
    tags_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Detects short-term obsession signals (7d track loops & album binges, 14d artist
    surges/breakouts/comebacks, and 14d vs 90d taste phases) with low-activity guards.
    """
    effective_rows = _load_parsed_history(output_dir) if parsed_rows is None else parsed_rows

    if not effective_rows:
        return {
            "window_14d_plays": 0,
            "tracks_on_repeat": [],
            "artist_signals": [],
            "album_binges": [],
            "taste_phases": [],
        }

    ref_date = reference_date or effective_rows[-1][0]
    d7_start = ref_date - timedelta(days=6)
    d14_start = ref_date - timedelta(days=13)
    d90_start = ref_date - timedelta(days=103)
    breakout_cutoff = ref_date - timedelta(days=30)

    tags_map = _load_artist_tags_map(output_dir) if tags_map is None else tags_map
    uploader_keys = _uploader_keys_from_tags(tags_map)

    window_14d_plays = 0
    prior_90d_total = 0

    first_seen_date: dict[str, date] = {}
    last_pre14d_date: dict[str, date] = {}
    last_pre14d_idx: dict[str, int] = {}
    pre14d_plays: Counter[str] = Counter()
    artist_casing: dict[str, Counter[str]] = defaultdict(Counter)

    plays_90d: Counter[str] = Counter()
    plays_14d: Counter[str] = Counter()
    tracks_14d: dict[str, set[str]] = defaultdict(set)
    first_14d_date: dict[str, date] = {}
    first_14d_idx: dict[str, int] = {}

    track_7d_plays: Counter[str] = Counter()
    track_7d_by_day: dict[str, Counter[date]] = defaultdict(Counter)
    track_7d_meta: dict[str, dict[str, str]] = {}

    album_7d_plays: Counter[tuple[str, str]] = Counter()
    album_7d_tracks: dict[tuple[str, str], set[str]] = defaultdict(set)
    album_7d_meta: dict[tuple[str, str], tuple[str, str]] = {}

    tag_14d_plays: Counter[tuple[str, str]] = Counter()
    tag_14d_artists: dict[tuple[str, str], set[str]] = defaultdict(set)
    tag_90d_plays: Counter[tuple[str, str]] = Counter()

    for idx, (play_date, row) in enumerate(effective_rows):
        if play_date > ref_date:
            continue

        title = (row.get("title") or "").strip()
        vid = (row.get("videoId") or "").strip()
        artist_display = clean_artist_display(row.get("artists"))
        split_artists = clean_and_split_artists(row.get("artists"))
        track_key = vid.lower() if vid else f"title:{title.lower()}|{artist_display.lower()}"

        in_7d = d7_start <= play_date <= ref_date
        in_14d = d14_start <= play_date <= ref_date
        in_90d = d90_start <= play_date < d14_start

        if in_14d:
            window_14d_plays += 1
        elif in_90d:
            prior_90d_total += 1

        if in_7d and (vid or title):
            track_7d_plays[track_key] += 1
            track_7d_by_day[track_key][play_date] += 1
            track_7d_meta[track_key] = {
                "title": title or vid,
                "artist": artist_display or "Unknown",
                "url": ytm_watch_url(vid),
            }

            album = (row.get("album") or "").strip()
            if album and split_artists:
                p_low = split_artists[0].lower()
                if p_low not in uploader_keys:
                    alb_key = (album.lower(), p_low)
                    album_7d_plays[alb_key] += 1
                    album_7d_tracks[alb_key].add(track_key)
                    album_7d_meta[alb_key] = (album, split_artists[0])

        row_tags_14d: dict[tuple[str, str], set[str]] = defaultdict(set)
        row_tags_90d: set[tuple[str, str]] = set()

        for name in split_artists:
            low = name.lower()
            artist_casing[low][name] += 1
            if low in uploader_keys:
                continue

            first_seen_date.setdefault(low, play_date)
            if play_date < d14_start:
                pre14d_plays[low] += 1
                last_pre14d_date[low] = play_date
                last_pre14d_idx[low] = idx
            if in_90d:
                plays_90d[low] += 1
            if in_14d:
                plays_14d[low] += 1
                tracks_14d[low].add(track_key)
                first_14d_date.setdefault(low, play_date)
                first_14d_idx.setdefault(low, idx)

            tag_entry = tags_map.get(low)
            if isinstance(tag_entry, dict) and (in_14d or in_90d):
                pg = str(tag_entry.get("primary_genre") or "")
                era = str(tag_entry.get("era") or "")
                candidates: list[tuple[str, str]] = []
                if pg and pg not in ("Other", "Uploader / Channel"):
                    candidates.append(("genre", pg))
                if era and era != "Unknown":
                    candidates.append(("era", era))
                for sg in tag_entry.get("subgenres") or []:
                    if sg:
                        candidates.append(("subgenre", str(sg)))
                for tag_k in candidates:
                    if in_14d:
                        row_tags_14d[tag_k].add(low)
                    else:
                        row_tags_90d.add(tag_k)

        for tag_k, matched_lows in row_tags_14d.items():
            tag_14d_plays[tag_k] += 1
            tag_14d_artists[tag_k].update(matched_lows)
        for tag_k in row_tags_90d:
            tag_90d_plays[tag_k] += 1

    tracks_on_repeat: list[dict[str, Any]] = []
    for t_key, cnt in track_7d_plays.items():
        peak_day = max(track_7d_by_day[t_key].values())
        if cnt >= 4 or peak_day >= 3:
            meta = track_7d_meta[t_key]
            tracks_on_repeat.append(
                {
                    "title": meta["title"],
                    "artist": meta["artist"],
                    "url": meta["url"],
                    "plays_7d": cnt,
                    "peak_day": peak_day,
                }
            )
    tracks_on_repeat.sort(key=lambda x: (-x["plays_7d"], -x["peak_day"], x["title"].lower()))
    tracks_on_repeat = tracks_on_repeat[:5]

    artist_signals: list[dict[str, Any]] = []
    for low, p14 in plays_14d.items():
        u14 = len(tracks_14d[low])
        canonical = artist_casing[low].most_common(1)[0][0]
        if first_seen_date[low] >= breakout_cutoff and (p14 >= 10 or u14 >= 5):
            artist_signals.append(
                {
                    "artist": canonical,
                    "signal": "BREAKOUT",
                    "plays_14d": p14,
                    "unique_tracks_14d": u14,
                    "context": "First 30d",
                }
            )
            continue

        if low in last_pre14d_date:
            gap_days = (first_14d_date[low] - last_pre14d_date[low]).days
            other_plays_in_gap = first_14d_idx[low] - last_pre14d_idx[low] - 1
            if (
                pre14d_plays[low] >= 20
                and gap_days >= 90
                and other_plays_in_gap >= 100
                and p14 >= 6
            ):
                artist_signals.append(
                    {
                        "artist": canonical,
                        "signal": "COMEBACK",
                        "plays_14d": p14,
                        "unique_tracks_14d": u14,
                        "context": f"{gap_days}d gap",
                    }
                )
                continue

        if p14 >= 8 and u14 >= 3:
            expected_14d = plays_90d[low] * (14.0 / 90.0)
            lift = (p14 + 1.0) / (expected_14d + 2.0)
            if lift >= 2.5:
                ctx = f"{lift:.1f}x vs 90d" if prior_90d_total >= 50 else f"{u14} tracks / 14d"
                artist_signals.append(
                    {
                        "artist": canonical,
                        "signal": "SURGE",
                        "plays_14d": p14,
                        "unique_tracks_14d": u14,
                        "context": ctx,
                    }
                )

    artist_signals.sort(
        key=lambda x: (-x["plays_14d"], -x["unique_tracks_14d"], x["artist"].lower())
    )
    artist_signals = artist_signals[:6]

    album_binges: list[dict[str, Any]] = []
    for alb_key, cnt in album_7d_plays.items():
        u7 = len(album_7d_tracks[alb_key])
        if u7 >= 5 or cnt >= 10:
            alb_name, artist_name = album_7d_meta[alb_key]
            album_binges.append(
                {
                    "album": alb_name,
                    "artist": artist_name,
                    "plays_7d": cnt,
                    "unique_tracks_7d": u7,
                }
            )
    album_binges.sort(key=lambda x: (-x["plays_7d"], -x["unique_tracks_7d"], x["album"].lower()))
    album_binges = album_binges[:3]

    taste_phases: list[dict[str, Any]] = []
    if window_14d_plays >= 25 and prior_90d_total >= 50:
        for (kind, label), cnt14 in tag_14d_plays.items():
            if cnt14 < 10 or len(tag_14d_artists[(kind, label)]) < 2:
                continue
            share_14d = cnt14 / window_14d_plays
            share_90d = tag_90d_plays[(kind, label)] / prior_90d_total
            ratio = share_14d / max(share_90d, 0.005)
            if ratio >= 2.0:
                taste_phases.append(
                    {
                        "kind": kind,
                        "label": label,
                        "plays_14d": cnt14,
                        "lift": round(ratio, 1),
                    }
                )
        taste_phases.sort(key=lambda x: (-x["lift"], -x["plays_14d"], x["label"].lower()))
        taste_phases = taste_phases[:4]

    return {
        "window_14d_plays": window_14d_plays,
        "tracks_on_repeat": tracks_on_repeat,
        "artist_signals": artist_signals,
        "album_binges": album_binges,
        "taste_phases": taste_phases,
    }


def _escape_cell(text: str) -> str:
    return str(text).replace("|", "\\|")


def _ascii_bar(ratio: float, width: int = 10) -> str:
    filled = max(0, min(width, round(ratio * width)))
    if ratio < 1.0 and filled >= width:
        filled = width - 1
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def _format_milestone_text(entry: dict[str, Any]) -> str:
    cat = entry.get("category", "")
    entity = _escape_cell(str(entry.get("entity", "")))
    threshold = int(entry.get("threshold") or 0)
    templates = {
        "catalog_plays": f"**{threshold:,}** total plays",
        "catalog_hours": f"**{threshold:,}** listening hours",
        "catalog_artists": f"**{threshold:,}** unique artists",
        "artist_plays": f"**{entity}** — {threshold:,} plays",
        "artist_hours": f"**{entity}** — {threshold:,} hours",
        "artist_tracks": f"**{entity}** — {threshold:,} unique tracks",
        "track_plays": f"**{entity}** — {threshold:,} plays",
        "album_plays": f"**{entity}** — {threshold:,} plays",
        "streak_days": f"**{threshold:,}** consecutive days",
    }
    return templates.get(cat, f"**{entity}** — {threshold:,}")


def format_milestone_summary(entry: dict[str, Any]) -> tuple[str, str]:
    """Returns `(category_code, markdown_text)` for a milestone entry."""
    code = _CATEGORY_CODE.get(str(entry.get("category") or ""), "MILESTONE")
    return code, _format_milestone_text(entry)


def select_email_almost_there(
    almost_there: list[dict[str, Any]],
    max_hot: int = 2,
    max_wild: int = 1,
) -> list[dict[str, Any]]:
    """Picks up to `max_hot` HOT targets and `max_wild` wildcard targets for email footer."""
    hot = [item for item in almost_there if item.get("tag") == "HOT"][:max_hot]
    wild = [item for item in almost_there if item.get("tag") != "HOT"][:max_wild]
    selected = hot + wild
    total_cap = max_hot + max_wild
    if len(selected) < total_cap:
        seen = {id(x) for x in selected}
        for item in almost_there:
            if id(item) in seen:
                continue
            selected.append(item)
            if len(selected) >= total_cap:
                break
    return selected


def format_major_milestone_subject_tag(milestones: list[dict[str, Any]]) -> str:
    """Returns a concise bracketed subject tag for major catalog or >=30d streak milestones."""
    if not milestones:
        return ""
    priorities = (
        ("catalog_hours", lambda t: f"[{t:,}h]", 1),
        ("catalog_plays", lambda t: f"[{t:,} plays]", 1),
        ("streak_days", lambda t: f"[{t:,}d Streak]", 30),
        ("catalog_artists", lambda t: f"[{t:,} artists]", 1),
    )
    for cat, fmt, min_val in priorities:
        matching = [
            int(m.get("threshold") or 0)
            for m in milestones
            if m.get("category") == cat and int(m.get("threshold") or 0) >= min_val
        ]
        if matching:
            return fmt(max(matching))
    return ""


def render_milestones_markdown(
    store: dict[str, Any],
    summary_stats: dict[str, Any],
    almost_there: list[dict[str, Any]],
    obsessions: dict[str, Any],
    updated_date: str,
) -> str:
    """Renders `output/MILESTONES.md` in minimal/brutalist GitHub Flavored Markdown."""
    unlocked = store.get("unlocked") or {}
    records = store.get("records") or {}

    lines: list[str] = [
        "# Milestones & Obsessions",
        "",
        "[<- README](README.md)",
        "",
        (
            f"`Updated: {updated_date}` | "
            f"`Plays: {summary_stats['total_plays']:,}` | "
            f"`Hours: {summary_stats['total_hours']:,.1f}h` | "
            f"`Artists: {summary_stats['unique_artists']:,}` | "
            f"`Unlocked: {len(unlocked):,}`"
        ),
        "",
        "---",
        "",
        "## Current Obsessions (14d)",
        "",
    ]

    tracks_rep = obsessions.get("tracks_on_repeat") or []
    artist_sigs = obsessions.get("artist_signals") or []
    album_binges = obsessions.get("album_binges") or []
    taste_phases = obsessions.get("taste_phases") or []

    if not (tracks_rep or artist_sigs or album_binges or taste_phases):
        lines.append(
            f"Quiet stretch ({obsessions.get('window_14d_plays', 0)} plays / 14d). "
            "No active obsessions."
        )
        lines.append("")
    else:
        if tracks_rep:
            lines.extend(
                [
                    "### Tracks on Repeat (7d)",
                    "| Track | Artist | 7d Plays | Peak Day |",
                    "|---|---|---:|---:|",
                ]
            )
            for item in tracks_rep:
                t_title = _escape_cell(item["title"]).replace("[", "(").replace("]", ")")
                t_cell = f"[{t_title}]({item['url']})" if item.get("url") else t_title
                lines.append(
                    f"| {t_cell} | {_escape_cell(item['artist'])} | "
                    f"{item['plays_7d']} | {item['peak_day']} |"
                )
            lines.append("")

        if artist_sigs:
            lines.extend(
                [
                    "### Artist Signals (14d)",
                    "| Artist | Type | 14d Plays | Tracks | Context |",
                    "|---|---|---:|---:|---|",
                ]
            )
            for item in artist_sigs:
                lines.append(
                    f"| {_escape_cell(item['artist'])} | `{item['signal']}` | "
                    f"{item['plays_14d']} | {item['unique_tracks_14d']} | {item['context']} |"
                )
            lines.append("")

        if album_binges or taste_phases:
            lines.append("### Album Binges & Taste Phases")
            for alb in album_binges:
                lines.append(
                    f"- `ALBUM` **{_escape_cell(alb['album'])}** — "
                    f"{_escape_cell(alb['artist'])} ({alb['plays_7d']} plays, "
                    f"{alb['unique_tracks_7d']} tracks / 7d)"
                )
            if taste_phases:
                phase_parts = " · ".join(
                    f"**{_escape_cell(p['label'])}** ({p['lift']:.1f}x baseline, "
                    f"{p['plays_14d']} plays)"
                    for p in taste_phases
                )
                lines.append(f"- `PHASE` {phase_parts}")
            lines.append("")

    if almost_there:
        lines.extend(
            [
                "---",
                "",
                "## Almost There",
                "",
                "| Target | Tag | Progress | Remaining |",
                "|---|---|---|---:|",
            ]
        )
        for item in almost_there:
            bar = _ascii_bar(item["ratio"])
            tag = item.get("tag", "HOT")
            lines.append(
                f"| {_escape_cell(item['label'])} | `{tag}` | `{bar} {item['progress']}` | "
                f"{item['remaining_display']} |"
            )
        lines.append("")

    lines.extend(["---", "", "## Recent Milestones", ""])
    if unlocked:
        sorted_ms = sorted(
            unlocked.values(),
            key=lambda x: (
                x.get("date", ""),
                int(x.get("threshold") or 0),
                str(x.get("entity", "")),
            ),
            reverse=True,
        )[:30]
        lines.extend(["| Date | Type | Milestone |", "|---|---|---|"])
        for entry in sorted_ms:
            code = _CATEGORY_CODE.get(entry.get("category", ""), "MILESTONE")
            lines.append(f"| {entry['date']} | `{code}` | {_format_milestone_text(entry)} |")
    else:
        lines.append("No milestones unlocked yet.")
    lines.append("")

    streak_end = records.get("longest_streak_end") or "-"
    streak_note = f"Ended {streak_end}" if records.get("longest_streak_days") else "-"
    first_date = str(summary_stats.get("first_history_date") or "").strip()
    period_note = f"Since {first_date[:7]}" if len(first_date) >= 7 else "Recorded"
    lines.extend(
        [
            "---",
            "",
            "## Recorded Totals & Peaks",
            "",
            "| Metric | Value | Date / Period |",
            "|---|---:|---|",
            f"| Total Plays | {summary_stats['total_plays']:,} | {period_note} |",
            f"| Total Hours | {summary_stats['total_hours']:,.1f}h | {period_note} |",
            f"| Unique Artists | {summary_stats['unique_artists']:,} | {period_note} |",
            f"| Longest Streak | {records.get('longest_streak_days', 0):,} days | {streak_note} |",
            (
                f"| Peak Day | {records.get('peak_day_plays', 0):,} plays | "
                f"{records.get('peak_day_date') or '-'} |"
            ),
            (
                f"| Peak Week | {records.get('peak_week_plays', 0):,} plays | "
                f"{records.get('peak_week_label') or '-'} |"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def get_period_milestones(
    output_dir: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Returns non-backfilled milestones crossed within [start_date, end_date]."""
    store = read_milestones(os.path.join(output_dir, "meta", "milestones.yaml"))
    start_iso = start_date.isoformat()
    end_iso = end_date.isoformat()
    matched = [
        entry
        for entry in (store.get("unlocked") or {}).values()
        if not entry.get("backfilled") and start_iso <= str(entry.get("date", "")) <= end_iso
    ]
    matched.sort(
        key=lambda x: (x.get("date", ""), int(x.get("threshold") or 0), str(x.get("entity", ""))),
        reverse=True,
    )
    return matched[:6]


def sync_milestones(
    output_dir: str = "output",
    backfill: bool = False,
    reference_date: date | None = None,
    now_dt: datetime | None = None,
) -> dict[str, Any]:
    """Evaluates milestones + obsessions and updates `milestones.yaml` and `MILESTONES.md` when changed."""
    meta_path = os.path.join(output_dir, "meta", "milestones.yaml")
    prev_exists = os.path.isfile(meta_path)
    prev_store = read_milestones(meta_path)
    prev_unlocked = dict(prev_store["unlocked"])
    prev_records = dict(prev_store["records"])
    prev_last_date = prev_store["meta"].get("last_history_date", "")

    parsed_rows = _load_parsed_history(output_dir)
    tags_map = _load_artist_tags_map(output_dir)

    store, newly_unlocked, summary_stats, almost_there = evaluate_milestones(
        output_dir=output_dir,
        reference_date=reference_date,
        backfill=backfill,
        parsed_rows=parsed_rows,
        tags_map=tags_map,
    )
    obs_ref = reference_date
    if obs_ref is None and store["meta"].get("last_history_date"):
        obs_ref = date.fromisoformat(store["meta"]["last_history_date"])
    obsessions = detect_obsessions(
        output_dir=output_dir,
        reference_date=obs_ref,
        parsed_rows=parsed_rows,
        tags_map=tags_map,
    )

    effective_now = now_dt or datetime.now(UTC)
    updated_date = (reference_date or effective_now.date()).isoformat()

    yaml_changed = (
        not prev_exists
        or store["unlocked"] != prev_unlocked
        or store["records"] != prev_records
        or store["meta"].get("last_history_date", "") != prev_last_date
    )
    if yaml_changed:
        write_milestones(meta_path, store, now_dt=effective_now)

    md = render_milestones_markdown(
        store=store,
        summary_stats=summary_stats,
        almost_there=almost_there,
        obsessions=obsessions,
        updated_date=updated_date,
    )
    md_path = os.path.join(output_dir, "MILESTONES.md")
    existing_md = ""
    if os.path.isfile(md_path):
        with open(md_path, encoding="utf-8") as f:
            existing_md = f.read()
    if md != existing_md:
        _atomic_write_text(md_path, md)

    obsessions_count = sum(
        len(obsessions[k])
        for k in ("tracks_on_repeat", "artist_signals", "album_binges", "taste_phases")
    )
    return {
        "newly_unlocked": len(newly_unlocked),
        "total_unlocked": len(store["unlocked"]),
        "obsessions_count": obsessions_count,
    }


def run_milestones_cli(argv: list[str] | None = None) -> dict[str, Any]:
    """CLI entrypoint for `python ytm-dl.py milestones`."""
    parser = argparse.ArgumentParser(prog="ytm-dl.py milestones")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--backfill", action="store_true")
    args = parser.parse_args(argv)

    res = sync_milestones(output_dir=args.output_dir, backfill=args.backfill)
    mode = "backfill" if args.backfill else "sync"
    print(
        f"Milestones {mode} complete: +{res['newly_unlocked']} newly unlocked, "
        f"{res['total_unlocked']} total unlocked, {res['obsessions_count']} active obsession(s)."
    )
    return res
