import concurrent.futures
import csv
import os
import re
from datetime import UTC, datetime

import yaml
from ytmusicapi.navigation import SECTION_LIST, SINGLE_COLUMN_TAB, nav

from .api import get_thread_client
from .mapping import ExtractNameStr, MoodMixTrackSchema, get_run_id
from .util import file_exists, output_path, write_file

CORE_HOME_MIX_TITLES = {
    "my supermix",
    "discover mix",
    "new release mix",
    "replay mix",
    "archive mix",
}


def slugify(text: str) -> str:
    """Converts display names to clean snake_case filenames."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def is_supermix_or_core_mix(title: str) -> bool:
    """Returns True if the title belongs to a Supermix or Core Home Mix."""
    cleaned = title.strip().lower()
    if "supermix" in cleaned:
        return True
    if cleaned in CORE_HOME_MIX_TITLES:
        return True
    return False


def discover_mood_chips(client) -> list[tuple[str, str]]:
    """Extracts active mood chips (Relax, Focus, Energize, etc.) from home feed."""
    raw = client._send_request("browse", {"browseId": "FEmusic_home"})
    chips = []
    try:
        header_chips = (
            raw.get("contents", {})
            .get("singleColumnBrowseResultsRenderer", {})
            .get("tabs", [{}])[0]
            .get("tabRenderer", {})
            .get("content", {})
            .get("sectionListRenderer", {})
            .get("header", {})
            .get("chipCloudRenderer", {})
            .get("chips", [])
        )
        for item in header_chips:
            cr = item.get("chipCloudChipRenderer", {})
            text = cr.get("text", {}).get("runs", [{}])[0].get("text")
            params = cr.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("params")
            if text and params and text != "Podcasts":
                chips.append((text, params))
    except Exception as e:
        print(f"Warning: Failed to parse mood chips: {e}")
    return chips


def discover_chip_supermixes(client, chip_name: str, chip_params: str) -> list[dict]:
    """Finds the Supermix in 'Mixed for you' section under a specific mood chip."""
    supermixes = []
    try:
        chip_raw = client._send_request(
            "browse", {"browseId": "FEmusic_home", "params": chip_params}
        )
        section_list = nav(chip_raw, SINGLE_COLUMN_TAB + SECTION_LIST)
        for sec in section_list:
            for key in [
                "musicCarouselShelfRenderer",
                "musicImmersiveCarouselShelfRenderer",
                "gridRenderer",
            ]:
                if key in sec:
                    header = sec[key].get("header", {})
                    title_runs = (
                        header.get("musicCarouselShelfBasicHeaderRenderer", {})
                        .get("title", {})
                        .get("runs", [])
                    )
                    if not title_runs:
                        title_runs = (
                            header.get("gridHeaderRenderer", {}).get("title", {}).get("runs", [])
                        )
                    sec_title = "".join([r.get("text", "") for r in title_runs])
                    if sec_title == "Mixed for you":
                        for item in sec[key].get("contents", []):
                            for r_type in [
                                "musicTwoRowItemRenderer",
                                "musicResponsiveListItemRenderer",
                            ]:
                                if r_type in item:
                                    rend = item[r_type]
                                    t = "".join(
                                        [
                                            r.get("text", "")
                                            for r in rend.get("title", {}).get("runs", [])
                                        ]
                                    )
                                    sub = "".join(
                                        [
                                            r.get("text", "")
                                            for r in rend.get("subtitle", {}).get("runs", [])
                                        ]
                                    )
                                    nav_ep = rend.get("navigationEndpoint", {})
                                    b_ep = nav_ep.get("browseEndpoint", {})
                                    w_ep = nav_ep.get("watchEndpoint", {})
                                    p_id = w_ep.get("playlistId") or b_ep.get("browseId")
                                    if p_id and p_id.startswith("VL"):
                                        p_id = p_id[2:]
                                    if p_id and is_supermix_or_core_mix(t):
                                        supermixes.append(
                                            {
                                                "title": t,
                                                "mood_chip": chip_name,
                                                "playlist_id": p_id,
                                                "featured_artists": sub,
                                            }
                                        )
    except Exception as e:
        print(f"Warning: Failed to discover mixes for chip '{chip_name}': {e}")
    return supermixes


def discover_home_core_mixes(client) -> list[dict]:
    """Finds My Supermix and core algorithmic mixes (Discover, Replay, etc.) on Home."""
    home_mixes = []
    try:
        home_sections = client.get_home(limit=25)
        for sec in home_sections:
            sec_title = sec.get("title", "")
            if sec_title in ["Mixed for you", "Fresh finds, old favorites"]:
                for item in sec.get("contents", []):
                    title = item.get("title", "")
                    p_id = item.get("playlistId") or item.get("browseId")
                    if p_id and p_id.startswith("VL"):
                        p_id = p_id[2:]
                    if p_id and is_supermix_or_core_mix(title):
                        desc = item.get("description", "")
                        home_mixes.append(
                            {
                                "title": title,
                                "mood_chip": "Home",
                                "playlist_id": p_id,
                                "featured_artists": desc,
                            }
                        )
    except Exception as e:
        print(f"Warning: Failed to discover home mixes: {e}")
    return home_mixes


def discover_all_supermixes(client) -> list[dict]:
    """Scans all mood chips and home feed to build master list of Supermixes & Core Mixes."""
    all_mixes = []
    seen_ids = set()

    # 1. Home mixes
    for mix in discover_home_core_mixes(client):
        pid = mix["playlist_id"]
        if pid not in seen_ids:
            seen_ids.add(pid)
            all_mixes.append(mix)

    # 2. Mood Chip supermixes
    chips = discover_mood_chips(client)
    for chip_name, chip_params in chips:
        for mix in discover_chip_supermixes(client, chip_name, chip_params):
            pid = mix["playlist_id"]
            if pid not in seen_ids:
                seen_ids.add(pid)
                all_mixes.append(mix)

    return all_mixes


def read_existing_catalog(csv_path: str) -> tuple[list[dict], dict[str, dict]]:
    """Reads existing catalog CSV into a list of ordered rows and a dict keyed by videoId."""
    rows = []
    lookup = {}
    if not file_exists(csv_path):
        return rows, lookup

    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                vid = row.get("videoId")
                if vid:
                    row_dict = dict(row)
                    rows.append(row_dict)
                    lookup[vid] = row_dict
    except Exception as e:
        print(f"Warning: Failed to read existing catalog at {csv_path}: {e}")
    return rows, lookup


def merge_catalog_tracks(
    existing_rows: list[dict],
    existing_lookup: dict[str, dict],
    new_tracks: list[dict],
    captured_at: str,
) -> tuple[list[dict], int, int]:
    """
    Merges newly fetched tracks into existing cumulative catalog:
    - Brand new songs are prepended at the top.
    - Existing songs stay in their exact row positions and update in-place.
    Returns: (final_ordered_rows, new_count, updated_count)
    """
    extractor = ExtractNameStr()
    new_rows = []
    new_count = 0
    updated_count = 0
    seen_in_new_batch = set()

    for idx, t in enumerate(new_tracks):
        vid = t.get("videoId")
        if not vid or vid in seen_in_new_batch:
            continue
        seen_in_new_batch.add(vid)

        pos = idx + 1
        title = t.get("title", "")
        artists = extractor._serialize(t.get("artists", []), None, None) or ""
        album = extractor._serialize(t.get("album", {}), None, None) or ""
        duration = t.get("duration", "")
        duration_sec = t.get("duration_seconds") or 0
        like_status = t.get("likeStatus", "INDIFFERENT")
        in_library = str(t.get("inLibrary", False))

        if vid in existing_lookup:
            # Update existing track in-place
            row = existing_lookup[vid]
            row["last_seen"] = captured_at
            row["times_recommended"] = str(int(row.get("times_recommended") or 1) + 1)
            row["latest_position"] = str(pos)
            row["likeStatus"] = like_status
            row["inLibrary"] = in_library
            if duration and not row.get("duration"):
                row["duration"] = duration
                row["duration_seconds"] = str(duration_sec)
            if album and not row.get("album"):
                row["album"] = album
            updated_count += 1
        else:
            # Prepend new track at the top
            new_row = {
                "videoId": vid,
                "title": title,
                "artists": artists,
                "album": album,
                "duration": duration,
                "duration_seconds": str(duration_sec),
                "first_seen": captured_at,
                "last_seen": captured_at,
                "times_recommended": "1",
                "latest_position": str(pos),
                "likeStatus": like_status,
                "inLibrary": in_library,
            }
            new_rows.append(new_row)
            new_count += 1

    final_rows = new_rows + existing_rows
    return final_rows, new_count, updated_count


def fetch_and_merge_mix(
    mix_info: dict,
    output_base_dir: str = "output/mixes",
    limit: int = 400,
    run_time: datetime | None = None,
    run_id: str | None = None,
) -> dict:
    """Fetches playlist tracks, merges with cumulative catalog, and writes files."""
    client = get_thread_client()
    playlist_id = mix_info["playlist_id"]
    if run_time is None:
        run_time = datetime.now(UTC)
    run_id = get_run_id(run_time, run_id)
    captured_at = run_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    res = client.get_playlist(playlist_id, limit=limit)
    raw_tracks = res.get("tracks", [])

    mix_slug = slugify(mix_info.get("title", playlist_id))
    csv_path = os.path.join(output_base_dir, f"{mix_slug}.csv")
    yaml_path = os.path.join(output_base_dir, f"{mix_slug}.yaml")

    existing_rows, existing_lookup = read_existing_catalog(csv_path)
    merged_tracks, new_count, updated_count = merge_catalog_tracks(
        existing_rows, existing_lookup, raw_tracks, captured_at
    )

    schema = MoodMixTrackSchema()
    columns = schema.keys

    # Write CSV
    os.makedirs(output_base_dir, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for track in merged_tracks:
            writer.writerow({col: track.get(col, "") for col in columns})

    author = res.get("author")
    if isinstance(author, dict):
        author = author.get("name")

    metadata = {
        "title": res.get("title") or mix_info.get("title", ""),
        "mood_chip": mix_info.get("mood_chip", ""),
        "playlist_id": playlist_id,
        "description": res.get("description") or "",
        "featured_artists": mix_info.get("featured_artists", ""),
        "author": author or "YouTube Music",
        "year": str(res.get("year", "")),
        "total_unique_tracks": len(merged_tracks),
        "new_tracks_latest_run": new_count,
        "latest_batch_size": len(raw_tracks),
        "last_updated": captured_at,
        "run_id": run_id,
    }

    write_file(yaml_path, yaml.dump(metadata, sort_keys=False))

    return {
        "title": metadata["title"],
        "mix_slug": mix_slug,
        "total_tracks": len(merged_tracks),
        "new_tracks": new_count,
        "batch_size": len(raw_tracks),
    }


def sync_all_mood_mixes(
    output_base_dir: str | None = None,
    max_workers: int = 8,
    run_time: datetime | None = None,
    run_id: str | None = None,
) -> list[dict]:
    """
    Main entry point: Discovers, fetches in parallel, and merges all Supermixes & Core Home Mixes.
    """
    if output_base_dir is None:
        output_base_dir = output_path("mixes")

    if run_time is None:
        run_time = datetime.now(UTC)

    client = get_thread_client()

    print("🔍 Discovering Supermixes and Core Home Mixes...")
    all_mixes = discover_all_supermixes(client)
    print(f"Discovered {len(all_mixes)} Supermixes & Core Mixes.")

    if not all_mixes:
        print("No mixes found to sync.")
        return []

    print(f"🚀 Fetching & merging {len(all_mixes)} mixes (concurrency: {max_workers})...")

    def worker(mix_info):
        try:
            return fetch_and_merge_mix(
                mix_info,
                output_base_dir=output_base_dir,
                limit=400,
                run_time=run_time,
                run_id=run_id,
            )
        except Exception as e:
            print(f"Error syncing {mix_info.get('title')}: {e}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(worker, all_mixes))

    results = [r for r in results if r is not None]

    total_new = sum(r["new_tracks"] for r in results)
    print(f"✅ Synced {len(results)} mix catalogs (+{total_new} new unique songs discovered).")
    return results
