#!/usr/bin/env python3
"""
Backfill history.csv with played_at timestamps and run_id provenance
by replaying git commits on the main-output branch.
"""

import csv
import io
import os
import re
import subprocess
import sys
import argparse
from datetime import datetime, timezone, timedelta

from src.clean_history import clean_history


def parse_run_id(commit_msg, short_sha):
    """Extract run_id from commit message (e.g., #4102 or run_number=62) or fallback to short SHA."""
    match = re.search(r"#(\d+)", commit_msg)
    if match:
        return f"gh-{match.group(1)}"
    match = re.search(r"run_number=(\d+)", commit_msg)
    if match:
        return f"gh-{match.group(1)}"
    return f"commit:{short_sha}"


def parse_commit_date(date_str):
    """Parse ISO date string into UTC datetime."""
    # Handles 2024-01-14T11:34:49Z or 2024-01-14T03:50:28-07:00
    date_str = date_str.strip()
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def parse_duration_seconds(duration_sec_str, duration_str):
    """Extract integer duration in seconds or None if ambiguous/missing."""
    if duration_sec_str:
        try:
            val = int(duration_sec_str.strip())
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass

    if duration_str and ":" in duration_str:
        parts = duration_str.strip().split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except (ValueError, TypeError):
            pass

    return None


def get_history_commits(branch="main-output", csv_rel_path="output/history.csv"):
    """Fetch all commits touching the history CSV in chronological order."""
    cmd = [
        "git",
        "log",
        "--reverse",
        "--format=%H|%ad|%s",
        "--date=iso-strict",
        branch,
        "--",
        csv_rel_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    commits = []
    for line in res.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({
                "hash": parts[0],
                "short_sha": parts[0][:8],
                "date_str": parts[1],
                "subject": parts[2],
            })
    return commits


def extract_added_rows_from_commit(commit_hash, csv_rel_path="output/history.csv"):
    """Extract lines added in a given commit diff."""
    cmd = ["git", "show", "-U0", commit_hash, "--", csv_rel_path]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)

    added_lines = []
    for line in res.stdout.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])  # Strip leading '+'

    if not added_lines:
        return []

    # Parse with standard CSV reader
    reader = csv.reader(io.StringIO("\n".join(added_lines)))
    rows = []
    for row in reader:
        if not row:
            continue
        # Skip header rows if captured
        if len(row) > 1 and row[0] == "title" and row[1] == "artists":
            continue
        rows.append(row)
    return rows


def extract_video_id(link_or_id):
    """Extract 11-char YouTube videoId from a URL or raw ID string."""
    if not link_or_id:
        return ""
    link_or_id = link_or_id.strip()
    if "v=" in link_or_id:
        return link_or_id.split("v=")[-1].split("&")[0]
    if "youtu.be/" in link_or_id:
        return link_or_id.split("youtu.be/")[-1].split("?")[0]
    return link_or_id


def normalize_raw_row(row):
    """
    Normalizes historical rows from legacy schema variants to standard 8 base columns:
    [title, artists, album, inLibrary, likeStatus, duration, duration_seconds, videoId]
    """
    if not row:
        return [""] * 8

    # Variant A & B: 9 columns (contained 'played' column at index 5)
    # [title, artists, album, inLibrary, likeStatus, played, duration, duration_seconds, link/videoId]
    if len(row) == 9:
        title = row[0]
        artists = row[1]
        album = row[2]
        in_library = row[3]
        like_status = row[4]
        # index 5 is 'played'
        duration = row[6]
        duration_sec = row[7]
        video_id = extract_video_id(row[8])
        return [title, artists, album, in_library, like_status, duration, duration_sec, video_id]

    # Variant C: Standard 8 columns
    # [title, artists, album, inLibrary, likeStatus, duration, duration_seconds, videoId]
    base_row = list(row[:8])
    while len(base_row) < 8:
        base_row.append("")
    base_row[7] = extract_video_id(base_row[7])
    return base_row


def replay_git_history(branch="main-output", csv_rel_path="output/history.csv"):
    """
    Replay all commits in reverse chronological order (or chronological + reverse)
    to assemble the full raw history timeline with calculated timestamps.
    """
    commits = get_history_commits(branch, csv_rel_path)
    print(f"Found {len(commits):,} commits touching {csv_rel_path} on {branch}.")

    # Collect batches chronologically
    all_batches = []
    total_raw_rows = 0

    for idx, commit in enumerate(commits, 1):
        # Skip bulk maintenance / cleanup commits
        if "Clean up duplicate history" in commit["subject"]:
            continue

        commit_dt = parse_commit_date(commit["date_str"])
        run_id = parse_run_id(commit["subject"], commit["short_sha"])

        rows = extract_added_rows_from_commit(commit["hash"], csv_rel_path)
        if not rows:
            continue

        # In diff additions: row 0 was the latest song played just before commit
        # Project backwards in time for each song
        timestamped_rows = []
        current_time = commit_dt

        for r in rows:
            base_row = normalize_raw_row(r)
            dur_str = base_row[5]
            dur_sec_str = base_row[6]
            dur_sec = parse_duration_seconds(dur_sec_str, dur_str)

            if current_time and dur_sec and dur_sec > 0:
                current_time = current_time - timedelta(seconds=dur_sec)
                played_at = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                played_at = ""

            timestamped_row = base_row + [played_at, run_id]
            timestamped_rows.append(timestamped_row)

        all_batches.append(timestamped_rows)
        total_raw_rows += len(timestamped_rows)

        if idx % 200 == 0 or idx == len(commits):
            print(f"  Processed {idx}/{len(commits)} commits ({total_raw_rows:,} rows extracted)...")

    # In chronological replay: later commits prepended on top of earlier commits.
    # To assemble final history in reverse chronological order (newest first):
    final_raw_history = []
    for batch in reversed(all_batches):
        final_raw_history.extend(batch)

    return final_raw_history, len(commits)


def run_backfill(branch="main-output", target_csv="output/history.csv", apply=False):
    raw_history, num_commits = replay_git_history(branch, target_csv)
    print(f"\nTotal raw rows extracted before deduplication: {len(raw_history):,}")

    # Step 2: Deduplicate sequence slices and filter noise
    key_idx = 7  # videoId is at index 7
    cleaned_rows, stats = clean_history(raw_history, key_idx=key_idx, min_overlap=4, max_distance=500)

    header = [
        "title",
        "artists",
        "album",
        "inLibrary",
        "likeStatus",
        "duration",
        "duration_seconds",
        "videoId",
        "played_at",
        "run_id",
    ]

    print("\n" + "=" * 60)
    print(f"  BACKFILL TIMESTAMPS & RUN_ID REPORT")
    print("=" * 60)
    print(f"  Total Commits Scanned:     {num_commits:,}")
    print(f"  Raw Rows Extracted:        {stats['initial_rows']:,}")
    print(f"  Noise Tracks Filtered:     {stats['noise_tracks_removed']:,}")
    print(f"  Duplicate Slices Pruned:   {stats['duplicate_blocks_found']:,} ({stats['duplicate_rows_removed']:,} rows)")
    print(f"  Final Timestamped Rows:    {stats['final_rows']:,}")
    print("-" * 60)

    if cleaned_rows:
        newest = cleaned_rows[0]
        oldest = cleaned_rows[-1]
        mid = cleaned_rows[len(cleaned_rows) // 2]
        print("\n  Sample Rows:")
        print(f"    1. Newest: {newest[0]} by {newest[1]} | videoId={newest[7]} | played_at={newest[8]} | run_id={newest[9]}")
        print(f"    2. Mid:    {mid[0]} by {mid[1]} | videoId={mid[7]} | played_at={mid[8]} | run_id={mid[9]}")
        print(f"    3. Oldest: {oldest[0]} by {oldest[1]} | videoId={oldest[7]} | played_at={oldest[8]} | run_id={oldest[9]}")

    if apply:
        backup_path = f"{target_csv}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if os.path.exists(target_csv):
            with open(target_csv, "r", newline="", encoding="utf-8") as f_in, open(backup_path, "w", newline="", encoding="utf-8") as f_out:
                f_out.write(f_in.read())
            print(f"\n  [APPLY] Backup saved to: {backup_path}")

        with open(target_csv, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.writer(f_out, delimiter=",", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(header)
            writer.writerows(cleaned_rows)

        print(f"  [APPLY] Written {len(cleaned_rows):,} rows to {target_csv} successfully!")
    else:
        print(f"\n  [DRY RUN] Run with --apply to write changes to {target_csv}")

    return cleaned_rows, stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill history.csv timestamps and run IDs from Git history.")
    parser.add_argument("--branch", default="main-output", help="Git branch to inspect (default: main-output)")
    parser.add_argument("--csv", default="output/history.csv", help="Path to history.csv")
    parser.add_argument("--apply", action="store_true", help="Apply changes and overwrite history.csv")
    args = parser.parse_args()

    run_backfill(branch=args.branch, target_csv=args.csv, apply=args.apply)
