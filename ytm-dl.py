#!/usr/bin/env python
import sys
import concurrent.futures
import string

from src.api import ApiMethod, suggest_search
from src.output import Output, update_search_suggestions
from src.meta import write_meta


def ytmusic_to_file(file):
    records, meta = ApiMethod(f"get_{file}").perform()
    result = Output(file, records, meta).write_files()
    if result is None:
        return
    return result


def do_search_suggestions():
    with concurrent.futures.ThreadPoolExecutor() as executor:
        search_results = list(
            executor.map(lambda l: suggest_search(l), list(string.ascii_lowercase))
        )
    search_results = {row[0]: row[1] for row in search_results}
    return update_search_suggestions(search_results)


def do_updates(option):
    if not option in ["all", "frequent"]:
        print("Option must be all or frequent")
        print("  given: " + str(option))
        sys.exit(1)

    files = ["liked_songs", "library_songs", "history"]
    if option == "all":
        files += ["library_subscriptions", "library_artists", "library_albums"]
        files += ["library_upload_songs", "library_upload_artists", "library_upload_albums"]

    files_written = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        files_written += list(executor.map(lambda file: ytmusic_to_file(file), files))

    if option == "all":
        files_written += do_search_suggestions()

    files_written = set(filter(None, files_written))
    output_updates = len(files_written) > 0

    ApiMethod.save_api_artifact()
    write_meta(output_updates)


if __name__ == "__main__":
    option = ""
    if len(sys.argv) >= 2:
        option = sys.argv[1]

    do_updates(option)
