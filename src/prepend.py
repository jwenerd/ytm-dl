import csv
import difflib
import os


def get_existing_ids(csv_file, key_index=None, limit=float("inf")):
    """Read existing primary keys from a CSV file up to limit."""
    if not os.path.exists(csv_file):
        return []

    existing_ids = []
    with open(csv_file, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=",")
        header = next(reader, None)
        if header is None:
            return []

        if isinstance(key_index, str) and key_index in header:
            idx = header.index(key_index)
        elif key_index is not None and isinstance(key_index, int) and key_index < len(header):
            idx = key_index
        elif "videoId" in header:
            idx = header.index("videoId")
        elif "browseId" in header:
            idx = header.index("browseId")
        elif "id" in header:
            idx = header.index("id")
        else:
            idx = len(header) - 1

        for row in reader:
            if row and len(row) > idx:
                existing_ids.append(row[idx])
                if len(existing_ids) >= limit:
                    break
    return existing_ids


def find_history_overlap(existing_ids, new_ids, max_window=15, min_ratio=0.75):
    """
    Find the index in new_ids where the new plays meet existing history.
    Returns:
      int: 0 if no new plays, >0 if new plays exist, or None if no overlap detected.
    """
    if not existing_ids:
        return len(new_ids)

    # 1. Look for exact sequence matches
    for i in range(len(new_ids)):
        candidate = new_ids[i:]
        window = min(len(candidate), len(existing_ids), max_window)
        if window == 0:
            continue
        if candidate[:window] == existing_ids[:window]:
            return i

    # 2. Look for approximate match with sequence similarity (handles deletions/edits)
    best_i = None
    best_ratio = 0.0
    for i in range(len(new_ids)):
        candidate = new_ids[i:]
        window_cand = min(len(candidate), max_window)
        window_exist = min(len(existing_ids), max_window)
        if window_cand < 3 or window_exist < 3:
            continue

        matcher = difflib.SequenceMatcher(
            None, candidate[:window_cand], existing_ids[:window_exist]
        )
        ratio = matcher.ratio()
        if ratio >= min_ratio and ratio > best_ratio:
            best_ratio = ratio
            best_i = i

    if best_i is not None:
        return best_i

    return None


def prepend_rows_for_file(csv_file, new_rows, is_history=False, key_index=None, by_key=False):
    """
    Determine which rows from new_rows should be prepended to the CSV file.
    - If is_history: Uses sequence alignment to find new play events.
    - Else (collections/library/likes): Deduplicates by key, preserving new additions.
    """
    if not new_rows:
        return []

    # Default key_index to last column if not provided
    if key_index is None:
        key_index = len(new_rows[0]) - 1

    if is_history:
        existing_ids = get_existing_ids(csv_file, key_index=key_index, limit=200)
        if not existing_ids:
            return new_rows

        new_ids = [row[key_index] for row in new_rows if len(row) > key_index]
        start_index = find_history_overlap(existing_ids, new_ids)

        if start_index is None:
            print(f"Warning: No history overlap found with {csv_file}. Prepending all {len(new_rows)} rows.")
            return new_rows

        return new_rows[0:start_index]

    # For collections (liked_songs, library_*, etc.)
    existing_keys = set(get_existing_ids(csv_file, key_index=key_index))
    seen_in_batch = set()
    rows_to_add = []

    for row in new_rows:
        if len(row) > key_index:
            key = row[key_index]
            if key not in existing_keys and key not in seen_in_batch:
                seen_in_batch.add(key)
                rows_to_add.append(row)

    return rows_to_add
