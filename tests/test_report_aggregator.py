"""Unit tests for src/reports/aggregator.py"""

import os
from datetime import UTC, date, datetime

import pytest

from src.reports.aggregator import (
    aggregate_listening_telemetry,
    assemble_report_context,
    clean_and_split_artists,
    clean_artist_display,
    extract_forgotten_favorites,
    extract_long_form_picks,
    extract_radar_candidates,
    filter_rows_by_timestamp,
    format_duration,
    format_period_label,
    get_cadence_window,
    parse_iso_timestamp,
    read_csv_rows,
    ytm_entity_url,
    ytm_watch_url,
)


def test_url_and_artist_helpers():
    assert ytm_watch_url(None) == ""
    assert ytm_watch_url("") == ""
    assert ytm_watch_url("abc123XYZ") == "https://music.youtube.com/watch?v=abc123XYZ"

    assert ytm_entity_url("") == ""
    assert ytm_entity_url("MPREb_album1") == "https://music.youtube.com/browse/MPREb_album1"
    assert ytm_entity_url("PLlist1") == "https://music.youtube.com/playlist?list=PLlist1"
    assert ytm_entity_url("VLPLlist2") == "https://music.youtube.com/playlist?list=PLlist2"
    assert ytm_entity_url("vid999") == "https://music.youtube.com/watch?v=vid999"

    assert clean_and_split_artists(None) == []
    assert clean_and_split_artists("1.2M views, Le Mellotron, Bonobo, bonobo") == [
        "Le Mellotron",
        "Bonobo",
    ]
    assert clean_artist_display("850K views, Acid Pauli") == "Acid Pauli"
    assert clean_artist_display("1.2M views") == "1.2M views"


def test_parse_iso_timestamp_and_csv_errors(tmp_path):
    dt = parse_iso_timestamp("2026-10-18T20:44:59Z")
    assert dt == datetime(2026, 10, 18, 20, 44, 59, tzinfo=UTC)
    assert parse_iso_timestamp("2026-10-18T20:44:59") == dt
    assert parse_iso_timestamp("2026-10-18T20:44:59+00:00") == dt
    assert parse_iso_timestamp("") is None
    assert parse_iso_timestamp(None) is None
    assert parse_iso_timestamp("invalid-date") is None

    assert read_csv_rows(str(tmp_path / "missing.csv")) == []


def test_format_duration_and_period_labels(monkeypatch):
    monkeypatch.setenv("YTM_TIMEZONE", "UTC")
    assert format_duration(0) == "0m"
    assert format_duration(-10) == "0m"
    assert format_duration(65) == "1m"
    assert format_duration(3600) == "1h"
    assert format_duration(3665) == "1h 01m"

    s = datetime(2026, 10, 18, 4, 0, tzinfo=UTC)
    e = datetime(2026, 10, 19, 3, 59, tzinfo=UTC)
    assert format_period_label("daily", s, e, None) == "2026-10-18"
    assert "2026-W" in format_period_label("weekly", s, e)
    assert format_period_label("monthly", s, e) == "October 2026"
    assert format_period_label("custom", s, e) == "2026-10-18"


def test_get_cadence_window_variants(monkeypatch):
    monkeypatch.setenv("YTM_TIMEZONE", "America/Denver")
    target = date(2026, 10, 18)
    start, end = get_cadence_window("daily", target)
    assert start == datetime(2026, 10, 18, 10, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 19, 9, 59, 59, 999999, tzinfo=UTC)

    monkeypatch.setenv("YTM_TIMEZONE", "UTC")
    # Default target_date=None and naive datetime handling
    s_none, _ = get_cadence_window("daily", None)
    assert s_none.tzinfo == UTC
    s_dt, _ = get_cadence_window("daily", datetime(2026, 10, 18, 12, 0))
    assert s_dt == datetime(2026, 10, 18, 4, 0, 0, tzinfo=UTC)

    start_w, end_w = get_cadence_window("weekly", target)
    assert start_w == datetime(2026, 10, 12, 4, 0, 0, tzinfo=UTC)
    assert end_w == datetime(2026, 10, 19, 3, 59, 59, 999999, tzinfo=UTC)

    start_m, end_m = get_cadence_window("monthly", target)
    assert start_m == datetime(2026, 10, 1, 4, 0, 0, tzinfo=UTC)
    assert end_m == datetime(2026, 11, 1, 3, 59, 59, 999999, tzinfo=UTC)

    start_dec, end_dec = get_cadence_window("monthly", date(2026, 12, 5))
    assert start_dec == datetime(2026, 12, 1, 4, 0, 0, tzinfo=UTC)
    assert end_dec == datetime(2027, 1, 1, 3, 59, 59, 999999, tzinfo=UTC)

    with pytest.raises(ValueError, match="Unsupported cadence"):
        get_cadence_window("yearly", target)


def test_filter_rows_by_timestamp():
    rows = [
        {"id": "1", "ts": "2026-10-18T10:00:00Z"},
        {"id": "2", "ts": "2026-10-18T15:00:00Z"},
        {"id": "3", "ts": "2026-10-19T02:00:00Z"},
    ]
    start = datetime(2026, 10, 18, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 10, 18, 23, 59, 59, tzinfo=UTC)
    filtered = filter_rows_by_timestamp(rows, "ts", start, end)
    assert [r["id"] for r in filtered] == ["1", "2"]


def test_aggregate_listening_telemetry():
    empty_res = aggregate_listening_telemetry([])
    assert empty_res["total_tracks"] == 0
    assert empty_res["new_artists_count"] == 0
    assert "library_ratio_pct" not in empty_res

    history_slice = [
        {
            "title": "Shakedown Street",
            "artists": "Grateful Dead",
            "album": "Merriweather 85 Live",
            "duration_seconds": "900",
            "likeStatus": "LIKE",
            "played_at": "2026-10-18T22:00:00Z",
            "videoId": "vid-1",
        },
        {
            "title": "Shakedown Street",
            "artists": "Grateful Dead",
            "album": "Merriweather 85 Live",
            "duration_seconds": "bad-int",
            "likeStatus": "INDIFFERENT",
            "played_at": "2026-10-18T22:30:00Z",
            "videoId": "vid-1",
        },
        {
            "title": "The World Is Waiting for the Sunrise",
            "artists": "Chet Atkins, Les Paul",
            "album": "Chester & Lester",
            "duration_seconds": "180",
            "likeStatus": "LIKE",
            "played_at": "2026-10-18T14:00:00Z",
            "videoId": "vid-2",
        },
        {
            "title": "The World Is Waiting for the Sunrise",
            "artists": "1.2M views, George Lewis",
            "album": "New Orleans Stompers",
            "duration_seconds": "200",
            "likeStatus": "INDIFFERENT",
            "played_at": "2026-10-18T15:00:00Z",
            "videoId": "vid-3",
        },
    ]

    likes_slice = [
        {
            "title": "Honky Cat",
            "artists": "Elton John",
            "album": "Honky Chateau",
            "videoId": "vid-like-1",
            "liked_at": "2026-10-18T20:44:59Z",
        }
    ]

    res = aggregate_listening_telemetry(
        history_slice,
        likes_slice,
        prior_artists={"grateful dead", "chet atkins"},
    )
    assert res["total_tracks"] == 4
    assert res["total_seconds"] == 1280
    assert "library_ratio_pct" not in res
    assert res["unique_artists_count"] == 4  # Grateful Dead, Chet Atkins, Les Paul, George Lewis
    assert res["new_artists_count"] == 2
    assert set(res["new_artists"]) == {"Les Paul", "George Lewis"}
    assert res["live_track_count"] == 2
    assert res["liked_plays_count"] == 2
    assert res["repeat_tracks"][0]["url"] == "https://music.youtube.com/watch?v=vid-1"
    assert len(res["version_collisions"]) == 1
    assert res["version_collisions"][0]["title"] == "The World Is Waiting for the Sunrise"
    assert res["new_likes"][0]["url"] == "https://music.youtube.com/watch?v=vid-like-1"


def test_extract_radar_candidates_filters_playlists_and_exclusions(tmp_path):
    output_dir = str(tmp_path)
    os.makedirs(os.path.join(output_dir, "home"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "mixes"), exist_ok=True)

    with open(os.path.join(output_dir, "home", "your_daily_discover.csv"), "w") as f:
        f.write(
            "id,type,title,artists,description,first_seen,last_seen,times_recommended,latest_position\n"
            "RDCLAK_mix,Playlist,Discover Mix,Traffic,,2026-10-18T08:00:00Z,2026-10-18T08:00:00Z,1,1\n"
            "vid-10,Song,GREEN,Hiroshi Yoshimura,,2026-10-18T08:00:00Z,2026-10-18T08:00:00Z,bad,bad\n"
            "vid-empty,Song,,,desc,2026-10-18T08:00:00Z,2026-10-18T08:00:00Z,1,1\n"
            "vid-old,Song,Stale Song,Artist,,2026-09-01T08:00:00Z,2026-09-02T08:00:00Z,1,5\n"
            "vid-recent,Song,Pitched Yesterday,Artist,,2026-10-18T08:00:00Z,2026-10-18T08:00:00Z,1,2\n"
            "vid-1,Song,Already Played,Grateful Dead,,2026-10-18T08:00:00Z,2026-10-18T08:00:00Z,1,2\n"
        )

    with open(os.path.join(output_dir, "mixes", "discover_mix.csv"), "w") as f:
        f.write(
            "videoId,title,artists,album,duration,duration_seconds,first_seen,last_seen,times_recommended,latest_position,likeStatus,inLibrary\n"
            "vid-11,Tha,Aphex Twin,SAW,6:05,365,2026-10-15T08:00:00Z,2026-10-18T08:00:00Z,4,3,INDIFFERENT,False\n"
        )

    start = datetime(2026, 10, 18, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 10, 18, 23, 59, 59, tzinfo=UTC)

    cands = extract_radar_candidates(
        output_dir=output_dir,
        start_dt=start,
        end_dt=end,
        history_artists={"grateful dead"},
        played_video_ids={"vid-1"},
        excluded_ids={"vid-recent"},
        max_candidates=1,
    )
    assert len(cands) == 1
    assert cands[0]["id"] == "vid-10"
    assert cands[0]["url"] == "https://music.youtube.com/watch?v=vid-10"


def test_extract_forgotten_and_long_form_picks(tmp_path):
    output_dir = str(tmp_path)
    os.makedirs(os.path.join(output_dir, "home"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "mixes"), exist_ok=True)

    all_history = [
        {"videoId": "", "played_at": ""},
        {"videoId": "v-future", "played_at": "2026-11-01T00:00:00Z"},
        {"videoId": "v-recent", "played_at": "2026-10-10T00:00:00Z"},
        {"videoId": "v-old-spun", "played_at": "2026-03-01T00:00:00Z"},
    ]
    all_likes = [
        {
            "videoId": "v-recent",
            "title": "Played Recently",
            "artists": "A",
            "liked_at": "2026-01-01T00:00:00Z",
        },
        {
            "videoId": "v-new-like",
            "title": "Liked Yesterday",
            "artists": "B",
            "liked_at": "2026-10-17T00:00:00Z",
        },
        {
            "videoId": "v-old-spun",
            "title": "Dusty Gem",
            "artists": "Ryo Fukui",
            "liked_at": "2026-01-15T00:00:00Z",
        },
        {
            "videoId": "v-old-unspun",
            "title": "Never Spun",
            "artists": "Bonobo",
            "liked_at": "2026-02-01T00:00:00Z",
        },
    ]

    with open(os.path.join(output_dir, "home", "forgotten_favorites.csv"), "w") as f:
        f.write(
            "id,type,title,artists,description,first_seen,last_seen,times_recommended,latest_position\n"
            "PL_1,Playlist,My Playlist,Me,,2026-10-18T00:00:00Z,2026-10-18T00:00:00Z,1,1\n"
            "v-recent,Song,Recently Spun,Artist,,2026-10-18T00:00:00Z,2026-10-18T00:00:00Z,1,1\n"
            "v-shelf-gem,Song,Shelf Gem,Loscil,,2026-10-18T00:00:00Z,2026-10-18T00:00:00Z,1,2\n"
        )

    with open(os.path.join(output_dir, "mixes", "archive_mix.csv"), "w") as f:
        f.write(
            "videoId,title,artists,album,duration,duration_seconds,first_seen,last_seen,times_recommended,latest_position,likeStatus,inLibrary\n"
            "v-archive,Black Tusk,loscil,arc,10:00,600,2026-10-18T00:00:00Z,2026-10-18T00:00:00Z,2,1,LIKE,False\n"
        )

    forgotten = extract_forgotten_favorites(
        output_dir=output_dir,
        all_history=all_history,
        all_likes=all_likes,
        target_date=date(2026, 10, 18),
        max_candidates=3,
    )
    assert len(forgotten) == 3
    assert forgotten[0]["id"] == "v-old-spun"
    assert "last spun 2026-03-01" in forgotten[0]["note"]
    assert "unplayed since" in forgotten[1]["note"]

    # Test max_candidates*2 break in liked_songs
    many_likes = [
        {
            "videoId": f"v-lk-{i}",
            "title": f"T{i}",
            "artists": "A",
            "liked_at": "2026-01-01T00:00:00Z",
        }
        for i in range(5)
    ]
    fg_capped = extract_forgotten_favorites(
        output_dir, [], many_likes, date(2026, 10, 18), max_candidates=1
    )
    assert len(fg_capped) == 1

    # Long-form picks
    with open(os.path.join(output_dir, "home", "albums_for_you.csv"), "w") as f:
        f.write(
            "id,type,title,artists,description,first_seen,last_seen,times_recommended,latest_position\n"
            "PL_skip,Playlist,Not Album,Artist,,2026-10-18T00:00:00Z,2026-10-18T00:00:00Z,1,1\n"
            ",Album,Missing Id,Artist,,2026-10-18T00:00:00Z,2026-10-18T00:00:00Z,1,1\n"
            "MPREb_1,Album,Sixteen Oceans,Four Tet,,2026-10-18T00:00:00Z,2026-10-18T00:00:00Z,1,1\n"
            "MPREb_2,Album,II,Moderat,,2026-10-18T00:00:00Z,2026-10-18T00:00:00Z,1,2\n"
        )
    with open(os.path.join(output_dir, "home", "long_listens.csv"), "w") as f:
        f.write(
            "id,type,title,artists,description,first_seen,last_seen,times_recommended,latest_position\n"
            "PL_skip,Playlist,Skip List,Artist,,2026-10-18T00:00:00Z,2026-10-18T00:00:00Z,1,1\n"
            ",Video,No ID,Artist,,2026-10-18T00:00:00Z,2026-10-18T00:00:00Z,1,1\n"
            "v-set-1,Video,In Dub Live [FULL ALBUM],Hallucinogen,,2026-10-18T00:00:00Z,2026-10-18T00:00:00Z,1,2\n"
        )

    lf = extract_long_form_picks(output_dir, played_video_ids=set(), max_albums=1, max_sets=1)
    assert len(lf["albums"]) == 1
    assert lf["albums"][0]["url"] == "https://music.youtube.com/browse/MPREb_1"
    assert len(lf["long_sets"]) == 1
    assert lf["long_sets"][0]["url"] == "https://music.youtube.com/watch?v=v-set-1"


def test_assemble_report_context_and_new_artists(monkeypatch, tmp_path):
    monkeypatch.setenv("YTM_TIMEZONE", "America/Denver")
    output_dir = str(tmp_path)
    os.makedirs(os.path.join(output_dir, "home"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "mixes"), exist_ok=True)

    with open(os.path.join(output_dir, "history.csv"), "w") as f:
        f.write(
            "title,artists,album,inLibrary,likeStatus,duration,duration_seconds,videoId,played_at,run_id\n"
            "Old Favorite,Ott,Skylon,False,LIKE,4:00,240,v_old,2026-10-10T00:00:00Z,run0\n"
            "Camping '76!,Ott,Heads,False,INDIFFERENT,4:00,240,v_ott,2026-10-19T00:00:00Z,run1\n"
            "Pawky,Dorothy Ashby,Hip Harp,False,LIKE,5:00,300,v_ashby,2026-10-19T00:00:00Z,run2\n"
            "Killin' It,Foxy Shazam,Foxy Shazam,False,LIKE,3:59,239,v_foxy,2026-10-20T00:00:00Z,run3\n"
        )

    with open(os.path.join(output_dir, "liked_songs.csv"), "w") as f:
        f.write(
            "title,artists,album,duration,duration_seconds,videoId,liked_at,run_id\n"
            "Pawky,Dorothy Ashby,Hip Harp,5:00,300,v_ashby,2026-10-20T07:19:00Z,run2\n"
        )

    ctx = assemble_report_context(output_dir, "daily", date(2026, 10, 19))
    assert ctx["telemetry"]["total_tracks"] == 2
    assert ctx["telemetry"]["new_artists_count"] == 1
    assert ctx["telemetry"]["new_artists"] == ["Dorothy Ashby"]
    assert "forgotten_candidates" in ctx
    assert "long_form_picks" in ctx

    # Also test target_date=None and naive datetime inputs
    ctx_dt = assemble_report_context(output_dir, "daily", datetime(2026, 10, 19, 18, 0))
    assert ctx_dt["period_label"] == "2026-10-19"
    ctx_default = assemble_report_context(output_dir, "daily", None)
    assert ctx_default["cadence"] == "daily"
