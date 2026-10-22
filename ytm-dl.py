#!/usr/bin/env python
import concurrent.futures
import string
import sys

from src.api import (
    ApiMethod,
    AuthenticationExpiredError,
    report_auth_failure,
    suggest_search,
    validate_auth,
)
from src.changes import ChangeTracker
from src.home_catalog import sync_all_home_shelves
from src.meta import write_meta
from src.mood_mixes import sync_all_mood_mixes
from src.output import Output, update_search_suggestions


def ytmusic_to_file(file):
    records, meta = ApiMethod(f"get_{file}").perform()
    return Output(file, records, meta).write_files()


def do_search_suggestions():
    with concurrent.futures.ThreadPoolExecutor() as executor:
        search_results = list(executor.map(suggest_search, list(string.ascii_lowercase)))
    search_results = {row[0]: row[1] for row in search_results}
    return update_search_suggestions(search_results)


def do_updates(option):
    ChangeTracker.reset()
    if option not in ["all", "frequent", "mixes", "home", "auth", "report", "mail"]:
        print("Option must be all, frequent, mixes, home, auth, report, or mail")
        print("  given: " + str(option))
        sys.exit(1)

    if option == "mail":
        from src.reports.mailer import ReportMailer

        cadence = "daily"
        for arg in sys.argv[2:]:
            if not arg.startswith("-"):
                cadence = arg
                break
        dry_run = "--dry-run" in sys.argv
        mailer = ReportMailer(cadence=cadence)
        try:
            res = mailer.send(dry_run=dry_run)
            print(f"✓ Mailer result: {res}")
        except Exception as e:
            print(f"✗ Mailer error: {e}")
            sys.exit(1)
        return

    if option == "report":
        from src.reports.rotator import run_reports

        cadence = sys.argv[2] if len(sys.argv) >= 3 else None
        generated = run_reports(output_dir="output", force_cadence=cadence)
        if generated:
            print(f"✓ Generated AI listening report(s): {', '.join(generated)}")
        else:
            print("ℹ No reports due for generation.")
        return

    try:
        auth_info = validate_auth()
    except AuthenticationExpiredError as e:
        report_auth_failure(e)
        sys.exit(1)

    if option == "auth":
        captured = auth_info.get("captured_at", "Unknown")
        age = auth_info.get("age", "Unknown")
        auth_type = auth_info.get("auth_type", "browser.json")
        sample = auth_info.get("sample_count", 0)
        print("✓ YouTube Music authentication is valid!")
        print(f"  Auth Mode:        {auth_type}")
        if "captured_at" in auth_info:
            print(f"  Session Captured: {captured} ({age})")
        print(f"  Probe Result:     Successfully verified {sample} liked track sample.")
        from src.meta import write_auth_meta

        write_auth_meta()
        return

    if option == "mixes":
        sync_all_mood_mixes()
        ApiMethod.save_api_artifact()
        write_meta(len(ChangeTracker.get_changes()) > 0, run_option=option)
        return

    if option == "home":
        sync_all_home_shelves()
        ApiMethod.save_api_artifact()
        write_meta(len(ChangeTracker.get_changes()) > 0, run_option=option)
        return

    files = ["liked_songs", "library_songs", "history"]
    if option == "all":
        files += ["library_subscriptions", "library_artists", "library_albums"]
        files += ["library_upload_songs", "library_upload_artists", "library_upload_albums"]

    files_written = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        files_written += list(executor.map(lambda file: ytmusic_to_file(file), files))

    if option == "all":
        search_res = do_search_suggestions()
        if search_res:
            files_written.append(search_res)
        sync_all_mood_mixes()
        sync_all_home_shelves()

    files_written = set(filter(None, files_written))

    # Evaluate lazy-man AI reports after sync
    try:
        from src.reports.rotator import run_reports

        history_updated = any("history" in str(f) for f in files_written)
        reports_generated = run_reports(output_dir="output", refresh_nocturnal=history_updated)
        if reports_generated:
            print(f"✓ Generated listening report(s): {', '.join(reports_generated)}")
            try:
                from src.util import write_file

                write_file("tmp/reports_generated.txt", "\n".join(reports_generated) + "\n")
            except Exception:
                pass
            ChangeTracker.record(
                emoji="📰",
                label="Listening Reports",
                count=len(reports_generated),
                log_message=f"✨ {', '.join(r.capitalize() for r in reports_generated)} report{'s' if len(reports_generated) > 1 else ''} generated",
            )
    except Exception as e:
        print(f"Warning: Failed to evaluate listening reports: {e}")

    output_updates = len(files_written) > 0 or len(ChangeTracker.get_changes()) > 0

    ApiMethod.save_api_artifact()
    write_meta(output_updates, run_option=option)


if __name__ == "__main__":
    option = ""
    if len(sys.argv) >= 2:
        option = sys.argv[1]

    do_updates(option)
