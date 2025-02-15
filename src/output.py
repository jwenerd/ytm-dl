import csv
import os.path
import shutil
from .mapping import Mapping
from .prepend import prepend_rows_for_file
from .util import (
    file_hash,
    file_exists,
    output_path,
    read_output_yaml,
    write_output_yaml,
)
from .meta import MetaOutput

PREPEND_FILES = [
    "home",
    "history",
    "liked_songs",
    "library_songs",
    "library_subscriptions",
    "library_upload_songs",
    "library_upload_artists",
    "library_upload_albums",
    "library_albums",
]

BY_KEY = ["library_subscriptions", "library_upload_artists", "library_artists"]


# todo: rename this output
class Output:
    readme_written = False

    def __init__(self, file, records, meta={}):
        self.file = file
        self.csv_file = self.file + ".csv"
        self.csv_file_with_path = output_path(self.csv_file)
        self.file_exists = file_exists(self.csv_file_with_path)

        self.prepend = file in PREPEND_FILES
        self.by_key = file in BY_KEY

        self.mapping = Mapping(file, records)
        self.hash_before = file_hash(self.csv_file)
        self.meta = MetaOutput(file, meta)
        self.rows = []

    def write_csv(self):
        with open(self.csv_file_with_path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile, delimiter=",", quoting=csv.QUOTE_MINIMAL)
            writer.writerows([self.mapping.columns] + self.rows)

    def prepend_to_csv(self):
        # first copy the existing csv
        prev_file = f"{self.csv_file_with_path}.old"
        shutil.move(self.csv_file_with_path, prev_file)

        # write a csv the newly added values
        self.write_csv()

        # move all the values from the previous file to the new file; open in append
        # mode so starts at the end of the file
        with open(prev_file, "r") as old_file, open(
            self.csv_file_with_path, "a+"
        ) as new_file:
            for index, line in enumerate(old_file):
                if index == 0:
                    continue
                new_file.write(line)

        # lastly - delete the old data
        os.unlink(prev_file)

    def update_rows_for_prepend(self):
        self.rows = prepend_rows_for_file(
            self.csv_file_with_path, self.rows, self.by_key
        )

    def write_files(self):
        self.rows = self.mapping.get_rows()

        use_prepend = self.file_exists and (self.prepend or self.by_key)

        if use_prepend:
            self.update_rows_for_prepend()
            new_rows_count = len(self.rows)
            self.meta.add_meta("CSV File", {"lines_added": new_rows_count})

            # todo: if doing other files need to pass different look aahead
            if new_rows_count > 0:
                self.prepend_to_csv()
        else:
            self.write_csv()

        if self.hash_before == file_hash(self.csv_file):
            return print("no updates to " + self.file)

        self.meta.write_files()
        length_rows = str(len(self.rows))

        log = (
            f"added {length_rows} to {self.file}"
            if self.prepend
            else f"created {self.file} with {length_rows} rows"
        )
        print(log)

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
    words = [w for l in words for w in l]
    words = [word for word in set(words) if len(word) > size_gt]
    return words


def update_search_suggestions(search_results):
    output_file = "search/suggest_by_letter.yaml"
    data = read_output_yaml(output_file)
    if data is None:
        data = {}
    data = read_search_suggestions()

    added_count = 0
    for key, data_new in search_results.items():
        data_before = data.get(key, [])
        search_results[key] = list(set(data_before + data_new))
        search_results[key].sort()
        added_count += len(search_results[key]) - len(data_before)

    write_output_yaml(output_file, search_results)
    print(f"added {added_count} to search/suggest_by_letter")
    return "search/suggest_by_letter"
