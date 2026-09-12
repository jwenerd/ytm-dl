import os
import tempfile
from datetime import UTC, datetime

import yaml

from src.mapping import MoodMixTrackSchema
from src.mood_mixes import (
    compute_tracklist_hash,
    discover_chip_mixes,
    discover_home_mixes,
    discover_mood_chips,
    get_week_archive_folder,
    slugify,
    write_mix_files,
)


def test_slugify():
    assert slugify("Feel good") == "feel_good"
    assert slugify("Chill Mix 2") == "chill_mix_2"
    assert slugify("  Focus  Supermix!  ") == "focus_supermix"
    assert slugify("R&B / Soul & Funk") == "r_b_soul_funk"


def test_get_week_archive_folder():
    # Saturday, Sept 12, 2026 -> Monday, Sept 7, 2026
    dt_sat = datetime(2026, 9, 12, 10, 0, 0, tzinfo=UTC)
    assert get_week_archive_folder(dt_sat) == "2026_09_07"

    # Monday, Sept 7, 2026 -> Monday, Sept 7, 2026
    dt_mon = datetime(2026, 9, 7, 0, 0, 0, tzinfo=UTC)
    assert get_week_archive_folder(dt_mon) == "2026_09_07"

    # Sunday, Sept 13, 2026 -> Monday, Sept 7, 2026
    dt_sun = datetime(2026, 9, 13, 23, 59, 59, tzinfo=UTC)
    assert get_week_archive_folder(dt_sun) == "2026_09_07"


def test_compute_tracklist_hash():
    tracks1 = [{"videoId": "vid1"}, {"videoId": "vid2"}]
    tracks2 = [{"videoId": "vid1"}, {"videoId": "vid2"}]
    tracks3 = [{"videoId": "vid2"}, {"videoId": "vid1"}]
    tracks4 = [{"videoId": "vid1"}, {"videoId": "vid3"}]

    hash1 = compute_tracklist_hash(tracks1)
    hash2 = compute_tracklist_hash(tracks2)
    hash3 = compute_tracklist_hash(tracks3)
    hash4 = compute_tracklist_hash(tracks4)

    assert hash1 == hash2
    assert hash1 != hash3
    assert hash1 != hash4


def test_mood_mix_track_schema():
    schema = MoodMixTrackSchema()
    assert schema.keys == [
        "position",
        "title",
        "artists",
        "album",
        "duration",
        "duration_seconds",
        "videoId",
        "likeStatus",
        "inLibrary",
    ]

    sample_track = {
        "position": 1,
        "title": "Test Song",
        "artists": [{"name": "Artist One", "id": "A1"}, {"name": "Artist Two", "id": "A2"}],
        "album": {"name": "Test Album", "id": "AL1"},
        "duration": "3:45",
        "duration_seconds": 225,
        "videoId": "vid_abc123",
        "likeStatus": "LIKE",
        "inLibrary": True,
    }

    dumped = schema.dump(sample_track)
    assert dumped["position"] == 1
    assert dumped["title"] == "Test Song"
    assert dumped["artists"] == "Artist One, Artist Two"
    assert dumped["album"] == "Test Album"
    assert dumped["duration"] == "3:45"
    assert dumped["duration_seconds"] == 225
    assert dumped["videoId"] == "vid_abc123"
    assert dumped["likeStatus"] == "LIKE"
    assert str(dumped["inLibrary"]) == "True"


def test_discover_mood_chips():
    class MockClient:
        def _send_request(self, endpoint, body):
            return {
                "contents": {
                    "singleColumnBrowseResultsRenderer": {
                        "tabs": [
                            {
                                "tabRenderer": {
                                    "content": {
                                        "sectionListRenderer": {
                                            "header": {
                                                "chipCloudRenderer": {
                                                    "chips": [
                                                        {
                                                            "chipCloudChipRenderer": {
                                                                "text": {
                                                                    "runs": [{"text": "Podcasts"}]
                                                                },
                                                                "navigationEndpoint": {
                                                                    "browseEndpoint": {
                                                                        "params": "param_pod"
                                                                    }
                                                                },
                                                            }
                                                        },
                                                        {
                                                            "chipCloudChipRenderer": {
                                                                "text": {
                                                                    "runs": [{"text": "Relax"}]
                                                                },
                                                                "navigationEndpoint": {
                                                                    "browseEndpoint": {
                                                                        "params": "param_relax"
                                                                    }
                                                                },
                                                            }
                                                        },
                                                        {
                                                            "chipCloudChipRenderer": {
                                                                "text": {
                                                                    "runs": [{"text": "Focus"}]
                                                                },
                                                                "navigationEndpoint": {
                                                                    "browseEndpoint": {
                                                                        "params": "param_focus"
                                                                    }
                                                                },
                                                            }
                                                        },
                                                    ]
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        ]
                    }
                }
            }

    client = MockClient()
    chips = discover_mood_chips(client)
    assert len(chips) == 2
    assert chips == [("Relax", "param_relax"), ("Focus", "param_focus")]


def test_discover_chip_mixes():
    class MockClient:
        def _send_request(self, endpoint, body):
            return {
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
                                                                        {"text": "Mixed for you"}
                                                                    ]
                                                                }
                                                            }
                                                        },
                                                        "contents": [
                                                            {
                                                                "musicTwoRowItemRenderer": {
                                                                    "title": {
                                                                        "runs": [
                                                                            {"text": "Chill Mix 1"}
                                                                        ]
                                                                    },
                                                                    "subtitle": {
                                                                        "runs": [
                                                                            {
                                                                                "text": "Artist A, Artist B"
                                                                            }
                                                                        ]
                                                                    },
                                                                    "navigationEndpoint": {
                                                                        "browseEndpoint": {
                                                                            "browseId": "VLRDTMAK_123"
                                                                        }
                                                                    },
                                                                }
                                                            },
                                                            {
                                                                "musicTwoRowItemRenderer": {
                                                                    "title": {
                                                                        "runs": [
                                                                            {
                                                                                "text": "Chill Supermix"
                                                                            }
                                                                        ]
                                                                    },
                                                                    "subtitle": {
                                                                        "runs": [
                                                                            {
                                                                                "text": "Artist C, Artist D"
                                                                            }
                                                                        ]
                                                                    },
                                                                    "navigationEndpoint": {
                                                                        "watchEndpoint": {
                                                                            "playlistId": "RDTMAK_super"
                                                                        }
                                                                    },
                                                                }
                                                            },
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

    client = MockClient()
    mixes = discover_chip_mixes(client, "Relax", "param_relax")
    assert len(mixes) == 2
    assert mixes[0] == {
        "title": "Chill Mix 1",
        "mood_chip": "Relax",
        "playlist_id": "RDTMAK_123",
        "featured_artists": "Artist A, Artist B",
    }
    assert mixes[1] == {
        "title": "Chill Supermix",
        "mood_chip": "Relax",
        "playlist_id": "RDTMAK_super",
        "featured_artists": "Artist C, Artist D",
    }


def test_discover_home_mixes():
    class MockClient:
        def get_home(self, limit=25):
            return [
                {
                    "title": "Mixed for you",
                    "contents": [
                        {
                            "title": "My Supermix",
                            "playlistId": "RDTMAK_mysuper",
                            "description": "Top picks for you",
                        }
                    ],
                },
                {
                    "title": "Fresh finds, old favorites",
                    "contents": [
                        {
                            "title": "Discover Mix",
                            "playlistId": "RDTMAK_discover",
                            "description": "Weekly discoveries",
                        }
                    ],
                },
            ]

    client = MockClient()
    home_mixes = discover_home_mixes(client)
    assert len(home_mixes) == 2
    assert home_mixes[0]["title"] == "My Supermix"
    assert home_mixes[0]["playlist_id"] == "RDTMAK_mysuper"
    assert home_mixes[1]["title"] == "Discover Mix"
    assert home_mixes[1]["playlist_id"] == "RDTMAK_discover"


def test_write_mix_files_and_deduplication():
    with tempfile.TemporaryDirectory() as tmp_dir:
        schema = MoodMixTrackSchema()
        columns = schema.keys
        rows = [
            [1, "Song A", "Artist A", "Album A", "3:00", 180, "vidA", "LIKE", "True"],
            [2, "Song B", "Artist B", "Album B", "4:00", 240, "vidB", "INDIFFERENT", "False"],
        ]
        metadata = {
            "title": "Chill Mix 1",
            "mood_chip": "Relax",
            "playlist_id": "RDTMAK_chill1",
            "description": "Smooth relax tracks",
            "featured_artists": "Artist A, Artist B",
            "author": "YouTube Music",
            "year": "2026",
            "track_count": 2,
            "content_hash": "hash_version_1",
            "captured_at": "2026-09-12T04:00:00Z",
            "run_id": "local_123",
        }

        mix_data = {
            "metadata": metadata,
            "columns": columns,
            "rows": rows,
            "mood_slug": "relax",
            "mix_slug": "chill_mix_1",
        }

        # 1. Initial write for week 2026_09_07
        res1 = write_mix_files(mix_data, output_base_dir=tmp_dir, week_folder="2026_09_07")
        assert res1["history_written"] is True

        current_csv = os.path.join(tmp_dir, "current", "relax", "chill_mix_1.csv")
        current_yaml = os.path.join(tmp_dir, "current", "relax", "chill_mix_1.yaml")
        history_csv = os.path.join(tmp_dir, "history", "2026_09_07", "relax", "chill_mix_1.csv")
        history_yaml = os.path.join(tmp_dir, "history", "2026_09_07", "relax", "chill_mix_1.yaml")

        assert os.path.exists(current_csv)
        assert os.path.exists(current_yaml)
        assert os.path.exists(history_csv)
        assert os.path.exists(history_yaml)

        with open(current_yaml) as f:
            loaded_yaml = yaml.safe_load(f)
            assert loaded_yaml["title"] == "Chill Mix 1"
            assert loaded_yaml["content_hash"] == "hash_version_1"

        # 2. Second write during same week (e.g. daily run next day) -> skips rewriting history
        res2 = write_mix_files(mix_data, output_base_dir=tmp_dir, week_folder="2026_09_07")
        assert res2["history_written"] is False

        # 3. Third write for next week 2026_09_14 -> writes new weekly snapshot
        res3 = write_mix_files(mix_data, output_base_dir=tmp_dir, week_folder="2026_09_14")
        assert res3["history_written"] is True
        next_week_csv = os.path.join(tmp_dir, "history", "2026_09_14", "relax", "chill_mix_1.csv")
        assert os.path.exists(next_week_csv)
