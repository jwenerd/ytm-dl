"""Unit tests for src/reports/playlist.py."""

from unittest.mock import MagicMock, patch

from src.reports.playlist import (
    DEFAULT_PLAYLIST_TITLE,
    extract_featured_entity_ids,
    extract_playlist_video_ids,
    inject_playlist_banner,
    sync_daily_radar_playlist,
)


def test_extract_playlist_and_featured_entity_ids():
    # Exercises both colon-inside (**Long Spin:**) and colon-outside (- **Long Spin**:)
    md = """# Daily Listening Log: 2026-11-24
*Recorded via ytm-dl | Crate-Digger Daily*

## On the Turntable
- **Fresh Likes:** **[Ignored Like](https://music.youtube.com/watch?v=vid_like)** — Artist

## Today's Radar
- **[Sweet Echo](https://music.youtube.com/watch?v=vid_r1)** — Ezra Collective — *Tight keys.*
- **[Lavender Buds](https://music.youtube.com/watch?v=vid_r2)** — El Michels Affair — *Warm soul.*

## Deep Cuts & Long Spins
- **Liked & Forgotten**: **[Body And Soul](https://music.youtube.com/watch?v=vid_fg)** — Ryo Fukui — *Liked 8m ago.*
- **Full Album**: **[Sixteen Oceans](https://music.youtube.com/browse/MPREb_1)** — Four Tet — *Full LP.*
- **Long Spin**: **[In Dub Live](https://music.youtube.com/watch?v=vid_longset)** — Hallucinogen — *Full show.*
"""
    ctx = {
        "radar_candidates": [{"id": "vid_r1"}, {"id": "vid_r2"}],
        "forgotten_candidates": [{"id": "vid_fg"}],
        "long_form_picks": {"long_sets": [{"id": "vid_longset"}]},
    }
    song_ids = extract_playlist_video_ids(md, ctx)
    assert song_ids == ["vid_r1", "vid_r2", "vid_fg"]

    # Featured entity IDs include song picks PLUS Full Album MPREb_1 and Long Spin vid_longset
    all_featured = extract_featured_entity_ids(md, song_ids)
    assert all_featured == ["vid_r1", "vid_r2", "vid_fg", "MPREb_1", "vid_longset"]

    # Respects max_new cap and fallback when markdown contains no watch links
    assert extract_playlist_video_ids(md, ctx, max_new=2) == ["vid_r1", "vid_r2"]
    assert extract_playlist_video_ids("# Plain text report\n", ctx) == [
        "vid_r1",
        "vid_r2",
        "vid_fg",
    ]


def test_inject_playlist_banner_is_idempotent():
    md = "# Daily Listening Log: 2026-11-24\n*Recorded via ytm-dl | Crate-Digger Daily*\n\n**The Spin:** Nice.\n"
    assert inject_playlist_banner(md, "") == md

    injected = inject_playlist_banner(md, "https://music.youtube.com/playlist?list=PL_123")
    assert (
        "**[▶ Play Rolling Daily Radar Playlist](https://music.youtube.com/playlist?list=PL_123)**"
        in injected
    )

    updated = inject_playlist_banner(injected, "https://music.youtube.com/playlist?list=PL_456")
    assert updated.count("Play Rolling Daily Radar Playlist") == 1
    assert "PL_456" in updated
    assert "PL_123" not in updated


def test_sync_daily_radar_playlist_create_rolling_noop_and_recovery():
    meta: dict = {}

    assert sync_daily_radar_playlist([], "2026-11-24", meta) is None

    with patch("src.reports.playlist.get_thread_client", side_effect=RuntimeError("No auth")):
        assert sync_daily_radar_playlist(["v1"], "2026-11-24", meta) is None

    bad_client = MagicMock()
    bad_client.get_library_playlists.return_value = []
    bad_client.create_playlist.return_value = {"error": "quota"}
    assert sync_daily_radar_playlist(["v1"], "2026-11-24", meta, client=bad_client) is None

    # Discovers existing library playlist by title when meta is empty
    discover_client = MagicMock()
    discover_client.get_library_playlists.return_value = [
        {"title": DEFAULT_PLAYLIST_TITLE, "playlistId": "PL_FOUND"}
    ]
    discover_client.get_playlist.return_value = {"tracks": []}
    meta_discover: dict = {}
    found_url = sync_daily_radar_playlist(
        ["v1"], "2026-11-24", meta_discover, client=discover_client
    )
    assert found_url == "https://music.youtube.com/playlist?list=PL_FOUND"
    discover_client.create_playlist.assert_not_called()

    # First-time creation
    client = MagicMock()
    client.get_library_playlists.return_value = [{"title": "Other", "playlistId": "PL_OTHER"}]
    client.create_playlist.return_value = "PL_RADAR_1"
    url = sync_daily_radar_playlist(["v1", "v2", "v1"], "2026-11-23", meta, client=client)
    assert url == "https://music.youtube.com/playlist?list=PL_RADAR_1"
    assert meta["playlist"]["video_ids"] == ["v1", "v2"]

    # Next-day rolling update (prepends new, deduplicates, caps at max_tracks=4)
    client.get_playlist.return_value = {
        "tracks": [
            {"videoId": "v1", "setVideoId": "sv1"},
            {"videoId": "v2", "setVideoId": "sv2"},
            {"videoId": "v3", "setVideoId": "sv3"},
        ]
    }
    url2 = sync_daily_radar_playlist(
        ["v_new1", "v_new2", "v2"],
        "2026-11-24",
        meta,
        client=client,
        max_tracks=4,
    )
    assert url2 == "https://music.youtube.com/playlist?list=PL_RADAR_1"
    client.add_playlist_items.assert_called_once_with(
        "PL_RADAR_1",
        videoIds=["v_new1", "v_new2", "v2", "v1"],
        duplicates=False,
    )

    # Same-period nocturnal refresh with identical picks -> NO-OP short-circuit (0 destructive calls!)
    client.remove_playlist_items.reset_mock()
    client.add_playlist_items.reset_mock()
    client.get_playlist.return_value = {
        "tracks": [
            {"videoId": "v_new1", "setVideoId": "sv1"},
            {"videoId": "v_new2", "setVideoId": "sv2"},
            {"videoId": "v2", "setVideoId": "sv4"},
            {"videoId": "v1", "setVideoId": "sv3"},
        ]
    }
    sync_daily_radar_playlist(
        ["v_new1", "v_new2", "v2"],
        "2026-11-24",
        meta,
        client=client,
        max_tracks=4,
    )
    client.remove_playlist_items.assert_not_called()
    client.add_playlist_items.assert_not_called()

    # Same-period nocturnal refresh with updated picks -> replaces earlier 2026-11-24 picks instead of stacking
    sync_daily_radar_playlist(
        ["v_refresh"],
        "2026-11-24",
        meta,
        client=client,
        max_tracks=4,
    )
    client.add_playlist_items.assert_called_once_with(
        "PL_RADAR_1",
        videoIds=["v_refresh", "v1"],
        duplicates=False,
    )

    # API error during update preserves existing URL without crashing
    client.get_playlist.side_effect = RuntimeError("API glitch")
    fallback_url = sync_daily_radar_playlist(["v9"], "2026-11-25", meta, client=client)
    assert fallback_url == "https://music.youtube.com/playlist?list=PL_RADAR_1"
