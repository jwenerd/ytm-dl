import csv
import os

import yaml

from .util import create_directory, file_exists, write_file


def read_catalog(csv_path: str, key_field: str = "id") -> tuple[list[dict], dict[str, dict]]:
    """
    Reads an existing cumulative catalog CSV into:
    - An ordered list of row dictionaries (preserving file line order).
    - A lookup dictionary keyed by key_field for fast identity matching.
    """
    rows = []
    lookup = {}
    if not file_exists(csv_path):
        return rows, lookup

    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key_val = row.get(key_field)
                if key_val:
                    row_dict = dict(row)
                    rows.append(row_dict)
                    lookup[key_val] = row_dict
    except Exception as e:
        print(f"Warning: Failed to read existing catalog at {csv_path}: {e}")
    return rows, lookup


def merge_catalog_items(
    existing_rows: list[dict],
    existing_lookup: dict[str, dict],
    new_items: list[dict],
    key_field: str,
    now_iso: str,
    make_new_row_fn,
    update_existing_fn=None,
) -> tuple[list[dict], int, int]:
    """
    Merges newly fetched items into an existing cumulative catalog:
    - Existing items remain in their exact row positions and update in-place (Git diff stability).
    - Newly discovered items are prepended at the top of the file (index 0).
    - Returns: (final_ordered_rows, new_count, updated_count)
    """
    new_rows = []
    new_count = 0
    updated_count = 0

    for idx, item in enumerate(new_items):
        pos = idx + 1
        key_val = item.get(key_field)
        if not key_val:
            continue

        if key_val in existing_lookup:
            row = existing_lookup[key_val]
            row["last_seen"] = now_iso
            try:
                current_times = int(row.get("times_recommended") or 1)
            except (ValueError, TypeError):
                current_times = 1
            row["times_recommended"] = str(current_times + 1)
            row["latest_position"] = str(pos)

            if update_existing_fn:
                update_existing_fn(row, item)
            updated_count += 1
        else:
            new_row = make_new_row_fn(item, pos, now_iso)
            new_rows.append(new_row)
            existing_lookup[key_val] = new_row
            new_count += 1

    final_rows = new_rows + existing_rows
    return final_rows, new_count, updated_count


def write_catalog_csv(csv_path: str, columns: list[str], rows: list[dict]):
    """
    Atomically writes the catalog CSV file with specified column ordering.
    """
    create_directory(os.path.dirname(csv_path))
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_catalog_yaml(yaml_path: str, meta: dict):
    """
    Writes companion metadata YAML, preserving original first_captured timestamp if present.
    """
    create_directory(os.path.dirname(yaml_path))
    if file_exists(yaml_path):
        try:
            with open(yaml_path, encoding="utf-8") as f:
                existing_meta = yaml.safe_load(f)
                if isinstance(existing_meta, dict) and "first_captured" in existing_meta:
                    meta["first_captured"] = existing_meta["first_captured"]
        except Exception:
            pass

    write_file(yaml_path, yaml.dump(meta, sort_keys=False))
