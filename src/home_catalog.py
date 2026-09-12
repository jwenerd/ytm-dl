import concurrent.futures
import os
from datetime import UTC, datetime

from ytmusicapi.continuations import get_continuations
from ytmusicapi.navigation import SECTION_LIST, SINGLE_COLUMN_TAB, nav
from ytmusicapi.parsers.browsing import (
    MMRIR,
    MRLIR,
    MTRIR,
    NAVIGATION_BROWSE,
    NAVIGATION_WATCH_PLAYLIST_ID,
    PAGE_TYPE,
    TITLE,
    parse_album,
    parse_episode,
    parse_playlist,
    parse_podcast,
    parse_related_artist,
    parse_song,
    parse_song_flat,
    parse_watch_playlist,
)

from .api import get_thread_client
from .catalog import (
    merge_catalog_items,
    read_catalog,
    write_catalog_csv,
    write_catalog_yaml,
)
from .mapping import ExtractNameStr, HomeCatalogItemSchema, get_run_id
from .util import output_path, slugify


def parse_home_item(result: dict) -> dict | None:
    """Parses a single recommendation item renderer from carousel/grid contents."""
    data = nav(result, [MTRIR], True)
    if data:
        page_type = nav(data, TITLE + NAVIGATION_BROWSE + PAGE_TYPE, True)
        try:
            if page_type is None:
                if nav(data, NAVIGATION_WATCH_PLAYLIST_ID, True) is not None:
                    return parse_watch_playlist(data)
                else:
                    return parse_song(data)
            elif page_type in ["MUSIC_PAGE_TYPE_ALBUM", "MUSIC_PAGE_TYPE_AUDIOBOOK"]:
                return parse_album(data)
            elif page_type in ["MUSIC_PAGE_TYPE_ARTIST", "MUSIC_PAGE_TYPE_USER_CHANNEL"]:
                return parse_related_artist(data)
            elif page_type == "MUSIC_PAGE_TYPE_PLAYLIST":
                return parse_playlist(data)
            elif page_type == "MUSIC_PAGE_TYPE_PODCAST_SHOW_DETAIL_PAGE":
                return parse_podcast(data)
        except Exception:
            pass

        # Fallback extraction
        title_runs = nav(data, ["title", "runs"], True) or []
        title = (
            "".join(r.get("text", "") for r in title_runs)
            or nav(data, ["title", "simpleText"], True)
            or ""
        )
        subtitle_runs = nav(data, ["subtitle", "runs"], True) or []
        subtitle = "".join(r.get("text", "") for r in subtitle_runs)

        watch_ep = nav(data, ["navigationEndpoint", "watchEndpoint"], True) or {}
        browse_ep = nav(data, ["navigationEndpoint", "browseEndpoint"], True) or {}

        return {
            "title": title,
            "description": subtitle,
            "videoId": watch_ep.get("videoId"),
            "playlistId": watch_ep.get("playlistId"),
            "browseId": browse_ep.get("browseId"),
        }

    elif data := nav(result, [MRLIR], True):
        try:
            return parse_song_flat(data)
        except Exception:
            pass
    elif data := nav(result, [MMRIR], True):
        try:
            return parse_episode(data)
        except Exception:
            pass

    return None


def fetch_rich_home_sections(client, limit: int = 50) -> list[dict]:
    """
    Fetches the home browse endpoint and continuations, extracting:
    - Shelf title, strapline, thumbnail, browse_id, and item_size
    - All parsed recommendation items
    """
    endpoint = "browse"
    body = {"browseId": "FEmusic_home"}
    response = client._send_request(endpoint, body)

    raw_sections = list(nav(response, SINGLE_COLUMN_TAB + SECTION_LIST, True) or [])
    section_list = nav(response, [*SINGLE_COLUMN_TAB, "sectionListRenderer"], True) or {}

    if "continuations" in section_list:

        def request_func(additionalParams):
            return client._send_request(endpoint, body, additionalParams)

        cont_sections = get_continuations(
            section_list, "sectionListContinuation", limit, request_func, lambda c: c
        )
        raw_sections.extend(cont_sections)

    parsed_sections = []
    seen_titles = set()

    for sec in raw_sections:
        for k in [
            "musicCarouselShelfRenderer",
            "musicImmersiveCarouselShelfRenderer",
            "gridRenderer",
        ]:
            if k in sec:
                shelf = sec[k]
                hdr = shelf.get("header", {})
                b_hdr = (
                    hdr.get("musicCarouselShelfBasicHeaderRenderer", {})
                    or hdr.get("gridHeaderRenderer", {})
                    or hdr.get("musicImmersiveCarouselShelfHeaderRenderer", {})
                )

                title_runs = b_hdr.get("title", {}).get("runs", [])
                title = "".join(r.get("text", "") for r in title_runs)

                strapline_runs = b_hdr.get("strapline", {}).get("runs", [])
                strapline = (
                    "".join(r.get("text", "") for r in strapline_runs) if strapline_runs else None
                )

                if not title:
                    if strapline:
                        title = strapline
                        strapline = None
                    else:
                        continue

                # Skip duplicate shelves in the same feed snapshot
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                # Thumbnail
                thumb_renderer = b_hdr.get("thumbnail", {}).get("musicThumbnailRenderer", {})
                thumbnails = (
                    thumb_renderer.get("thumbnail", {}).get("thumbnails", [])
                    if thumb_renderer
                    else []
                )
                thumbnail = thumbnails[-1].get("url") if thumbnails else None

                # Browse ID / Navigation
                title_nav = title_runs[0].get("navigationEndpoint", {}) if title_runs else {}
                browse_id = title_nav.get("browseEndpoint", {}).get("browseId")

                # Sizing
                item_size = shelf.get("itemSize")

                # Parse items
                contents = []
                for res in shelf.get("contents", []):
                    item = parse_home_item(res)
                    if item:
                        contents.append(item)

                if contents:
                    parsed_sections.append(
                        {
                            "title": title,
                            "strapline": strapline,
                            "browse_id": browse_id,
                            "thumbnail": thumbnail,
                            "item_size": item_size,
                            "contents": contents,
                        }
                    )

    return parsed_sections


def _resolve_item_id(item: dict) -> str:
    """Resolves primary ID from videoId, playlistId, browseId, or podcastId."""
    if item.get("id"):
        return item["id"]
    if item.get("videoId"):
        return item["videoId"]
    if item.get("playlistId"):
        p_id = item["playlistId"]
        if p_id.startswith("VL"):
            p_id = p_id[2:]
        return p_id
    if item.get("browseId"):
        return item["browseId"]
    if item.get("podcastId"):
        return item["podcastId"]
    return ""


def _resolve_item_type(item: dict) -> str:
    """Deduces entity type (Song, Playlist, Album, Single, Artist, Podcast, Video)."""
    explicit_type = item.get("type")
    if explicit_type:
        return explicit_type

    if item.get("videoId"):
        return "Song" if not item.get("videoType") else "Video"
    if item.get("playlistId"):
        return "Playlist"
    if item.get("podcastId"):
        return "Podcast"
    if item.get("subscribers"):
        return "Artist"
    if item.get("browseId"):
        b_id = item["browseId"]
        if b_id.startswith("MPRE") or b_id.startswith("FEmusic_library_privately_owned_release"):
            return "Album"
        if b_id.startswith("UC"):
            return "Artist"
    return "Unknown"


def _make_home_item_row(item: dict, pos: int, captured_at: str) -> dict:
    """Constructs a row dictionary for a newly discovered home recommendation."""
    extractor = ExtractNameStr()
    item_id = _resolve_item_id(item)
    item_type = _resolve_item_type(item)
    title = item.get("title", "")

    # Extract artists/creators
    artists_raw = item.get("artists") or item.get("channel") or item.get("author") or []
    if isinstance(artists_raw, dict):
        artists_raw = [artists_raw]
    artists = extractor._serialize(artists_raw, None, None) or ""

    # Extract description / subtitle
    desc = item.get("description", "")
    if not desc and item.get("subtitle"):
        desc = item["subtitle"]

    return {
        "id": item_id,
        "type": item_type,
        "title": title,
        "artists": artists,
        "description": desc,
        "first_seen": captured_at,
        "last_seen": captured_at,
        "times_recommended": "1",
        "latest_position": str(pos),
    }


def _update_home_item_row(row: dict, item: dict) -> None:
    """Updates non-destructive metadata fields in-place for returning items."""
    extractor = ExtractNameStr()
    if not row.get("description"):
        desc = item.get("description", "")
        if not desc and item.get("subtitle"):
            desc = item["subtitle"]
        if desc:
            row["description"] = desc

    if not row.get("artists"):
        artists_raw = item.get("artists") or item.get("channel") or item.get("author") or []
        if isinstance(artists_raw, dict):
            artists_raw = [artists_raw]
        artists = extractor._serialize(artists_raw, None, None) or ""
        if artists:
            row["artists"] = artists

    if row.get("type") in ["", "Unknown"]:
        resolved = _resolve_item_type(item)
        if resolved != "Unknown":
            row["type"] = resolved


def sync_home_shelf(
    shelf: dict,
    output_base_dir: str,
    run_time: datetime,
    run_id: str,
) -> dict:
    """Merges a single home shelf into its continuous catalog files (<slug>.csv and .yaml)."""
    title = shelf["title"]
    slug = slugify(title)
    if not slug:
        slug = "home_recommendations"

    csv_path = os.path.join(output_base_dir, f"{slug}.csv")
    yaml_path = os.path.join(output_base_dir, f"{slug}.yaml")
    captured_at = run_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    existing_rows, existing_lookup = read_catalog(csv_path, key_field="id")
    raw_contents = shelf.get("contents", [])

    # Deduplicate within incoming batch while preserving order
    seen_in_batch = set()
    deduped_items = []
    for it in raw_contents:
        i_id = _resolve_item_id(it)
        if i_id and i_id not in seen_in_batch:
            it["id"] = i_id
            seen_in_batch.add(i_id)
            deduped_items.append(it)

    merged_items, new_count, updated_count = merge_catalog_items(
        existing_rows=existing_rows,
        existing_lookup=existing_lookup,
        new_items=deduped_items,
        key_field="id",
        now_iso=captured_at,
        make_new_row_fn=_make_home_item_row,
        update_existing_fn=_update_home_item_row,
    )

    schema = HomeCatalogItemSchema()
    write_catalog_csv(csv_path, schema.keys, merged_items)

    metadata = {
        "title": title,
        "strapline": shelf.get("strapline"),
        "slug": slug,
        "browse_id": shelf.get("browse_id"),
        "thumbnail": shelf.get("thumbnail"),
        "item_size": shelf.get("item_size"),
        "total_items": len(merged_items),
        "new_items_latest_run": new_count,
        "latest_batch_size": len(raw_contents),
        "first_captured": captured_at,
        "last_captured": captured_at,
        "run_id": run_id,
    }

    write_catalog_yaml(yaml_path, metadata)

    return {
        "title": title,
        "slug": slug,
        "total_items": len(merged_items),
        "new_items": new_count,
        "updated_items": updated_count,
        "batch_size": len(raw_contents),
    }


def sync_all_home_shelves(
    output_base_dir: str | None = None,
    max_workers: int = 8,
    run_time: datetime | None = None,
    run_id: str | None = None,
) -> list[dict]:
    """
    Main entrypoint for Home recommendations:
    Discovers all active Home shelves, merges into continuous living libraries in output/home/,
    and writes companion YAML metadata.
    """
    if output_base_dir is None:
        output_base_dir = output_path("home")

    if run_time is None:
        run_time = datetime.now(UTC)
    run_id = get_run_id(run_time, run_id)

    client = get_thread_client()

    print("🔍 Discovering active Home feed shelves...")
    shelves = fetch_rich_home_sections(client, limit=50)
    print(f"Discovered {len(shelves)} Home shelves.")

    if not shelves:
        print("No Home shelves found.")
        return []

    print(
        f"🚀 Merging {len(shelves)} Home shelves into living catalogs (concurrency: {max_workers})..."
    )

    def worker(shelf_info):
        try:
            return sync_home_shelf(
                shelf_info,
                output_base_dir=output_base_dir,
                run_time=run_time,
                run_id=run_id,
            )
        except Exception as e:
            print(f"Error syncing Home shelf '{shelf_info.get('title')}': {e}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(worker, shelves))

    results = [r for r in results if r is not None]

    total_new = sum(r["new_items"] for r in results)
    print(
        f"✅ Synced {len(results)} Home shelf catalogs (+{total_new} new unique recommendations discovered)."
    )

    for r in results:
        slug = r["slug"]
        new_cnt = r["new_items"]
        upd_cnt = r["updated_items"]
        tot = r["total_items"]
        if new_cnt > 0:
            print(f"🏠 Home: ✨ [{slug}] +{new_cnt} new, {upd_cnt} updated ({tot} total)")
        else:
            print(f"🏠 Home: ☕ [{slug}] {upd_cnt} updated ({tot} total)")

    return results
