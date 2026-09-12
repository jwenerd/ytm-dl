from datetime import UTC, datetime
from unittest.mock import MagicMock

import yaml

from src.home_catalog import (
    _make_home_item_row,
    _resolve_item_id,
    _resolve_item_type,
    _update_home_item_row,
    fetch_rich_home_sections,
    sync_all_home_shelves,
    sync_home_shelf,
)


def test_resolve_item_id_and_type():
    # Song
    assert _resolve_item_id({"videoId": "song_123"}) == "song_123"
    assert _resolve_item_type({"videoId": "song_123"}) == "Song"

    # Video
    assert (
        _resolve_item_type({"videoId": "vid_123", "videoType": "MUSIC_VIDEO_TYPE_UGC"}) == "Video"
    )

    # Playlist (stripping VL if present)
    assert _resolve_item_id({"playlistId": "VLPL12345"}) == "PL12345"
    assert _resolve_item_type({"playlistId": "PL12345"}) == "Playlist"

    # Podcast
    assert _resolve_item_id({"podcastId": "pod_123"}) == "pod_123"
    assert _resolve_item_type({"podcastId": "pod_123"}) == "Podcast"

    # Album
    assert _resolve_item_id({"browseId": "MPREb_123"}) == "MPREb_123"
    assert _resolve_item_type({"browseId": "MPREb_123"}) == "Album"

    # Artist
    assert _resolve_item_id({"browseId": "UC12345"}) == "UC12345"
    assert _resolve_item_type({"browseId": "UC12345"}) == "Artist"

    # Explicit type override
    assert _resolve_item_type({"type": "Single", "browseId": "MPREb_123"}) == "Single"


def test_make_home_item_row():
    item = {
        "videoId": "vid1",
        "title": "Summer Song",
        "artists": [{"name": "Artist 1"}, {"name": "Artist 2"}],
        "description": "Trending now",
    }
    row = _make_home_item_row(item, pos=1, captured_at="2026-09-12T10:00:00Z")

    assert row["id"] == "vid1"
    assert row["type"] == "Song"
    assert row["title"] == "Summer Song"
    assert row["artists"] == "Artist 1, Artist 2"
    assert row["description"] == "Trending now"
    assert row["first_seen"] == "2026-09-12T10:00:00Z"
    assert row["last_seen"] == "2026-09-12T10:00:00Z"
    assert row["times_recommended"] == "1"
    assert row["latest_position"] == "1"


def test_update_home_item_row_non_destructive():
    row = {
        "id": "vid1",
        "type": "Song",
        "title": "Summer Song",
        "artists": "",
        "description": "",
        "first_seen": "2026-09-01T00:00:00Z",
        "last_seen": "2026-09-01T00:00:00Z",
        "times_recommended": "1",
        "latest_position": "5",
    }
    item = {
        "videoId": "vid1",
        "artists": [{"name": "Artist 1"}],
        "description": "Updated subtitle",
    }
    _update_home_item_row(row, item)

    assert row["artists"] == "Artist 1"
    assert row["description"] == "Updated subtitle"


def test_fetch_rich_home_sections():
    mock_client = MagicMock()
    mock_client._send_request.return_value = {
        "contents": {
            "singleColumnBrowseResultsRenderer": {
                "tabs": [
                    {
                        "tabRenderer": {
                            "content": {
                                "sectionListRenderer": {
                                    "contents": [
                                        {
                                            "musicCarouselShelfRenderer": {
                                                "header": {
                                                    "musicCarouselShelfBasicHeaderRenderer": {
                                                        "title": {
                                                            "runs": [
                                                                {"text": "That summer feeling"}
                                                            ]
                                                        },
                                                        "strapline": {
                                                            "runs": [
                                                                {"text": "SOUNDTRACK THE SEASON"}
                                                            ]
                                                        },
                                                        "thumbnail": {
                                                            "musicThumbnailRenderer": {
                                                                "thumbnail": {
                                                                    "thumbnails": [
                                                                        {"url": "https://thumb/1"}
                                                                    ]
                                                                }
                                                            }
                                                        },
                                                    }
                                                },
                                                "itemSize": "COLLECTION_STYLE_ITEM_SIZE_MEDIUM",
                                                "contents": [
                                                    {
                                                        "musicTwoRowItemRenderer": {
                                                            "title": {
                                                                "runs": [{"text": "Summer Vibes"}]
                                                            },
                                                            "navigationEndpoint": {
                                                                "watchEndpoint": {
                                                                    "playlistId": "PLsummer"
                                                                }
                                                            },
                                                        }
                                                    }
                                                ],
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        }
    }

    sections = fetch_rich_home_sections(mock_client, limit=10)
    assert len(sections) == 1
    sec = sections[0]
    assert sec["title"] == "That summer feeling"
    assert sec["strapline"] == "SOUNDTRACK THE SEASON"
    assert sec["thumbnail"] == "https://thumb/1"
    assert sec["item_size"] == "COLLECTION_STYLE_ITEM_SIZE_MEDIUM"
    assert len(sec["contents"]) == 1


def test_sync_home_shelf_multi_run_lifecycle(tmp_path):
    output_dir = str(tmp_path / "home")
    time_run1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
    time_run2 = datetime(2026, 9, 12, 12, 0, 0, tzinfo=UTC)

    shelf_run1 = {
        "title": "That summer feeling",
        "strapline": "SOUNDTRACK THE SEASON",
        "thumbnail": "https://thumb/avatar.jpg",
        "browse_id": None,
        "item_size": "COLLECTION_STYLE_ITEM_SIZE_MEDIUM",
        "contents": [
            {"playlistId": "PL_1", "title": "Summer 1", "description": "Hits"},
            {"playlistId": "PL_2", "title": "Summer 2", "description": "Chill"},
        ],
    }

    # Run 1: initial creation
    res1 = sync_home_shelf(shelf_run1, output_dir, time_run1, "gh-1")
    assert res1["slug"] == "that_summer_feeling"
    assert res1["total_items"] == 2
    assert res1["new_items"] == 2
    assert res1["updated_items"] == 0

    yaml_file = tmp_path / "meta" / "home" / "that_summer_feeling.yaml"
    assert not (tmp_path / "home" / "that_summer_feeling.yaml").exists()
    with open(yaml_file) as f:
        meta1 = yaml.safe_load(f)
    assert meta1["title"] == "That summer feeling"
    assert meta1["strapline"] == "SOUNDTRACK THE SEASON"
    assert meta1["first_captured"] == "2026-09-01T10:00:00Z"
    assert meta1["total_items"] == 2

    # Run 2: PL_3 (new), PL_1 (repeat in position 2)
    shelf_run2 = {
        "title": "That summer feeling",
        "strapline": "SOUNDTRACK THE SEASON",
        "thumbnail": "https://thumb/avatar.jpg",
        "contents": [
            {"playlistId": "PL_3", "title": "Summer 3", "description": "New Summer"},
            {"playlistId": "PL_1", "title": "Summer 1", "description": "Hits"},
        ],
    }
    res2 = sync_home_shelf(shelf_run2, output_dir, time_run2, "gh-2")
    assert res2["total_items"] == 3
    assert res2["new_items"] == 1
    assert res2["updated_items"] == 1

    # Verify CSV line order: PL_3 is at index 0 (line 2), PL_1 at index 1, PL_2 at index 2
    csv_file = tmp_path / "home" / "that_summer_feeling.csv"
    with open(csv_file) as f:
        lines = [line.strip() for line in f.readlines()]

    assert lines[0].startswith("id,type,title")
    assert lines[1].startswith("PL_3,Playlist,Summer 3")
    assert lines[2].startswith("PL_1,Playlist,Summer 1")
    assert lines[3].startswith("PL_2,Playlist,Summer 2")

    # Verify times_recommended and positions for PL_1
    pl1_parts = lines[2].split(",")
    # latest_position is the last column
    assert pl1_parts[-1] == "2"  # position in run2
    assert pl1_parts[-2] == "2"  # times_recommended = 2

    # Verify YAML preserves first_captured
    with open(yaml_file) as f:
        meta2 = yaml.safe_load(f)
    assert meta2["first_captured"] == "2026-09-01T10:00:00Z"
    assert meta2["last_captured"] == "2026-09-12T12:00:00Z"
    assert meta2["total_items"] == 3


def test_sync_all_home_shelves_orchestration(tmp_path, monkeypatch):
    output_dir = str(tmp_path / "home")
    fixed_time = datetime(2026, 9, 12, 10, 0, 0, tzinfo=UTC)

    mock_client = MagicMock()
    mock_client._send_request.return_value = {
        "contents": {
            "singleColumnBrowseResultsRenderer": {
                "tabs": [
                    {
                        "tabRenderer": {
                            "content": {
                                "sectionListRenderer": {
                                    "contents": [
                                        {
                                            "musicCarouselShelfRenderer": {
                                                "header": {
                                                    "musicCarouselShelfBasicHeaderRenderer": {
                                                        "title": {
                                                            "runs": [{"text": "Quick picks"}]
                                                        },
                                                    }
                                                },
                                                "contents": [
                                                    {
                                                        "musicTwoRowItemRenderer": {
                                                            "title": {
                                                                "runs": [{"text": "Quick Track 1"}]
                                                            },
                                                            "navigationEndpoint": {
                                                                "watchEndpoint": {
                                                                    "videoId": "qvid1"
                                                                }
                                                            },
                                                        }
                                                    }
                                                ],
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        }
    }

    monkeypatch.setattr("src.home_catalog.get_thread_client", lambda: mock_client)

    results = sync_all_home_shelves(
        output_base_dir=output_dir,
        max_workers=2,
        run_time=fixed_time,
        run_id="gh-123",
    )

    assert len(results) == 1
    assert results[0]["slug"] == "quick_picks"
    assert results[0]["new_items"] == 1

    assert (tmp_path / "home" / "quick_picks.csv").exists()
    assert (tmp_path / "meta" / "home" / "quick_picks.yaml").exists()
    assert not (tmp_path / "home" / "quick_picks.yaml").exists()
