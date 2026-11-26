"""Incremental Artist Genre, Era & Country enricher (`output/meta/artist_tags.yaml`)."""

import argparse
import json
import logging
import os
import re
import time
import unicodedata
from collections import Counter, defaultdict
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
MAX_CONSECUTIVE_FAILURES = 3

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
    """Persists `output/meta/artist_tags.yaml` atomically with updated summary metadata."""
    parent = os.path.dirname(meta_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
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
    tmp_path = f"{meta_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=True, indent=2, allow_unicode=True)
    os.replace(tmp_path, meta_path)


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
    casing_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for row in rows:
        for name in clean_and_split_artists(row.get("artists")):
            low = name.lower()
            counts[low] += 1
            casing_counts[low][name] += 1

    qualifying = [
        (low, casing_counts[low].most_common(1)[0][0], count)
        for low, count in counts.items()
        if count >= min_plays
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


def _normalize_country(raw: Any) -> str:
    code = str(raw or "").strip().upper()
    if code == "UK":
        return "GB"
    if len(code) == 2 and code.isalpha():
        return code
    return "Unknown"


def _dedupe_str_list(values: Any, *, lower: bool = False, limit: int = 3) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for val in values or []:
        cleaned = str(val).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(key if lower else cleaned)
        if len(result) >= limit:
            break
    return result


def _normalize_artist_key(name: str) -> str:
    cleaned = unicodedata.normalize("NFKC", name).lower()
    cleaned = re.sub(r"[\u2018\u2019\u201b`´]", "'", cleaned)
    cleaned = re.sub(r"[\u2010-\u2015\u2212]", "-", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_tag_record(item: dict[str, Any]) -> dict[str, Any]:
    raw_genre = str(item.get("primary_genre") or "").strip()
    primary_genre = _CANONICAL_GENRE_BY_LOWER.get(raw_genre.lower(), "Other")
    subgenres = _dedupe_str_list(item.get("subgenres"), lower=False, limit=3)
    moods = _dedupe_str_list(item.get("moods"), lower=True, limit=3)
    era = str(item.get("era") or "Unknown").strip() or "Unknown"
    country = _normalize_country(item.get("country"))
    is_uploader = bool(item.get("is_uploader", False)) or primary_genre == "Uploader / Channel"
    if is_uploader:
        primary_genre = "Uploader / Channel"
    return {
        "name": str(item.get("name") or "").strip(),
        "primary_genre": primary_genre,
        "subgenres": subgenres,
        "era": era,
        "country": country,
        "moods": moods,
        "is_uploader": is_uploader,
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
        except requests.HTTPError as e:
            logger.warning("Gemini artist tagging HTTP error: %s", e)
            return []
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
    max_consecutive_failures: int = MAX_CONSECUTIVE_FAILURES,
) -> dict[str, Any]:
    """
    Incrementally tags qualifying uncached artists into `output/meta/artist_tags.yaml`.
    Checkpoints YAML after every batch so large backfills are safely resumable.
    """
    if min_plays < 1:
        raise ValueError("min_plays must be >= 1")
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

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
    consecutive_failures = 0

    for batch_idx, start in enumerate(range(0, len(targets), batch_size), start=1):
        batch = targets[start : start + batch_size]
        names = [name for _, name, _ in batch]
        results = fetch_artist_tags_batch(names, api_key=api_key)
        by_lower = {r["name"].lower(): r for r in results if r.get("name")}
        by_norm = {_normalize_artist_key(r["name"]): r for r in results if r.get("name")}

        batch_added = 0
        unmatched: list[str] = []
        for low, canonical, _ in batch:
            tag = by_lower.get(low) or by_norm.get(_normalize_artist_key(canonical))
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
            else:
                unmatched.append(canonical)

        if results and unmatched:
            logger.warning(
                "[artist_tags] Batch %d/%d missed %d artist(s): %s",
                batch_idx,
                total_batches,
                len(unmatched),
                ", ".join(unmatched[:5]),
            )

        if batch_added > 0:
            write_artist_tags(meta_path, store, now_dt=now_dt)

        print(
            f"  [artist_tags] Batch {batch_idx}/{total_batches}: "
            f"tagged {batch_added}/{len(batch)} (cached: {len(artists_map)})"
        )

        if not results:
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures:
                logger.warning(
                    "Aborting artist_tags enrichment after %d consecutive failed batches.",
                    consecutive_failures,
                )
                break
        else:
            consecutive_failures = 0

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

    if args.min_plays < 1:
        parser.error("--min-plays must be >= 1")
    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1")
    if not args.run_all and args.limit < 1:
        parser.error("--limit must be >= 1")

    api_key = get_google_ai_api_key()
    max_artists = None if args.run_all else args.limit
    res = enrich_artist_tags(
        output_dir=args.output_dir,
        min_plays=args.min_plays,
        max_artists=max_artists,
        batch_size=args.batch_size,
        api_key=api_key or "",
    )
    if not api_key and res["remaining"] > 0:
        print(
            f"⚠ GOOGLE_AI_API_KEY not set: skipped {res['remaining']} uncached artist(s) "
            f"({res['total_cached']} total cached)."
        )
        return res
    print(
        f"✓ Artist tags sync complete: +{res['tagged']} tagged, "
        f"{res['remaining']} remaining, {res['total_cached']} total cached."
    )
    return res
