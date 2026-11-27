import csv
import os.path
import shutil
from datetime import UTC, datetime

import yaml

from .changes import ChangeTracker
from .history_partition import get_months_from_rows, partition_history_csv
from .mapping import Mapping, clamp_history_rows_played_at
from .meta import MetaOutput
from .prepend import get_existing_head_played_at, prepend_rows_for_file
from .util import (
    file_exists,
    file_hash,
    get_effective_listening_date,
    output_path,
    read_output_yaml,
    write_output_yaml,
)


def read_last_history_sync_at(meta_file_path: str) -> datetime | None:
    """Reads Sync.last_sync_at from output/meta/history YAML if present and valid."""
    if not os.path.isfile(meta_file_path):
        return None
    try:
        with open(meta_file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        raw_ts = (data.get("Sync") or {}).get("last_sync_at") if isinstance(data, dict) else None
        if isinstance(raw_ts, datetime):
            dt = raw_ts
        elif isinstance(raw_ts, str) and raw_ts.strip():
            dt = datetime.fromisoformat(raw_ts.strip().replace("Z", "+00:00"))
        else:
            return None
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    except (OSError, yaml.YAMLError, ValueError, AttributeError):
        return None


PREPEND_FILES = [
    "history",
    "liked_songs",
    "library_songs",
    "library_subscriptions",
    "library_upload_songs",
    "library_upload_artists",
    "library_upload_albums",
    "library_albums",
]


FILE_DISPLAY: dict[str, tuple[str, str]] = {
    "history": ("🕒", "History"),
    "liked_songs": ("❤️", "Liked Songs"),
    "home": ("🏠", "Home Feed"),
    "library_songs": ("🎵", "Library Songs"),
    "library_albums": ("💿", "Library Albums"),
    "library_artists": ("👤", "Library Artists"),
    "library_subscriptions": ("🔔", "Subscriptions"),
    "library_upload_songs": ("☁️", "Uploaded Songs"),
    "library_upload_artists": ("☁️", "Uploaded Artists"),
    "library_upload_albums": ("☁️", "Uploaded Albums"),
    "search/suggest_by_letter": ("🔤", "Search Suggestions"),
    "search/suggest_by_letter.yaml": ("🔤", "Search Suggestions"),
    "mixes": ("🎛️", "Mixes"),
}


def get_file_display(file_name: str) -> tuple[str, str]:
    """Returns (emoji, human_readable_title) for a given output file name."""
    if file_name in FILE_DISPLAY:
        return FILE_DISPLAY[file_name]
    clean_name = file_name.replace("search/", "").replace("library_", "").replace("_", " ").title()
    return "📄", clean_name


# todo: rename this output
class Output:
    readme_written = False

    def __init__(self, file, records, meta=None, run_time=None):
        if meta is None:
            meta = {}
        self.file = file
        self.csv_file = self.file + ".csv"
        self.csv_file_with_path = output_path(self.csv_file)
        self.file_exists = file_exists(self.csv_file_with_path)

        self.prepend = file in PREPEND_FILES

        self.mapping = Mapping(file, records)
        self.hash_before = file_hash(self.csv_file)
        self.meta = MetaOutput(file, meta)
        self.run_time = run_time
        self.rows = []

    def write_csv(self):
        with open(self.csv_file_with_path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile, delimiter=",", quoting=csv.QUOTE_MINIMAL)
            writer.writerows([self.mapping.columns, *self.rows])

    def prepend_to_csv(self):
        # first copy the existing csv
        prev_file = f"{self.csv_file_with_path}.old"
        shutil.move(self.csv_file_with_path, prev_file)

        # write a csv the newly added values
        self.write_csv()

        # move all the values from the previous file to the new file; open in append
        # mode so starts at the end of the file
        with open(prev_file) as old_file, open(self.csv_file_with_path, "a+") as new_file:
            for index, line in enumerate(old_file):
                if index == 0:
                    continue
                new_file.write(line)

        # lastly - delete the old data
        os.unlink(prev_file)

    def update_rows_for_prepend(self):
        is_history = self.file == "history"
        self.rows = prepend_rows_for_file(
            self.csv_file_with_path,
            self.rows,
            is_history=is_history,
            key_index=self.mapping.key_index,
        )

    def write_files(self):
        run_time = self.run_time or datetime.now(UTC)
        if run_time.tzinfo is None:
            run_time = run_time.replace(tzinfo=UTC)

        self.rows = self.mapping.get_rows(run_time=run_time)

        is_history = self.file == "history"
        prev_sync_at = None
        head_played_date = None
        if is_history:
            prev_sync_at = read_last_history_sync_at(output_path("meta/history"))
            head_played_date = get_existing_head_played_at(self.csv_file_with_path)

            # remove the sleep noise tracks i use
            problems = {
                "Sv0LwXYAVVg",
                "dMEp0pl-hhE",
                "yOk_XMB6_vs",
                "sE0ypPpvbNQ",
                "xu2b6YVlQoU",
                "C8KGOXqrDyU",
            }
            key_idx = self.mapping.key_index
            self.rows = [
                row for row in self.rows if len(row) > key_idx and row[key_idx] not in problems
            ]

        use_prepend = self.file_exists and self.prepend

        if use_prepend:
            self.update_rows_for_prepend()

        if is_history:
            if self.rows:
                clamp_history_rows_played_at(
                    self.rows,
                    self.mapping.columns.index("played_at"),
                    run_time=run_time,
                    prev_sync_at=prev_sync_at,
                    head_played_date=head_played_date,
                )
            sync_ts = run_time.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.meta.add_meta("Sync", {"last_sync_at": sync_ts})

        if use_prepend:
            new_rows_count = len(self.rows)
            self.meta.add_meta("CSV File", {"lines_added": new_rows_count})

            # todo: if doing other files need to pass different look aahead
            if new_rows_count > 0:
                self.prepend_to_csv()
        else:
            self.write_csv()

        emoji, label = get_file_display(self.file)
        if self.hash_before == file_hash(self.csv_file):
            if is_history and (
                prev_sync_at is None
                or get_effective_listening_date(run_time)
                > get_effective_listening_date(prev_sync_at)
            ):
                self.meta.write_files()
            print(f"{emoji} {label}: ☕ Up to date")
            return None

        if self.file == "history":
            played_at_idx = (
                self.mapping.columns.index("played_at")
                if "played_at" in self.mapping.columns
                else 8
            )
            touched_months = (
                get_months_from_rows(self.rows, played_at_idx=played_at_idx)
                if use_prepend
                else None
            )
            partition_history_csv(
                self.csv_file_with_path,
                output_dir=output_path("history"),
                target_months=touched_months,
            )

        self.meta.write_files()
        length_rows = len(self.rows)

        if self.prepend:
            if self.file == "home":
                log = f"{emoji} {label}: ✨ +{length_rows} items captured"
            elif self.file == "history":
                log = f"{emoji} {label}: ✨ +{length_rows} plays added"
            else:
                log = f"{emoji} {label}: ✨ +{length_rows} added"
        else:
            log = f"{emoji} {label}: 🆕 Created with {length_rows} rows"
        print(log)
        ChangeTracker.record(
            emoji=emoji,
            label=label,
            count=length_rows,
            log_message=log,
        )

        return self.file


def read_search_suggestions():
    output_file = "search/suggest_by_letter.yaml"
    data = read_output_yaml(output_file)
    if data is None:
        data = {}
    return data


def get_words_from_suggestions(size_gt=3):
    data = read_search_suggestions()
    words = [" ".join(i).split() for i in list(data.values())]
    words = [w for word_list in words for w in word_list]
    return [word for word in set(words) if len(word) > size_gt]


def update_search_suggestions(search_results):
    output_file = "search/suggest_by_letter.yaml"
    data = read_search_suggestions()

    added_count = 0
    for key, data_new in search_results.items():
        data_before = data.get(key, [])
        search_results[key] = list(set(data_before + data_new))
        search_results[key].sort()
        added_count += len(search_results[key]) - len(data_before)

    write_output_yaml(output_file, search_results)
    emoji, label = get_file_display(output_file)
    if added_count > 0:
        log = f"{emoji} {label}: ✨ +{added_count} new terms"
        print(log)
        ChangeTracker.record(
            emoji=emoji,
            label=label,
            count=added_count,
            log_message=log,
        )
        return "search/suggest_by_letter"

    print(f"{emoji} {label}: ☕ Up to date")
    return None
