from datetime import UTC, date, datetime

from src.mapping import (
    AlbumSchema,
    ArtistSchema,
    HistorySchema,
    HomeSchema,
    LikedSongSchema,
    Mapping,
    SongSchema,
    clamp_history_rows_played_at,
    enrich_liked_songs_records,
    get_run_id,
    snap_relative_played_at,
)


def test_get_run_id(monkeypatch):
    fixed_time = datetime(2026, 9, 12, 8, 30, 0, tzinfo=UTC)

    # Direct explicit run_id
    assert get_run_id(run_id="custom_123") == "custom_123"

    # From GITHUB_RUN_NUMBER
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "456")
    assert get_run_id(fixed_time) == "gh-456"

    # From GITHUB_RUN_ID when RUN_NUMBER unset
    monkeypatch.delenv("GITHUB_RUN_NUMBER", raising=False)
    monkeypatch.setenv("GITHUB_RUN_ID", "789")
    assert get_run_id(fixed_time) == "gh-789"

    # Local fallback
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    assert get_run_id(fixed_time) == "local_20260912_083000"


def test_schema_primary_keys():
    assert SongSchema.primary_key == "videoId"
    assert LikedSongSchema.primary_key == "videoId"
    assert HistorySchema.primary_key == "videoId"
    assert ArtistSchema.primary_key == "browseId"
    assert AlbumSchema.primary_key == "browseId"
    assert HomeSchema.primary_key == "id"


def test_mapping_columns_and_key_index():
    m_history = Mapping("history", [])
    assert m_history.primary_key == "videoId"
    assert "videoId" in m_history.columns
    assert m_history.key_index == m_history.columns.index("videoId")

    m_artists = Mapping("library_artists", [])
    assert m_artists.primary_key == "browseId"
    assert "browseId" in m_artists.columns
    assert m_artists.key_index == m_artists.columns.index("browseId")

    m_songs = Mapping("liked_songs", [])
    assert m_songs.primary_key == "videoId"
    assert "videoId" in m_songs.columns
    assert m_songs.key_index == m_songs.columns.index("videoId")
    assert m_songs.columns == [
        "title",
        "artists",
        "album",
        "duration",
        "duration_seconds",
        "videoId",
        "liked_at",
        "run_id",
    ]


def test_enrich_liked_songs_records():
    run_time = datetime(2026, 9, 12, 10, 0, 0, tzinfo=UTC)
    records = [
        {"title": "Track 1", "videoId": "v1"},
        {
            "title": "Track 2",
            "videoId": "v2",
            "liked_at": "2026-09-01T00:00:00Z",
            "run_id": "gh-100",
        },
    ]
    enriched = enrich_liked_songs_records(records, run_time=run_time, run_id="gh-200")
    assert enriched[0]["liked_at"] == "2026-09-12T10:00:00Z"
    assert enriched[0]["run_id"] == "gh-200"
    # Existing liked_at and run_id are preserved
    assert enriched[1]["liked_at"] == "2026-09-01T00:00:00Z"
    assert enriched[1]["run_id"] == "gh-100"


def test_liked_songs_mapping_rows():
    sample_records = [
        {
            "title": "Liked Track",
            "artists": [{"name": "Liked Artist"}],
            "album": {"name": "Liked Album"},
            "duration": "3:30",
            "duration_seconds": 210,
            "videoId": "vid_liked_123",
        }
    ]
    mapping = Mapping("liked_songs", sample_records)
    rows = mapping.get_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "Liked Track"
    assert row[1] == "Liked Artist"
    assert row[2] == "Liked Album"
    assert row[3] == "3:30"
    assert row[4] == 210
    assert row[5] == "vid_liked_123"
    assert row[6] != ""  # liked_at populated
    assert row[7] != ""  # run_id populated


def test_history_mapping_rows():
    sample_records = [
        {
            "title": "Song 1",
            "artists": [{"name": "Artist A"}],
            "album": {"name": "Album A"},
            "duration": "3:00",
            "duration_seconds": 180,
            "videoId": "vid123",
            "inLibrary": "True",
            "likeStatus": "LIKE",
        }
    ]
    mapping = Mapping("history", sample_records)
    rows = mapping.get_rows()
    assert len(rows) == 1
    row = rows[0]
    key_idx = mapping.key_index
    assert row[key_idx] == "vid123"


def test_home_mapping_rows():
    sample_home_records = [
        {
            "home": "Listen again",
            "home_index": "1",
            "type": "Song",
            "title": "Track 1",
            "artists": [{"name": "Artist X"}],
            "description": "Featured track",
            "id": "vid999",
        }
    ]
    mapping = Mapping("home", sample_home_records)
    assert mapping.columns == [
        "home",
        "home_index",
        "type",
        "title",
        "artists",
        "description",
        "id",
        "captured_at",
        "run_id",
    ]
    rows = mapping.get_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "Listen again"
    assert row[3] == "Track 1"
    assert row[4] == "Artist X"
    assert row[6] == "vid999"
    # Verify captured_at and run_id are populated
    assert row[7] != ""
    assert row[8] != ""


def test_snap_relative_played_at_timezone_and_nocturnal(monkeypatch):
    monkeypatch.setenv("YTM_TIMEZONE", "America/Denver")

    # 1. Daytime run (2:00 PM MDT on Oct 19 = 20:00 UTC Oct 19)
    run_day = datetime(2026, 10, 19, 20, 0, 0, tzinfo=UTC)
    assert snap_relative_played_at("Today", run_day) == "2026-10-19T00:00:00Z"
    assert snap_relative_played_at("Yesterday", run_day) == "2026-10-18T00:00:00Z"

    # 2. Evening run (10:42 PM MDT on Oct 18 = 04:42 UTC Oct 19)
    # Even though UTC is Oct 19, local time is Oct 18 evening!
    run_evening = datetime(2026, 10, 19, 4, 42, 0, tzinfo=UTC)
    assert snap_relative_played_at("Today", run_evening) == "2026-10-18T00:00:00Z"
    assert snap_relative_played_at("Yesterday", run_evening) == "2026-10-17T00:00:00Z"

    # 3. Nocturnal run (1:19 AM MDT on Oct 20 = 07:19 UTC Oct 20)
    # Both "Today" (post-midnight 12:30 AM) and "Yesterday" (pre-midnight 11:30 PM)
    # belong to the nocturnal conclusion of Oct 19
    run_nocturnal = datetime(2026, 10, 20, 7, 19, 0, tzinfo=UTC)
    assert snap_relative_played_at("Today", run_nocturnal) == "2026-10-19T00:00:00Z"
    assert snap_relative_played_at("Yesterday", run_nocturnal) == "2026-10-19T00:00:00Z"

    # 4. Morning run after cutoff (6:00 AM MDT on Oct 20 = 12:00 UTC Oct 20)
    run_morning = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
    assert snap_relative_played_at("Today", run_morning) == "2026-10-20T00:00:00Z"
    assert snap_relative_played_at("Yesterday", run_morning) == "2026-10-19T00:00:00Z"


def test_clamp_history_rows_played_at(monkeypatch):
    monkeypatch.setenv("YTM_TIMEZONE", "America/Denver")

    # Empty rows early return
    assert clamp_history_rows_played_at([], played_at_idx=8) == []

    # Exact #7118 reproduction: prev_sync at 9:54 AM MST, curr at 6:44 PM MST (01:44Z Nov 27)
    # Both have effective date 2026-11-26 -> rows stamped 2026-11-25 clamp up to 2026-11-26
    rows = [
        ["Track 1", "vid1", "2026-11-25T00:00:00Z"],
        ["Track 2", "vid2", "2026-11-25T00:00:00Z"],
    ]
    clamp_history_rows_played_at(
        rows,
        played_at_idx=2,
        run_time=datetime(2026, 11, 27, 1, 44, 29, tzinfo=UTC),
        prev_sync_at=datetime(2026, 11, 26, 16, 54, 51, tzinfo=UTC),
        head_played_date=date(2026, 11, 26),
    )
    assert [r[2] for r in rows] == ["2026-11-26T00:00:00Z", "2026-11-26T00:00:00Z"]

    # Multi-day / overnight window: enforces upper bound, lower bound, malformed fallback, and monotonicity
    overnight_rows = [
        ["Future", "v0", "2026-11-29T00:00:00Z"],  # clamped down to max_date (2026-11-27)
        [
            "Inverted",
            "v1",
            "2026-11-26T00:00:00Z",
        ],  # bumped up to 2026-11-27 because v2 is 2026-11-27!
        ["BadTS", "v2", "not-a-date"],  # falls back to max_date (2026-11-27)
        ["ValidPrev", "v3", "2026-11-26T00:00:00Z"],  # preserved as 2026-11-26
        ["TooOld", "v4", "2026-11-20T00:00:00Z"],  # clamped up to min_date (2026-11-26)
    ]
    clamp_history_rows_played_at(
        overnight_rows,
        played_at_idx=2,
        run_time=datetime(2026, 11, 27, 12, 30, 0),  # naive UTC -> 5:30 AM MST Nov 27
        prev_sync_at=datetime(2026, 11, 26, 20, 0, 0, tzinfo=UTC),
        head_played_date=date(2026, 11, 25),
    )
    assert [r[2] for r in overnight_rows] == [
        "2026-11-27T00:00:00Z",
        "2026-11-27T00:00:00Z",
        "2026-11-27T00:00:00Z",
        "2026-11-26T00:00:00Z",
        "2026-11-26T00:00:00Z",
    ]

    # When run_time is None and head_played_date exceeds max_date, min_date caps cleanly at max_date
    future_head_rows = [["Track", "v1", "2020-01-01T00:00:00Z"]]
    clamp_history_rows_played_at(
        future_head_rows,
        played_at_idx=2,
        run_time=None,
        head_played_date=date(2099, 12, 31),
    )
    assert future_head_rows[0][2].endswith("T00:00:00Z")
    assert future_head_rows[0][2] != "2099-12-31T00:00:00Z"
