import csv
import io
import os
from datetime import UTC, datetime
from unittest.mock import patch

import yaml

from src.output import (
    Output,
    get_file_display,
    read_last_history_sync_at,
    update_search_suggestions,
)


def test_get_file_display():
    assert get_file_display("history") == ("🕒", "History")
    assert get_file_display("liked_songs") == ("❤️", "Liked Songs")
    assert get_file_display("home") == ("🏠", "Home Feed")
    assert get_file_display("library_songs") == ("🎵", "Library Songs")
    assert get_file_display("library_albums") == ("💿", "Library Albums")
    assert get_file_display("library_artists") == ("👤", "Library Artists")
    assert get_file_display("library_subscriptions") == ("🔔", "Subscriptions")
    assert get_file_display("library_upload_songs") == ("☁️", "Uploaded Songs")
    assert get_file_display("search/suggest_by_letter") == ("🔤", "Search Suggestions")
    assert get_file_display("mixes") == ("🎛️", "Mixes")
    assert get_file_display("custom_endpoint") == ("📄", "Custom Endpoint")


def test_output_write_files_logs_created_and_up_to_date(tmp_path, monkeypatch):
    def mock_output_path(file=""):
        if len(file) > 0:
            return os.path.join(str(tmp_path), file)
        return str(tmp_path)

    monkeypatch.setattr("src.output.output_path", mock_output_path)
    monkeypatch.setattr("src.meta.output_path", mock_output_path)
    monkeypatch.setattr("src.util.output_path", mock_output_path)

    records = [
        {
            "title": "Track 1",
            "artists": [{"name": "Artist 1"}],
            "album": {"name": "Album 1"},
            "duration": "3:00",
            "duration_seconds": 180,
            "videoId": "vid1",
            "played": "Today",
        }
    ]

    out = Output("history", records)

    # First write creates master and partitions
    from src.changes import ChangeTracker

    ChangeTracker.reset()
    with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
        res = out.write_files()
        assert res == "history"
        output_text = mock_stdout.getvalue()
        assert "🕒 History: ✨ +1 plays added" in output_text
        assert len(ChangeTracker.get_changes()) == 1
        assert ChangeTracker.get_changes()[0].label == "History"

    # Second write with same content should report up to date
    out2 = Output("history", records)
    with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
        res2 = out2.write_files()
        assert res2 is None
        output_text = mock_stdout.getvalue()
        assert "🕒 History: ☕ Up to date" in output_text
        assert len(ChangeTracker.get_changes()) == 1  # Unchanged, no new record


def test_output_write_files_non_prepend(tmp_path, monkeypatch):
    def mock_output_path(file=""):
        if len(file) > 0:
            return os.path.join(str(tmp_path), file)
        return str(tmp_path)

    monkeypatch.setattr("src.output.output_path", mock_output_path)
    monkeypatch.setattr("src.meta.output_path", mock_output_path)
    monkeypatch.setattr("src.util.output_path", mock_output_path)

    records = [
        {
            "title": "Custom Song",
            "artists": [{"name": "Artist 1"}],
            "album": {"name": "Album 1"},
            "duration": "3:00",
            "duration_seconds": 180,
            "videoId": "custom_vid1",
        }
    ]

    out = Output("custom_songs", records)
    with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
        res = out.write_files()
        assert res == "custom_songs"
        output_text = mock_stdout.getvalue()
        assert "📄 Custom Songs: 🆕 Created with 1 rows" in output_text


def test_update_search_suggestions_logs(tmp_path, monkeypatch):
    def mock_output_path(file=""):
        if len(file) > 0:
            return os.path.join(str(tmp_path), file)
        return str(tmp_path)

    monkeypatch.setattr("src.output.output_path", mock_output_path)
    monkeypatch.setattr("src.meta.output_path", mock_output_path)
    monkeypatch.setattr("src.util.output_path", mock_output_path)

    os.makedirs(tmp_path / "search", exist_ok=True)

    # First update with new terms
    from src.changes import ChangeTracker

    ChangeTracker.reset()
    search_data = {"a": ["apple", "artist"]}
    with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
        res = update_search_suggestions(search_data)
        assert res == "search/suggest_by_letter"
        assert "🔤 Search Suggestions: ✨ +2 new terms" in mock_stdout.getvalue()
        assert len(ChangeTracker.get_changes()) == 1
        assert ChangeTracker.get_changes()[0].label == "Search Suggestions"
        assert ChangeTracker.get_changes()[0].count == 2

    # Second update with same terms
    with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
        res = update_search_suggestions(search_data)
        assert res is None
        assert "🔤 Search Suggestions: ☕ Up to date" in mock_stdout.getvalue()
        assert len(ChangeTracker.get_changes()) == 1  # Unchanged, no new record


def test_get_words_from_suggestions(monkeypatch):
    monkeypatch.setattr(
        "src.output.read_search_suggestions",
        lambda: {"a": ["apple pie", "apricot"], "b": ["banana"]},
    )
    from src.output import get_words_from_suggestions

    words = get_words_from_suggestions(size_gt=3)
    assert "apple" in words
    assert "banana" in words


def test_read_last_history_sync_at(tmp_path):
    assert read_last_history_sync_at(str(tmp_path / "missing")) is None

    bad_yaml = tmp_path / "bad_yaml"
    bad_yaml.write_text(":::[", encoding="utf-8")
    assert read_last_history_sync_at(str(bad_yaml)) is None

    non_dict = tmp_path / "non_dict"
    non_dict.write_text("- just a list\n", encoding="utf-8")
    assert read_last_history_sync_at(str(non_dict)) is None

    bad_ts = tmp_path / "bad_ts"
    bad_ts.write_text("Sync:\n  last_sync_at: invalid-date\n", encoding="utf-8")
    assert read_last_history_sync_at(str(bad_ts)) is None

    naive_ts = tmp_path / "naive_ts"
    naive_ts.write_text("Sync:\n  last_sync_at: '2026-11-26T16:54:51'\n", encoding="utf-8")
    assert read_last_history_sync_at(str(naive_ts)) == datetime(
        2026, 11, 26, 16, 54, 51, tzinfo=UTC
    )

    unquoted_dt = tmp_path / "unquoted_dt"
    unquoted_dt.write_text("Sync:\n  last_sync_at: 2026-11-26T16:54:51Z\n", encoding="utf-8")
    assert read_last_history_sync_at(str(unquoted_dt)) == datetime(
        2026, 11, 26, 16, 54, 51, tzinfo=UTC
    )


def test_history_sync_window_bracketing_e2e(tmp_path, monkeypatch):
    monkeypatch.setenv("YTM_TIMEZONE", "America/Denver")

    def mock_output_path(file=""):
        if len(file) > 0:
            return os.path.join(str(tmp_path), file)
        return str(tmp_path)

    monkeypatch.setattr("src.output.output_path", mock_output_path)
    monkeypatch.setattr("src.meta.output_path", mock_output_path)
    monkeypatch.setattr("src.util.output_path", mock_output_path)

    def make_rec(vid, title, played):
        return {
            "title": title,
            "artists": [{"name": "Artist"}],
            "album": {"name": "Album"},
            "duration": "3:00",
            "duration_seconds": 180,
            "videoId": vid,
            "played": played,
        }

    # 1. Initial sync on Nov 25 evening (naive datetime -> normalized to UTC)
    r1 = [make_rec("v1", "Track 1", "Today")]
    assert (
        Output("history", r1, run_time=datetime(2026, 11, 26, 2, 0, 0)).write_files() == "history"
    )
    meta_1 = yaml.safe_load((tmp_path / "meta" / "history").read_text(encoding="utf-8"))
    assert meta_1["Sync"]["last_sync_at"] == "2026-11-26T02:00:00Z"

    # 2. Idle run on Nov 26 morning (09:54 AM MST = 16:54Z) refreshes Sync.last_sync_at on new listening day
    res_idle = Output(
        "history",
        [make_rec("v1", "Track 1", "Yesterday")],
        run_time=datetime(2026, 11, 26, 16, 54, 51, tzinfo=UTC),
    ).write_files()
    assert res_idle is None
    meta_2 = yaml.safe_load((tmp_path / "meta" / "history").read_text(encoding="utf-8"))
    assert meta_2["Sync"]["last_sync_at"] == "2026-11-26T16:54:51Z"

    # 3. Same listening day after 00:00 UTC (#7118 at 6:44 PM MST = 2026-11-27T01:44:29Z):
    # YTM reports 'Yesterday', which would naively stamp 2026-11-25, but sync-window brackets to 2026-11-26!
    r3 = [
        make_rec("v3", "Track 3", "Yesterday"),
        make_rec("v2", "Track 2", "Yesterday"),
        make_rec("v1", "Track 1", "Yesterday"),
    ]
    res_3 = Output(
        "history",
        r3,
        run_time=datetime(2026, 11, 27, 1, 44, 29, tzinfo=UTC),
    ).write_files()
    assert res_3 == "history"

    with open(tmp_path / "history.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [(r["videoId"], r["played_at"]) for r in rows] == [
        ("v3", "2026-11-26T00:00:00Z"),
        ("v2", "2026-11-26T00:00:00Z"),
        ("v1", "2026-11-25T00:00:00Z"),
    ]
    meta_3 = yaml.safe_load((tmp_path / "meta" / "history").read_text(encoding="utf-8"))
    assert meta_3["Sync"]["last_sync_at"] == "2026-11-27T01:44:29Z"
