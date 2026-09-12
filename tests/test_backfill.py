import pytest
from datetime import datetime, timezone
from src.backfill_history import (
    parse_run_id,
    parse_commit_date,
    parse_duration_seconds,
    extract_video_id,
    normalize_raw_row,
)
from src.mapping import enrich_history_records, HistorySchema, Mapping


def test_extract_video_id():
    assert extract_video_id("https://music.youtube.com/watch?v=MiOGtssMuFw") == "MiOGtssMuFw"
    assert extract_video_id("https://music.youtube.com/watch?v=MiOGtssMuFw&feature=share") == "MiOGtssMuFw"
    assert extract_video_id("https://youtu.be/MiOGtssMuFw?si=123") == "MiOGtssMuFw"
    assert extract_video_id("MiOGtssMuFw") == "MiOGtssMuFw"
    assert extract_video_id("") == ""


def test_normalize_raw_row():
    # 9-col legacy with link
    row9_link = ["Title", "Artist", "Album", "False", "LIKE", "Today", "3:20", "200", "https://music.youtube.com/watch?v=MiOGtssMuFw"]
    norm9 = normalize_raw_row(row9_link)
    assert len(norm9) == 8
    assert norm9 == ["Title", "Artist", "Album", "False", "LIKE", "3:20", "200", "MiOGtssMuFw"]

    # Standard 8-col
    row8 = ["Title", "Artist", "Album", "False", "LIKE", "3:20", "200", "MiOGtssMuFw"]
    assert normalize_raw_row(row8) == row8


def test_parse_run_id():
    assert parse_run_id("run(frequent) schedule #4102 7️⃣ 🚪 🎽", "2fdf345c") == "gh-4102"
    assert parse_run_id("🎵 🤠 job=run run_number=62)", "8348217f") == "gh-62"
    assert parse_run_id("update", "08a031ad") == "commit:08a031ad"
    assert parse_run_id("721e98a23c15f4f4de7f4b50ae887b1ae0727e95", "721e98a2") == "commit:721e98a2"


def test_parse_commit_date():
    dt1 = parse_commit_date("2025-05-02T02:15:12Z")
    assert dt1 == datetime(2025, 5, 2, 2, 15, 12, tzinfo=timezone.utc)

    dt2 = parse_commit_date("2024-01-14T03:50:28-07:00")
    assert dt2 == datetime(2024, 1, 14, 10, 50, 28, tzinfo=timezone.utc)

    assert parse_commit_date("invalid-date") is None


def test_parse_duration_seconds():
    assert parse_duration_seconds("189", "3:09") == 189
    assert parse_duration_seconds("", "3:09") == 189
    assert parse_duration_seconds("", "1:02:03") == 3723
    assert parse_duration_seconds("0", "") is None
    assert parse_duration_seconds("", "") is None
    assert parse_duration_seconds("invalid", "invalid") is None


from src.mapping import (
    snap_relative_played_at,
    enrich_history_records,
    HistorySchema,
    Mapping,
)


def test_snap_relative_played_at():
    # Saturday, Sep 12, 2026
    ref_time = datetime(2026, 9, 12, 14, 30, 0, tzinfo=timezone.utc)

    # Today
    assert snap_relative_played_at("Today", ref_time) == "2026-09-12T00:00:00Z"
    assert snap_relative_played_at("today", ref_time) == "2026-09-12T00:00:00Z"

    # Yesterday
    assert snap_relative_played_at("Yesterday", ref_time) == "2026-09-11T00:00:00Z"

    # This week (Monday of current week was Sep 7, 2026)
    assert snap_relative_played_at("This week", ref_time) == "2026-09-07T00:00:00Z"

    # Last week (Monday of last week was Aug 31, 2026)
    assert snap_relative_played_at("Last week", ref_time) == "2026-08-31T00:00:00Z"

    # Month Year
    assert snap_relative_played_at("August 2026", ref_time) == "2026-08-01T00:00:00Z"
    assert snap_relative_played_at("Feb 2025", ref_time) == "2025-02-01T00:00:00Z"

    # Empty / Fallback
    assert snap_relative_played_at("", ref_time) == "2026-09-12T00:00:00Z"
    assert snap_relative_played_at(None, ref_time) == "2026-09-12T00:00:00Z"


def test_enrich_history_records():
    run_time = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    records = [
        {"title": "Song A", "played": "Today", "videoId": "vidA"},
        {"title": "Song B", "played": "Yesterday", "videoId": "vidB"},
        {"title": "Song C", "played": "August 2026", "videoId": "vidC"},
        {"title": "Song D", "videoId": "vidD"},
    ]
    enriched = enrich_history_records(records, run_time=run_time, run_id="gh-1234")

    assert enriched[0]["played_at"] == "2026-09-12T00:00:00Z"
    assert enriched[0]["run_id"] == "gh-1234"
    assert enriched[1]["played_at"] == "2026-09-11T00:00:00Z"
    assert enriched[1]["run_id"] == "gh-1234"
    assert enriched[2]["played_at"] == "2026-08-01T00:00:00Z"
    assert enriched[2]["run_id"] == "gh-1234"
    assert enriched[3]["played_at"] == "2026-09-12T00:00:00Z"
    assert enriched[3]["run_id"] == "gh-1234"


def test_history_schema_columns():
    schema = HistorySchema()
    expected = [
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
    assert schema.keys == expected


def test_mapping_history_generation():
    records = [
        {
            "title": "Song A",
            "artists": [{"name": "Artist 1"}],
            "album": {"name": "Album 1"},
            "inLibrary": True,
            "likeStatus": "LIKE",
            "duration": "3:00",
            "duration_seconds": 180,
            "videoId": "vid123",
        }
    ]
    mapping = Mapping("history", records)
    assert mapping.columns == [
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
    assert mapping.key_index == 7
    rows = mapping.get_rows()
    assert len(rows) == 1
    assert rows[0][0] == "Song A"
    assert rows[0][1] == "Artist 1"
    assert rows[0][7] == "vid123"
    assert rows[0][8] != ""  # played_at populated
    assert rows[0][9] != ""  # run_id populated
