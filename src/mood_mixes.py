import concurrent.futures
import csv
import hashlib
import os
import re
from datetime import UTC, datetime, timedelta

import yaml
from ytmusicapi.navigation import SECTION_LIST, SINGLE_COLUMN_TAB, nav

from .api import get_thread_client
from .mapping import MoodMixTrackSchema, get_run_id
from .util import file_exists, output_path, write_file


def slugify(text: str) -> str:
    """Converts display names to clean snake_case filenames/folder names."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def get_week_archive_folder(run_time: datetime | None = None) -> str:
    """
    Returns the YYYY_MM_DD string for the Monday (start) of the ISO week.
    Example: 2026-09-12 (Saturday) -> '2026_09_08' (Monday)
    """
    if run_time is None:
        run_time = datetime.now(UTC)
    ref_date = run_time.date() if isinstance(run_time, datetime) else run_time
    monday = ref_date - timedelta(days=ref_date.weekday())
    return monday.strftime("%Y_%m_%d")


def compute_tracklist_hash(tracks: list[dict]) -> str:
    """Computes SHA-256 hash of ordered videoIds for change detection."""
    video_ids = [t.get("videoId", "") for t in tracks if isinstance(t, dict)]
    return hashlib.sha256(",".join(video_ids).encode("utf-8")).hexdigest()


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


def discover_chip_mixes(client, chip_name: str, chip_params: str) -> list[dict]:
    """Finds all mixes in 'Mixed for you' section under a specific mood chip."""
    mixes = []
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
                                    if p_id:
                                        mixes.append(
                                            {
                                                "title": t,
                                                "mood_chip": chip_name,
                                                "playlist_id": p_id,
                                                "featured_artists": sub,
                                            }
                                        )
    except Exception as e:
        print(f"Warning: Failed to discover mixes for chip '{chip_name}': {e}")
    return mixes


def discover_home_mixes(client) -> list[dict]:
    """Finds My Supermix and algorithmic mixes (Discover, Replay, etc.) on Home."""
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
                    if p_id and (
                        "mix" in title.lower()
                        or "supermix" in title.lower()
                        or sec_title == "Mixed for you"
                    ):
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


def discover_all_mixes(client) -> list[dict]:
    """Scans all mood chips and home feed to build master list of mixes."""
    all_mixes = []
    seen_ids = set()

    # 1. Home mixes
    for mix in discover_home_mixes(client):
        pid = mix["playlist_id"]
        if pid not in seen_ids:
            seen_ids.add(pid)
            all_mixes.append(mix)

    # 2. Mood Chip mixes
    chips = discover_mood_chips(client)
    for chip_name, chip_params in chips:
        for mix in discover_chip_mixes(client, chip_name, chip_params):
            pid = mix["playlist_id"]
            if pid not in seen_ids:
                seen_ids.add(pid)
                all_mixes.append(mix)

    return all_mixes


def fetch_and_format_mix(mix_info: dict, limit: int = 300, run_time=None, run_id=None) -> dict:
    """Fetches playlist tracks and formats metadata for a single mix."""
    client = get_thread_client()
    playlist_id = mix_info["playlist_id"]
    if run_time is None:
        run_time = datetime.now(UTC)
    run_id = get_run_id(run_time, run_id)
    captured_at = run_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    res = client.get_playlist(playlist_id, limit=limit)
    raw_tracks = res.get("tracks", [])

    # Enrich tracks with position index
    enriched_tracks = []
    for idx, t in enumerate(raw_tracks):
        track_copy = dict(t)
        track_copy["position"] = idx + 1
        enriched_tracks.append(track_copy)

    # Serialize tracks using schema
    schema = MoodMixTrackSchema()
    dumped_tracks = schema.dump(enriched_tracks, many=True)
    columns = schema.keys
    track_rows = [[row.get(col, "") for col in columns] for row in dumped_tracks]

    author = res.get("author")
    if isinstance(author, dict):
        author = author.get("name")

    content_hash = compute_tracklist_hash(raw_tracks)

    metadata = {
        "title": res.get("title") or mix_info.get("title", ""),
        "mood_chip": mix_info.get("mood_chip", ""),
        "playlist_id": playlist_id,
        "description": res.get("description") or "",
        "featured_artists": mix_info.get("featured_artists", ""),
        "author": author or "YouTube Music",
        "year": str(res.get("year", "")),
        "track_count": len(raw_tracks),
        "content_hash": content_hash,
        "captured_at": captured_at,
        "run_id": run_id,
    }

    return {
        "metadata": metadata,
        "columns": columns,
        "rows": track_rows,
        "mood_slug": slugify(mix_info.get("mood_chip", "mixes")),
        "mix_slug": slugify(mix_info.get("title", playlist_id)),
    }


def write_mix_files(
    mix_data: dict, output_base_dir: str = "output/mixes", week_folder: str | None = None
) -> dict:
    """
    Writes current/<mood>/<mix>.{csv,yaml} and history/<week>/<mood>/<mix>.{csv,yaml}
    with smart deduplication based on content hash.
    """
    metadata = mix_data["metadata"]
    columns = mix_data["columns"]
    rows = mix_data["rows"]
    mood_slug = mix_data["mood_slug"]
    mix_slug = mix_data["mix_slug"]

    # 1. Current files
    current_dir = os.path.join(output_base_dir, "current", mood_slug)
    os.makedirs(current_dir, exist_ok=True)
    current_csv = os.path.join(current_dir, f"{mix_slug}.csv")
    current_yaml = os.path.join(current_dir, f"{mix_slug}.yaml")

    with open(current_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=",", quoting=csv.QUOTE_MINIMAL)
        writer.writerows([columns] + rows)

    write_file(current_yaml, yaml.dump(metadata, sort_keys=False))

    # 2. History files (weekly snapshot)
    history_written = False
    if week_folder:
        history_dir = os.path.join(output_base_dir, "history", week_folder, mood_slug)
        history_csv = os.path.join(history_dir, f"{mix_slug}.csv")
        history_yaml = os.path.join(history_dir, f"{mix_slug}.yaml")

        if not file_exists(history_yaml):
            os.makedirs(history_dir, exist_ok=True)
            with open(history_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=",", quoting=csv.QUOTE_MINIMAL)
                writer.writerows([columns] + rows)
            write_file(history_yaml, yaml.dump(metadata, sort_keys=False))
            history_written = True

    return {
        "mix_slug": mix_slug,
        "mood_slug": mood_slug,
        "tracks": len(rows),
        "history_written": history_written,
    }


def sync_all_mood_mixes(
    output_base_dir: str | None = None,
    max_workers: int = 8,
    run_time: datetime | None = None,
    run_id: str | None = None,
) -> list[dict]:
    """
    Main entry point: Discovers, fetches in parallel, and saves all mood mixes and supermixes.
    """
    if output_base_dir is None:
        output_base_dir = output_path("mixes")

    if run_time is None:
        run_time = datetime.now(UTC)

    week_folder = get_week_archive_folder(run_time)
    client = get_thread_client()

    print("🔍 Discovering all Mood Chips and Mixes...")
    all_mixes = discover_all_mixes(client)
    print(f"Discovered {len(all_mixes)} total mixes across Home and Mood Chips.")

    if not all_mixes:
        print("No mixes found to sync.")
        return []

    print(f"🚀 Fetching tracks for {len(all_mixes)} mixes (concurrency: {max_workers})...")

    def worker(mix_info):
        try:
            return fetch_and_format_mix(mix_info, limit=300, run_time=run_time, run_id=run_id)
        except Exception as e:
            print(f"Error fetching {mix_info.get('title')}: {e}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(worker, all_mixes))

    results = [r for r in results if r is not None]

    history_count = 0
    for mix_data in results:
        res = write_mix_files(mix_data, output_base_dir=output_base_dir, week_folder=week_folder)
        if res.get("history_written"):
            history_count += 1

    print(
        f"✅ Synced {len(results)} mixes to current/ and archived {history_count} to history/{week_folder}/"
    )
    return results
