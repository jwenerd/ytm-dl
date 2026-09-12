import io
import os
from unittest.mock import patch

from src.output import Output, get_file_display, update_search_suggestions


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
