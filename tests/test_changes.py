import concurrent.futures
import os
from unittest.mock import patch

from src.changes import ChangeRecord, ChangeTracker


def test_record_and_get_changes():
    ChangeTracker.reset()
    assert ChangeTracker.get_changes() == []

    ChangeTracker.record(
        emoji="❤️",
        label="Liked Songs",
        count=5,
        log_message="❤️ Liked Songs: ✨ +5 added",
    )

    changes = ChangeTracker.get_changes()
    assert len(changes) == 1
    assert changes[0] == ChangeRecord(
        emoji="❤️",
        label="Liked Songs",
        count=5,
        log_message="❤️ Liked Songs: ✨ +5 added",
        details=[],
    )


def test_reset():
    ChangeTracker.reset()
    ChangeTracker.record("🕒", "History", 1, "🕒 History: ✨ +1 plays added")
    assert len(ChangeTracker.get_changes()) == 1

    ChangeTracker.reset()
    assert ChangeTracker.get_changes() == []


def test_format_commit_message_empty(monkeypatch):
    monkeypatch.setenv("GITHUB_JOB", "run")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "100")
    monkeypatch.setenv("RUN_OPTION", "frequent")

    ChangeTracker.reset()
    msg = ChangeTracker.format_commit_message()
    assert "run(frequent) workflow_dispatch #100: ☕ Up to date" in msg
    assert "No data files modified." in msg


def test_format_commit_message_single_item(monkeypatch):
    monkeypatch.setenv("GITHUB_JOB", "run")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "200")
    monkeypatch.setenv("RUN_OPTION", "frequent")

    ChangeTracker.reset()
    ChangeTracker.record("🕒", "History", 3, "🕒 History: ✨ +3 plays added")

    msg = ChangeTracker.format_commit_message()
    lines = msg.strip().split("\n")
    assert lines[0] == "run(frequent) schedule #200: 🕒 History (+3)"
    assert lines[1] == ""
    assert lines[2] == "🕒 History: ✨ +3 plays added"


def test_format_commit_message_multiple_items(monkeypatch):
    monkeypatch.setenv("GITHUB_JOB", "run")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "6770")

    ChangeTracker.reset()
    ChangeTracker.record("❤️", "Liked Songs", 10, "❤️ Liked Songs: ✨ +10 added")
    ChangeTracker.record("🕒", "History", 3, "🕒 History: ✨ +3 plays added")

    msg = ChangeTracker.format_commit_message(run_option="frequent")
    lines = msg.strip().split("\n")
    assert lines[0] == "run(frequent) workflow_dispatch #6770: ❤️ Liked Songs (+10), 🕒 History (+3)"
    assert lines[1] == ""
    assert lines[2] == "❤️ Liked Songs: ✨ +10 added"
    assert lines[3] == "🕒 History: ✨ +3 plays added"


def test_format_commit_message_many_items(monkeypatch):
    monkeypatch.setenv("GITHUB_JOB", "run")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "6771")

    ChangeTracker.reset()
    ChangeTracker.record("🕒", "History", 3, "🕒 History: ✨ +3 plays added")
    ChangeTracker.record("❤️", "Liked Songs", 2, "❤️ Liked Songs: ✨ +2 added")
    ChangeTracker.record("🔤", "Search Suggestions", 5, "🔤 Search Suggestions: ✨ +5 new terms")
    ChangeTracker.record(
        "🏠",
        "Home",
        14,
        "🏠 Home: ✨ +14 new items across 2 shelves",
        details=["- [quick-picks] +4 new", "- [covers-and-remixes] +10 new"],
    )

    msg = ChangeTracker.format_commit_message(run_option="all")
    lines = msg.strip().split("\n")
    assert lines[0] == "run(all) schedule #6771: 🕒 ❤️ 🔤 🏠 (4 datasets updated)"
    assert lines[1] == ""
    assert "🕒 History: ✨ +3 plays added" in lines
    assert "❤️ Liked Songs: ✨ +2 added" in lines
    assert "🔤 Search Suggestions: ✨ +5 new terms" in lines
    assert "🏠 Home: ✨ +14 new items across 2 shelves" in lines
    assert "  - [quick-picks] +4 new" in lines
    assert "  - [covers-and-remixes] +10 new" in lines


def test_write_commit_message_file(tmp_path):
    target_file = str(tmp_path / "commit_msg.txt")
    ChangeTracker.reset()
    ChangeTracker.record("❤️", "Liked Songs", 1, "❤️ Liked Songs: ✨ +1 added")

    with patch.dict(
        os.environ, {"GITHUB_JOB": "run", "GITHUB_EVENT_NAME": "test", "RUN_OPTION": "frequent"}
    ):
        res = ChangeTracker.write_commit_message(filepath=target_file)
        assert os.path.exists(target_file)
        with open(target_file) as f:
            content = f.read()
        assert content == res
        assert "run(frequent) test: ❤️ Liked Songs (+1)" in content


def test_concurrent_recording():
    ChangeTracker.reset()

    def worker(i):
        ChangeTracker.record("🎵", f"Song {i}", 1, f"🎵 Song {i}: ✨ +1 added")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(worker, range(50)))

    records = ChangeTracker.get_changes()
    assert len(records) == 50


def test_write_meta_integrates_commit_message(tmp_path, monkeypatch):
    from src.meta import write_meta

    commit_file = tmp_path / "commit_message.txt"

    monkeypatch.setattr(
        "src.changes.ChangeTracker.write_commit_message",
        lambda filepath="tmp/commit_message.txt", run_option="": (
            commit_file.parent.mkdir(parents=True, exist_ok=True)
            or commit_file.write_text("test commit message")
        ),
    )
    monkeypatch.setattr("src.meta.write_auth_meta", lambda: None)
    monkeypatch.setattr("src.meta.write_api_meta", lambda: None)

    write_meta(updated=True, run_option="frequent")
    assert commit_file.exists()
    assert commit_file.read_text() == "test commit message"
