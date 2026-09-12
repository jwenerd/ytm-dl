import csv
import os
import sys
import argparse
from datetime import datetime

NOISE_TRACK_IDS = {
    "Sv0LwXYAVVg",
    "dMEp0pl-hhE",
    "yOk_XMB6_vs",
    "sE0ypPpvbNQ",
    "xu2b6YVlQoU",
    "C8KGOXqrDyU",
}


def load_history_csv(file_path, key_col="videoId"):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            return [], [], -1
        rows = list(reader)

    key_idx = header.index(key_col) if key_col in header else len(header) - 1
    return header, rows, key_idx


def find_duplicate_slices(rows, key_idx, min_overlap=4, max_distance=500):
    """
    Detect overlapping contiguous duplicate slices caused by batch prepend failures.
    Returns:
        list of tuples: (start_idx, end_idx, match_target_idx, length, [sample_titles])
    """
    ids = [r[key_idx] if len(r) > key_idx else "" for r in rows]
    titles = [r[0] if len(r) > 0 else "" for r in rows]
    duplicate_slices = []

    deleted_indices = set()
    i = 0
    while i < len(rows):
        if i in deleted_indices:
            i += 1
            continue

        best_match = None  # (match_len, j)
        # Search forward for matching duplicate blocks
        for shift in range(1, min(max_distance, len(rows) - i)):
            j = i + shift
            if j in deleted_indices:
                continue

            match_len = 0
            while (
                i + match_len < len(rows)
                and j + match_len < len(rows)
                and (i + match_len) not in deleted_indices
                and (j + match_len) not in deleted_indices
                and ids[i + match_len]
                and ids[i + match_len] == ids[j + match_len]
            ):
                match_len += 1

            if match_len >= min_overlap:
                if best_match is None or match_len > best_match[0]:
                    best_match = (match_len, j)

        if best_match:
            match_len, j = best_match
            sample = titles[i : i + min(3, match_len)]
            duplicate_slices.append((i, i + match_len, j, match_len, sample))
            for idx in range(i, i + match_len):
                deleted_indices.add(idx)
            i += match_len
        else:
            i += 1

    return duplicate_slices, deleted_indices


def clean_history(rows, key_idx, min_overlap=4, max_distance=500, remove_noise=True):
    """
    Cleans history rows by removing noise tracks and duplicate sequence slices.
    Returns:
        cleaned_rows, stats_dict
    """
    initial_count = len(rows)
    noise_count = 0
    filtered_rows = []

    # Step 1: Remove noise tracks
    for row in rows:
        key = row[key_idx] if len(row) > key_idx else ""
        if remove_noise and key in NOISE_TRACK_IDS:
            noise_count += 1
            continue
        filtered_rows.append(row)

    # Step 2: Detect and remove duplicate sequence slices
    duplicate_slices, deleted_indices = find_duplicate_slices(
        filtered_rows, key_idx, min_overlap=min_overlap, max_distance=max_distance
    )

    cleaned_rows = [
        row for idx, row in enumerate(filtered_rows) if idx not in deleted_indices
    ]

    stats = {
        "initial_rows": initial_count,
        "noise_tracks_removed": noise_count,
        "duplicate_blocks_found": len(duplicate_slices),
        "duplicate_rows_removed": len(deleted_indices),
        "final_rows": len(cleaned_rows),
        "duplicate_slices": duplicate_slices,
    }

    return cleaned_rows, stats


def run_cleanup(file_path, min_overlap=4, max_distance=500, apply=False):
    header, rows, key_idx = load_history_csv(file_path)
    cleaned_rows, stats = clean_history(
        rows, key_idx, min_overlap=min_overlap, max_distance=max_distance
    )

    print("\n" + "=" * 60)
    print(f"  HISTORY CLEANUP REPORT: {file_path}")
    print("=" * 60)
    print(f"  Initial rows:           {stats['initial_rows']:,}")
    print(f"  Noise tracks removed:   {stats['noise_tracks_removed']:,}")
    print(f"  Duplicate blocks found: {stats['duplicate_blocks_found']:,}")
    print(f"  Duplicate rows removed: {stats['duplicate_rows_removed']:,}")
    print(f"  Final cleaned rows:     {stats['final_rows']:,} (reduction of {stats['initial_rows'] - stats['final_rows']:,} rows)")
    print("-" * 60)

    if stats["duplicate_slices"]:
        print("\n  Sample Detected Duplicate Blocks:")
        for idx, (start, end, target, length, sample) in enumerate(stats["duplicate_slices"][:10], 1):
            print(f"    {idx}. Rows {start}..{end-1} ({length} tracks) matching rows {target}..{target+length-1}")
            print(f"       Tracks: {', '.join(sample)}...")

    if apply:
        backup_path = f"{file_path}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with open(file_path, "r", newline="", encoding="utf-8") as f_in, open(backup_path, "w", newline="", encoding="utf-8") as f_out:
            f_out.write(f_in.read())
        print(f"\n  [APPLY] Backup saved to: {backup_path}")

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(cleaned_rows)
        print(f"  [APPLY] Cleaned history written to: {file_path}")
    else:
        print("\n  [DRY-RUN] No changes written to disk. Use --apply to execute cleanup.")

    print("=" * 60 + "\n")
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean duplicate sequences from history.csv")
    parser.add_argument("file", nargs="?", default="output/history.csv", help="Path to history.csv")
    parser.add_argument("--min-overlap", type=int, default=4, help="Minimum sequence length to consider duplicate (default 4)")
    parser.add_argument("--max-distance", type=int, default=500, help="Maximum search distance for duplicate batches (default 500)")
    parser.add_argument("--apply", action="store_true", help="Apply changes and save backup (default is dry-run)")

    args = parser.parse_args()
    run_cleanup(args.file, min_overlap=args.min_overlap, max_distance=args.max_distance, apply=args.apply)
