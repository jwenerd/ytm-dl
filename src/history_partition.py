import csv
import os
import re
from collections import defaultdict
from datetime import UTC, datetime


def extract_month_from_timestamp(ts_str):
    """
    Extract YYYY-MM from an ISO timestamp string (e.g., '2026-09-12T01:30:00Z').
    Falls back to current UTC month if string is invalid or empty.
    """
    if ts_str and isinstance(ts_str, str):
        match = re.match(r"^(\d{4}-\d{2})", ts_str.strip())
        if match:
            return match.group(1)

    return datetime.now(UTC).strftime("%Y-%m")


def get_months_from_rows(rows, played_at_idx=8):
    """
    Returns a set of YYYY-MM strings for the given rows.
    """
    months = set()
    for row in rows:
        if not row:
            continue
        ts = row[played_at_idx] if len(row) > played_at_idx else ""
        months.add(extract_month_from_timestamp(ts))
    return months


def partition_history_csv(
    history_csv_path="output/history.csv",
    output_dir="output/history",
    target_months=None,
):
    """
    Partitions rows from history_csv_path into month-specific CSV files in output_dir (e.g. output/history/2026-09.csv).

    - If target_months is provided (list/set of 'YYYY-MM'):
      Only regenerates the specified month files.
    - If target_months is None:
      Partitions all rows across the entire history file into their respective months.

    Returns dict mapping month -> row_count written.
    """
    if not os.path.exists(history_csv_path):
        return {}

    os.makedirs(output_dir, exist_ok=True)

    if target_months is not None:
        target_months = set(target_months)

    # Read the master CSV
    with open(history_csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=",")
        header = next(reader, None)
        if header is None:
            return {}

        # Locate played_at column
        if "played_at" in header:
            played_at_idx = header.index("played_at")
        elif len(header) >= 9:
            played_at_idx = 8
        else:
            played_at_idx = len(header) - 1

        # Group rows by month
        month_rows = defaultdict(list)

        for row in reader:
            if not row:
                continue

            ts = row[played_at_idx] if len(row) > played_at_idx else ""
            month = extract_month_from_timestamp(ts)

            if target_months is None or month in target_months:
                month_rows[month].append(row)

    # Write out each month file
    results = {}
    months_to_write = set(month_rows.keys())
    if target_months is not None:
        months_to_write = months_to_write.union(target_months)

    for month in months_to_write:
        rows = month_rows.get(month, [])
        month_file = os.path.join(output_dir, f"{month}.csv")
        with open(month_file, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.writer(f_out, delimiter=",", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(header)
            if rows:
                writer.writerows(rows)
        results[month] = len(rows)

    return results
