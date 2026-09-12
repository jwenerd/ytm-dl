import os
from datetime import datetime, timezone
import pytest
from src.mapping import (
    Mapping,
    SongSchema,
    HistorySchema,
    ArtistSchema,
    AlbumSchema,
    HomeSchema,
    get_run_id,
)


def test_get_run_id(monkeypatch):
    fixed_time = datetime(2026, 9, 12, 8, 30, 0, tzinfo=timezone.utc)

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
