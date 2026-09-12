import os
import tempfile

from src.mapping import MoodMixTrackSchema
from src.mood_mixes import (
    discover_chip_supermixes,
    discover_home_core_mixes,
    discover_mood_chips,
    is_supermix_or_core_mix,
    merge_catalog_tracks,
    read_existing_catalog,
    slugify,
)


def test_slugify():
    assert slugify("Feel good") == "feel_good"
    assert slugify("Chill Supermix") == "chill_supermix"
    assert slugify("  Focus  Supermix!  ") == "focus_supermix"
    assert slugify("Discover Mix") == "discover_mix"


def test_is_supermix_or_core_mix():
    # True cases
    assert is_supermix_or_core_mix("Chill Supermix") is True
    assert is_supermix_or_core_mix("Focus Supermix") is True
    assert is_supermix_or_core_mix("My Supermix") is True
    assert is_supermix_or_core_mix("Discover Mix") is True
    assert is_supermix_or_core_mix("New Release Mix") is True
    assert is_supermix_or_core_mix("Replay Mix") is True
    assert is_supermix_or_core_mix("Archive Mix") is True
    assert is_supermix_or_core_mix("Energy Supermix") is True

    # False cases (transient numbered sub-mixes or non-core mixes)
    assert is_supermix_or_core_mix("Chill Mix 1") is False
    assert is_supermix_or_core_mix("Chill Mix 2") is False
    assert is_supermix_or_core_mix("Focus Mix 3") is False
    assert is_supermix_or_core_mix("Ambient Techno Mix") is False


def test_mood_mix_track_schema():
    schema = MoodMixTrackSchema()
    assert schema.keys == [
        "videoId",
        "title",
        "artists",
        "album",
        "duration",
        "duration_seconds",
        "first_seen",
        "last_seen",
        "times_recommended",
        "latest_position",
        "likeStatus",
        "inLibrary",
    ]


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


def test_discover_chip_supermixes_filters_only_supermix():
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
    mixes = discover_chip_supermixes(client, "Relax", "param_relax")
    # Only Chill Supermix should be returned, Chill Mix 1 filtered out
    assert len(mixes) == 1
    assert mixes[0] == {
        "title": "Chill Supermix",
        "mood_chip": "Relax",
        "playlist_id": "RDTMAK_super",
        "featured_artists": "Artist C, Artist D",
    }


def test_discover_home_core_mixes():
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
                        },
                        {
                            "title": "Random Fleeting Mix",
                            "playlistId": "RDTMAK_random",
                            "description": "Fleeting mix",
                        },
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
    home_mixes = discover_home_core_mixes(client)
    assert len(home_mixes) == 2
    assert home_mixes[0]["title"] == "My Supermix"
    assert home_mixes[1]["title"] == "Discover Mix"


def test_merge_catalog_tracks():
    existing_catalog = {
        "vid1": {
            "videoId": "vid1",
            "title": "Song One",
            "artists": "Artist One",
            "album": "Album One",
            "duration": "3:00",
            "duration_seconds": "180",
            "first_seen": "2026-09-01T00:00:00Z",
            "last_seen": "2026-09-01T00:00:00Z",
            "times_recommended": "1",
            "latest_position": "10",
            "likeStatus": "INDIFFERENT",
            "inLibrary": "False",
        }
    }

    new_batch = [
        {
            "videoId": "vid2",
            "title": "Song Two (New)",
            "artists": [{"name": "Artist Two", "id": "A2"}],
            "album": {"name": "Album Two", "id": "AL2"},
            "duration": "4:00",
            "duration_seconds": 240,
            "likeStatus": "LIKE",
            "inLibrary": True,
        },
        {
            "videoId": "vid1",
            "title": "Song One",
            "artists": [{"name": "Artist One", "id": "A1"}],
            "album": {"name": "Album One", "id": "AL1"},
            "duration": "3:00",
            "duration_seconds": 180,
            "likeStatus": "LIKE",
            "inLibrary": True,
        },
    ]

    timestamp_run2 = "2026-09-12T04:30:00Z"
    merged, new_count, updated_count = merge_catalog_tracks(
        existing_catalog, new_batch, timestamp_run2
    )

    assert len(merged) == 2
    assert new_count == 1
    assert updated_count == 1

    # vid1 should have updated counts, updated timestamps, updated like status
    vid1_data = next(t for t in merged if t["videoId"] == "vid1")
    assert vid1_data["first_seen"] == "2026-09-01T00:00:00Z"
    assert vid1_data["last_seen"] == timestamp_run2
    assert vid1_data["times_recommended"] == "2"
    assert vid1_data["latest_position"] == "2"
    assert vid1_data["likeStatus"] == "LIKE"
    assert vid1_data["inLibrary"] == "True"

    # vid2 should be newly added with times_recommended = 1
    vid2_data = next(t for t in merged if t["videoId"] == "vid2")
    assert vid2_data["first_seen"] == timestamp_run2
    assert vid2_data["last_seen"] == timestamp_run2
    assert vid2_data["times_recommended"] == "1"
    assert vid2_data["latest_position"] == "1"
    assert vid2_data["artists"] == "Artist Two"
    assert vid2_data["album"] == "Album Two"


def test_read_existing_catalog_and_roundtrip():
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = os.path.join(tmp_dir, "test_mix.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            f.write(
                "videoId,title,artists,album,duration,duration_seconds,first_seen,last_seen,times_recommended,latest_position,likeStatus,inLibrary\n"
            )
            f.write(
                "v123,Track Title,Artist A,Album A,3:30,210,2026-09-01T00:00:00Z,2026-09-08T00:00:00Z,3,5,LIKE,True\n"
            )

        catalog = read_existing_catalog(csv_path)
        assert len(catalog) == 1
        assert "v123" in catalog
        assert catalog["v123"]["title"] == "Track Title"
        assert catalog["v123"]["times_recommended"] == "3"
