"""Self-updating rolling YouTube Music playlist sync for Daily Radar picks."""

import logging
import re
from typing import Any

from src.api import get_thread_client

logger = logging.getLogger(__name__)

DEFAULT_PLAYLIST_TITLE = "⚡ Daily Radar (ytm-dl)"
ROLLING_PLAYLIST_LIMIT = 25

_WATCH_ID_RE = re.compile(r"https://music\.youtube\.com/watch\?v=([A-Za-z0-9_-]+)")
_ALBUM_ID_RE = re.compile(r"https://music\.youtube\.com/browse/(MPREb_[A-Za-z0-9_-]+)")
_LONG_FORM_LINE_RE = re.compile(
    r"^(?:[-*]\s*)?\*\*(?:Long Spin|Full Album):?\*\*:?",
    re.IGNORECASE,
)


def extract_playlist_video_ids(
    md_content: str,
    context: dict[str, Any],
    max_new: int = 6,
) -> list[str]:
    """
    Extracts song videoIds featured in the Today's Radar and Liked & Forgotten sections.
    Excludes Long Spin full-set videos and Full Album links, falling back to top candidates.
    """
    long_set_ids = {
        s["id"]
        for s in ((context.get("long_form_picks") or {}).get("long_sets") or [])
        if s.get("id")
    }

    in_pick_section = False
    found_ids: list[str] = []

    for line in md_content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("## Today's Radar", "## Radar Picks")):
            in_pick_section = True
            continue
        if in_pick_section and _LONG_FORM_LINE_RE.match(stripped):
            continue
        if in_pick_section:
            for match in _WATCH_ID_RE.findall(stripped):
                if match not in long_set_ids and match not in found_ids:
                    found_ids.append(match)
                    if len(found_ids) >= max_new:
                        return found_ids

    if not found_ids:
        for cand in (context.get("radar_candidates") or [])[:4]:
            vid = cand.get("id")
            if vid and vid not in found_ids:
                found_ids.append(vid)
        for fg in (context.get("forgotten_candidates") or [])[:1]:
            vid = fg.get("id")
            if vid and vid not in found_ids:
                found_ids.append(vid)

    return found_ids[:max_new]


def extract_featured_entity_ids(md_content: str, playlist_ids: list[str]) -> list[str]:
    """
    Collects all featured IDs (Radar songs, Liked & Forgotten, Full Album browseId,
    and Long Spin videoId) from the report so multi-day deduplication rotates albums and sets too.
    """
    featured = list(playlist_ids)
    in_pick_section = False
    for line in md_content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("## Today's Radar", "## Radar Picks")):
            in_pick_section = True
            continue
        if in_pick_section:
            for vid in _WATCH_ID_RE.findall(stripped):
                if vid not in featured:
                    featured.append(vid)
            for aid in _ALBUM_ID_RE.findall(stripped):
                if aid not in featured:
                    featured.append(aid)
    return featured


def inject_playlist_banner(md_content: str, playlist_url: str) -> str:
    """Inserts or updates the clickable Rolling Daily Radar playlist banner below the header."""
    if not playlist_url:
        return md_content

    banner = f"**[▶ Play Rolling Daily Radar Playlist]({playlist_url})**"
    lines = [ln for ln in md_content.splitlines() if "Play Rolling Daily Radar Playlist" not in ln]

    insert_idx = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("# "):
            insert_idx = i + 1
        elif i <= 2 and s.startswith("*") and s.endswith("*"):
            insert_idx = i + 1
            break

    lines.insert(insert_idx, "")
    lines.insert(insert_idx + 1, banner)

    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines).strip())
    return cleaned + "\n"


def _find_existing_playlist_id(client: Any, title: str = DEFAULT_PLAYLIST_TITLE) -> str | None:
    """Searches the user's YTM library playlists for an existing Daily Radar playlist by title."""
    playlists = client.get_library_playlists(limit=50) or []
    for pl in playlists:
        if pl.get("title") == title and pl.get("playlistId"):
            return str(pl["playlistId"]).strip()
    return None


def sync_daily_radar_playlist(
    video_ids: list[str],
    period_label: str,
    meta: dict[str, Any],
    client: Any = None,
    max_tracks: int = ROLLING_PLAYLIST_LIMIT,
) -> str | None:
    """
    Creates or updates the rolling ~25-track private YouTube Music Daily Radar playlist.
    - Short-circuits destructive writes when `desired_ids == existing_ids`.
    - Replaces same-period picks cleanly on nocturnal refreshes instead of double-appending.
    - Persists `video_ids` in `meta["playlist"]` as crash-recovery state.
    """
    existing_url = (meta.get("playlist") or {}).get("url")
    if not video_ids:
        return existing_url

    if client is None:
        try:
            client = get_thread_client()
        except Exception as e:
            logger.info("Skipping Daily Radar playlist sync (no active YTM auth): %s", e)
            return None

    playlist_meta = meta.get("playlist") or {}
    playlist_id = playlist_meta.get("daily_radar_id")
    description = f"Rolling {max_tracks}-track crate curated by ytm-dl • Updated {period_label}"
    deduped_new = list(dict.fromkeys(video_ids))

    try:
        if not playlist_id:
            playlist_id = _find_existing_playlist_id(client, DEFAULT_PLAYLIST_TITLE)

        if not playlist_id:
            initial_ids = deduped_new[:max_tracks]
            created = client.create_playlist(
                title=DEFAULT_PLAYLIST_TITLE,
                description=description,
                privacy_status="PRIVATE",
                video_ids=initial_ids,
            )
            if not isinstance(created, str) or not created.strip():
                logger.warning("Unexpected create_playlist response: %s", created)
                return None
            playlist_id = created.strip()
            url = f"https://music.youtube.com/playlist?list={playlist_id}"
            meta["playlist"] = {
                "daily_radar_id": playlist_id,
                "url": url,
                "updated_period": period_label,
                "track_count": len(initial_ids),
                "video_ids": initial_ids,
                "last_period_ids": deduped_new,
            }
            return url

        pl = client.get_playlist(playlist_id, limit=max_tracks + 50)
        existing_tracks = pl.get("tracks") or []
        existing_ids = [t["videoId"] for t in existing_tracks if t.get("videoId")]

        # Merge persisted backup IDs in case a prior run failed mid-update
        backup_ids = playlist_meta.get("video_ids") or []
        prior_pool = list(dict.fromkeys(existing_ids + backup_ids))

        # On nocturnal refresh of the same period, replace earlier same-day picks instead of stacking
        if playlist_meta.get("updated_period") == period_label:
            same_day_prev = set(playlist_meta.get("last_period_ids") or [])
            prior_pool = [vid for vid in prior_pool if vid not in same_day_prev]

        desired_ids = list(dict.fromkeys(deduped_new + prior_pool))[:max_tracks]

        if desired_ids != existing_ids:
            removable = [t for t in existing_tracks if t.get("videoId") and t.get("setVideoId")]
            if removable:
                client.remove_playlist_items(playlist_id, removable)
            client.add_playlist_items(playlist_id, videoIds=desired_ids, duplicates=False)
            client.edit_playlist(playlist_id, description=description)

        url = f"https://music.youtube.com/playlist?list={playlist_id}"
        meta["playlist"] = {
            "daily_radar_id": playlist_id,
            "url": url,
            "updated_period": period_label,
            "track_count": len(desired_ids),
            "video_ids": desired_ids,
            "last_period_ids": deduped_new,
        }
        return url
    except Exception as e:
        logger.warning("Failed to sync Daily Radar playlist (%s): %s", playlist_id, e)
        return existing_url
