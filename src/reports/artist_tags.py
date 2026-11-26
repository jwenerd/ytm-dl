"""Incremental Artist Genre, Era & Country enricher (`output/meta/artist_tags.yaml`)."""

import argparse
import json
import logging
import os
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import requests
import yaml

from src.reports.generator import GEMINI_API_URL, get_google_ai_api_key
from src.reports.telemetry import clean_and_split_artists, read_csv_rows

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_MIN_PLAYS = 5
DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_ARTISTS_PER_RUN = 150

CANONICAL_GENRES = (
    "Jazz",
    "Rock",
    "Jam Band",
    "Folk & Bluegrass",
    "Country & Americana",
    "Electronic & Downtempo",
    "Ambient",
    "Soul & R&B",
    "Funk",
    "Hip-Hop",
    "World & Latin",
    "Reggae & Dub",
    "Classical",
    "Blues",
    "Metal",
    "Pop",
    "Soundtrack",
    "Uploader / Channel",
    "Other",
)
_CANONICAL_GENRE_BY_LOWER = {g.lower(): g for g in CANONICAL_GENRES}

_TAG_RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING"},
            "primary_genre": {"type": "STRING", "enum": list(CANONICAL_GENRES)},
            "subgenres": {"type": "ARRAY", "items": {"type": "STRING"}},
            "era": {"type": "STRING"},
            "country": {"type": "STRING"},
            "moods": {"type": "ARRAY", "items": {"type": "STRING"}},
            "is_uploader": {"type": "BOOLEAN"},
        },
        "required": [
            "name",
            "primary_genre",
            "subgenres",
            "era",
            "country",
            "moods",
            "is_uploader",
        ],
    },
}


def _default_store() -> dict[str, Any]:
    return {
        "meta": {"schema_version": SCHEMA_VERSION, "updated_at": "", "total_tagged": 0},
        "artists": {},
    }


def read_artist_tags(meta_path: str) -> dict[str, Any]:
    """Reads `output/meta/artist_tags.yaml` or returns an initialized store."""
    if not os.path.isfile(meta_path):
        return _default_store()
    try:
        with open(meta_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return _default_store()
        artists = data.get("artists")
        meta = data.get("meta")
        return {
            "meta": dict(meta) if isinstance(meta, dict) else _default_store()["meta"],
            "artists": dict(artists) if isinstance(artists, dict) else {},
        }
    except (OSError, yaml.YAMLError) as e:
        logger.warning("Could not read artist tags from %s: %s", meta_path, e)
        return _default_store()


def write_artist_tags(
    meta_path: str,
    store: dict[str, Any],
    now_dt: datetime | None = None,
) -> None:
    """Persists `output/meta/artist_tags.yaml` with updated summary metadata."""
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    ts = (now_dt or datetime.now(UTC)).isoformat()
    artists = store.get("artists") or {}
    payload = {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "updated_at": ts,
            "total_tagged": len(artists),
        },
        "artists": artists,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=True, indent=2, allow_unicode=True)


def collect_catalog_artists(
    output_dir: str,
    min_plays: int = DEFAULT_MIN_PLAYS,
) -> list[tuple[str, str, int]]:
    """
    Scans `history.csv`, splits & cleans artist names, and returns
    `(lower_key, canonical_name, play_count)` for artists with `play_count >= min_plays`,
    sorted highest play-count first.
    """
    rows = read_csv_rows(os.path.join(output_dir, "history.csv"))
    counts: Counter[str] = Counter()
    canonical_by_lower: dict[str, str] = {}

    for row in rows:
        for name in clean_and_split_artists(row.get("artists")):
            low = name.lower()
            canonical_by_lower.setdefault(low, name)
            counts[low] += 1

    qualifying = [
        (low, canonical_by_lower[low], count) for low, count in counts.items() if count >= min_plays
    ]
    qualifying.sort(key=lambda item: (-item[2], item[1].lower()))
    return qualifying


def _build_batch_prompt(artist_names: list[str]) -> str:
    names_json = json.dumps(artist_names, ensure_ascii=False)
    return (
        "Classify each music artist, band, composer, or YouTube channel below.\n"
        "Rules:\n"
        "- Echo the exact input string in `name`.\n"
        "- `primary_genre`: choose the single best fit from the allowed enum.\n"
        "- `subgenres`: 1 to 3 specific genres/styles (e.g. 'Ethio-jazz', 'Krautrock', 'Bluegrass').\n"
        "- `era`: primary active/signature decade such as '1970s', '1990s', '2010s', or 'Unknown'.\n"
        "- `country`: ISO-3166 alpha-2 country code (e.g. 'US', 'GB', 'ET', 'JP', 'CO') or 'Unknown'.\n"
        "- `moods`: 1 to 3 concise lowercase mood descriptors (e.g. 'hypnotic', 'acoustic', 'groove').\n"
        "- `is_uploader`: true ONLY if the name is a YouTube taper, channel, DJ archive, or uploader "
        "rather than a musical artist (e.g. 'Le Mellotron', 'Max Berde', 'Cercle'); use "
        "`primary_genre: 'Uploader / Channel'` when true.\n"
        f"\nArtists JSON:\n{names_json}"
    )


def _normalize_tag_record(item: dict[str, Any]) -> dict[str, Any]:
    raw_genre = str(item.get("primary_genre") or "").strip()
    primary_genre = _CANONICAL_GENRE_BY_LOWER.get(raw_genre.lower(), "Other")
    subgenres = [str(s).strip() for s in (item.get("subgenres") or []) if str(s).strip()][:3]
    moods = [str(m).strip().lower() for m in (item.get("moods") or []) if str(m).strip()][:3]
    era = str(item.get("era") or "Unknown").strip() or "Unknown"
    country = str(item.get("country") or "Unknown").strip() or "Unknown"
    return {
        "name": str(item.get("name") or "").strip(),
        "primary_genre": primary_genre,
        "subgenres": subgenres,
        "era": era,
        "country": country,
        "moods": moods,
        "is_uploader": bool(item.get("is_uploader", False)),
    }


def fetch_artist_tags_batch(
    artist_names: list[str],
    api_key: str,
    timeout: int = 60,
    max_retries: int = 2,
) -> list[dict[str, Any]]:
    """Queries Gemini Flash with structured JSON schema to classify a batch of artists."""
    if not artist_names or not api_key:
        return []

    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"parts": [{"text": _build_batch_prompt(artist_names)}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
            "responseSchema": _TAG_RESPONSE_SCHEMA,
        },
    }

    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                time.sleep(min(2 ** (attempt + 1), 8))
                continue
            resp.raise_for_status()
            data = resp.json()
            parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            if not parts or "text" not in parts[0]:
                return []
            parsed = json.loads(parts[0]["text"])
            if not isinstance(parsed, list):
                return []
            return [_normalize_tag_record(item) for item in parsed if isinstance(item, dict)]
        except (
            requests.RequestException,
            json.JSONDecodeError,
            ValueError,
            KeyError,
            IndexError,
        ) as e:
            if (
                isinstance(e, (requests.RequestException, json.JSONDecodeError))
                and attempt < max_retries
            ):
                time.sleep(min(2 ** (attempt + 1), 8))
                continue
            logger.warning("Gemini artist tagging batch failed: %s", e)
            return []
    return []  # pragma: no cover


def enrich_artist_tags(
    output_dir: str = "output",
    min_plays: int = DEFAULT_MIN_PLAYS,
    max_artists: int | None = DEFAULT_MAX_ARTISTS_PER_RUN,
    batch_size: int = DEFAULT_BATCH_SIZE,
    api_key: str | None = None,
    delay_seconds: float = 0.5,
    now_dt: datetime | None = None,
) -> dict[str, Any]:
    """
    Incrementally tags qualifying uncached artists into `output/meta/artist_tags.yaml`.
    Checkpoints YAML after every batch so large backfills are safely resumable.
    """
    if api_key is None:
        api_key = get_google_ai_api_key()

    meta_path = os.path.join(output_dir, "meta", "artist_tags.yaml")
    store = read_artist_tags(meta_path)
    artists_map = store["artists"]

    qualifying = collect_catalog_artists(output_dir, min_plays=min_plays)
    uncached = [(low, name, count) for (low, name, count) in qualifying if low not in artists_map]

    if not uncached or not api_key:
        return {
            "tagged": 0,
            "remaining": len(uncached),
            "total_cached": len(artists_map),
        }

    targets = uncached if max_artists is None else uncached[:max_artists]
    tagged_date = (now_dt or datetime.now(UTC)).date().strftime("%Y-%m-%d")
    newly_tagged = 0
    total_batches = (len(targets) + batch_size - 1) // batch_size

    for batch_idx, start in enumerate(range(0, len(targets), batch_size), start=1):
        batch = targets[start : start + batch_size]
        names = [name for _, name, _ in batch]
        results = fetch_artist_tags_batch(names, api_key=api_key)
        by_lower = {r["name"].lower(): r for r in results if r.get("name")}

        batch_added = 0
        for low, canonical, _ in batch:
            tag = by_lower.get(low)
            if tag:
                artists_map[low] = {
                    "name": canonical,
                    "primary_genre": tag["primary_genre"],
                    "subgenres": tag["subgenres"],
                    "era": tag["era"],
                    "country": tag["country"],
                    "moods": tag["moods"],
                    "is_uploader": tag["is_uploader"],
                    "source": "gemini",
                    "tagged_at": tagged_date,
                }
                newly_tagged += 1
                batch_added += 1

        if batch_added > 0:
            write_artist_tags(meta_path, store, now_dt=now_dt)

        print(
            f"  [artist_tags] Batch {batch_idx}/{total_batches}: "
            f"tagged {batch_added}/{len(batch)} (cached: {len(artists_map)})"
        )
        if delay_seconds > 0 and batch_idx < total_batches:
            time.sleep(delay_seconds)

    return {
        "tagged": newly_tagged,
        "remaining": max(0, len(uncached) - newly_tagged),
        "total_cached": len(artists_map),
    }


def run_enrich_cli(argv: list[str] | None = None) -> dict[str, Any]:
    """CLI entrypoint for `python ytm-dl.py enrich`."""
    parser = argparse.ArgumentParser(prog="ytm-dl.py enrich")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--min-plays", type=int, default=DEFAULT_MIN_PLAYS)
    parser.add_argument("--limit", type=int, default=DEFAULT_MAX_ARTISTS_PER_RUN)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--all", action="store_true", dest="run_all")
    args = parser.parse_args(argv)

    max_artists = None if args.run_all else args.limit
    res = enrich_artist_tags(
        output_dir=args.output_dir,
        min_plays=args.min_plays,
        max_artists=max_artists,
        batch_size=args.batch_size,
    )
    print(
        f"✓ Artist tags sync complete: +{res['tagged']} tagged, "
        f"{res['remaining']} remaining, {res['total_cached']} total cached."
    )
    return res
