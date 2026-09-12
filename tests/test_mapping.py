import pytest
from src.mapping import Mapping, SongSchema, HistorySchema, ArtistSchema, AlbumSchema, HomeSchema


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
