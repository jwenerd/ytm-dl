"""Unit tests for src/reports/aggregator.py"""

import os
from datetime import UTC, date, datetime

import pytest

from src.reports.aggregator import (
    aggregate_listening_telemetry,
    assemble_report_context,
    extract_radar_candidates,
    filter_rows_by_timestamp,
    format_duration,
    get_cadence_window,
    parse_iso_timestamp,
)


def test_parse_iso_timestamp():
    dt = parse_iso_timestamp("2026-10-18T20:44:59Z")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 10
    assert dt.day == 18
    assert dt.hour == 20
    assert dt.tzinfo == UTC

    # Non-Z offset
    dt2 = parse_iso_timestamp("2026-10-18T20:44:59+00:00")
    assert dt2 == dt

    # Invalid
    assert parse_iso_timestamp("") is None
    assert parse_iso_timestamp(None) is None
    assert parse_iso_timestamp("invalid-date") is None


def test_format_duration():
    assert format_duration(0) == "0m"
    assert format_duration(-10) == "0m"
    assert format_duration(45) == "0m"
    assert format_duration(65) == "1m"
    assert format_duration(3600) == "1h"
    assert format_duration(3665) == "1h 01m"
    assert format_duration(7200 + 840) == "2h 14m"


def test_get_cadence_window_daily(monkeypatch):
    monkeypatch.setenv("YTM_TIMEZONE", "America/Denver")
    target = date(2026, 10, 18)
    start, end = get_cadence_window("daily", target)
    # 04:00 MDT is 10:00 UTC
    assert start == datetime(2026, 10, 18, 10, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 19, 9, 59, 59, 999999, tzinfo=UTC)

    # With UTC timezone
    monkeypatch.setenv("YTM_TIMEZONE", "UTC")
    start_utc, end_utc = get_cadence_window("daily", target)
    assert start_utc == datetime(2026, 10, 18, 4, 0, 0, tzinfo=UTC)
    assert end_utc == datetime(2026, 10, 19, 3, 59, 59, 999999, tzinfo=UTC)


def test_get_cadence_window_weekly(monkeypatch):
    monkeypatch.setenv("YTM_TIMEZONE", "UTC")
    # 2026-10-18 is a Sunday
    target = date(2026, 10, 18)
    start, end = get_cadence_window("weekly", target)
    # Monday of that week is 2026-10-12 at 04:00 UTC
    assert start == datetime(2026, 10, 12, 4, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 19, 3, 59, 59, 999999, tzinfo=UTC)


def test_get_cadence_window_monthly(monkeypatch):
    monkeypatch.setenv("YTM_TIMEZONE", "UTC")
    target = date(2026, 10, 18)
    start, end = get_cadence_window("monthly", target)
    assert start == datetime(2026, 10, 1, 4, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 1, 3, 59, 59, 999999, tzinfo=UTC)

    # Edge case: December rollover
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
    assert len(filtered) == 2
    assert [r["id"] for r in filtered] == ["1", "2"]


def test_aggregate_listening_telemetry():
    # Empty
    empty_res = aggregate_listening_telemetry([])
    assert empty_res["total_tracks"] == 0
    assert empty_res["total_seconds"] == 0
    assert empty_res["unique_artists_count"] == 0

    history_slice = [
        {
            "title": "Shakedown Street",
            "artists": "Grateful Dead",
            "album": "Merriweather 85",
            "duration_seconds": "900",
            "inLibrary": "True",
            "played_at": "2026-10-18T22:00:00Z",  # evening
            "videoId": "vid-1",
        },
        {
            "title": "Shakedown Street",
            "artists": "Grateful Dead",
            "album": "Merriweather 85",
            "duration_seconds": "900",
            "inLibrary": "True",
            "played_at": "2026-10-18T22:30:00Z",  # evening (repeat!)
            "videoId": "vid-1",
        },
        {
            "title": "Looks Like Rain",
            "artists": "Grateful Dead",
            "album": "Merriweather 85",
            "duration_seconds": "480",
            "inLibrary": "False",
            "played_at": "2026-10-18T14:00:00Z",  # afternoon
            "videoId": "vid-2",
        },
    ]

    likes_slice = [
        {
            "title": "Honky Cat",
            "artists": "Elton John",
            "album": "Honky Chateau",
            "liked_at": "2026-10-18T20:44:59Z",
        }
    ]

    res = aggregate_listening_telemetry(history_slice, likes_slice)
    assert res["total_tracks"] == 3
    assert res["total_seconds"] == 2280
    assert res["total_duration_display"] == "38m"
    assert res["unique_artists_count"] == 1
    assert res["unique_albums_count"] == 1
    assert res["library_ratio_pct"] == 66.7
    assert "Grateful Dead" in res["catalog_anchor"]
    assert len(res["repeat_tracks"]) == 1
    assert res["repeat_tracks"][0]["title"] == "Shakedown Street"
    assert res["repeat_tracks"][0]["count"] == 2
    assert len(res["new_likes"]) == 1
    assert res["new_likes"][0]["title"] == "Honky Cat"


def test_extract_radar_candidates(tmp_path):
    output_dir = str(tmp_path)
    os.makedirs(os.path.join(output_dir, "home"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "mixes"), exist_ok=True)

    # 1. your_daily_discover
    ydd_file = os.path.join(output_dir, "home", "your_daily_discover.csv")
    with open(ydd_file, "w") as f:
        f.write(
            "id,type,title,artists,description,first_seen,last_seen,times_recommended,latest_position\n"
            "vid-10,Song,GREEN,Hiroshi Yoshimura,,2026-10-18T08:00:00Z,2026-10-18T08:00:00Z,1,1\n"
            "vid-1,Song,Already Played,Grateful Dead,,2026-10-18T08:00:00Z,2026-10-18T08:00:00Z,1,2\n"
        )

    # 2. discover_mix
    dm_file = os.path.join(output_dir, "mixes", "discover_mix.csv")
    with open(dm_file, "w") as f:
        f.write(
            "videoId,title,artists,album,duration,duration_seconds,first_seen,last_seen,times_recommended,latest_position,likeStatus,inLibrary\n"
            "vid-11,Tha,Aphex Twin,Selected Ambient Works,6:05,365,2026-10-15T08:00:00Z,2026-10-18T08:00:00Z,4,3,INDIFFERENT,False\n"
        )

    start = datetime(2026, 10, 18, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 10, 18, 23, 59, 59, tzinfo=UTC)

    history_artists = {"grateful dead"}
    played_video_ids = {"vid-1"}  # Already played

    cands = extract_radar_candidates(
        output_dir=output_dir,
        start_dt=start,
        end_dt=end,
        history_artists=history_artists,
        played_video_ids=played_video_ids,
        max_candidates=5,
    )

    # vid-1 should be excluded because it was played
    ids = [c["id"] for c in cands]
    assert "vid-1" not in ids
    assert "vid-10" in ids
    assert "vid-11" in ids

    # Check GREEN properties
    green = next(c for c in cands if c["id"] == "vid-10")
    assert green["is_new"] is True
    assert green["is_known_artist"] is False

    # Check Tha properties
    tha = next(c for c in cands if c["id"] == "vid-11")
    assert tha["is_new"] is False
    assert tha["times_recommended"] == 4


def test_assemble_report_context(tmp_path):
    output_dir = str(tmp_path)
    os.makedirs(os.path.join(output_dir, "home"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "mixes"), exist_ok=True)

    with open(os.path.join(output_dir, "history.csv"), "w") as f:
        f.write(
            "title,artists,album,inLibrary,likeStatus,duration,duration_seconds,videoId,played_at,run_id\n"
            "Song A,Artist A,Album A,True,LIKE,3:00,180,v1,2026-10-18T10:00:00Z,run1\n"
        )

    with open(os.path.join(output_dir, "liked_songs.csv"), "w") as f:
        f.write(
            "title,artists,album,duration,duration_seconds,videoId,liked_at,run_id\n"
            "Song A,Artist A,Album A,3:00,180,v1,2026-10-18T10:05:00Z,run1\n"
        )

    ctx = assemble_report_context(output_dir, "daily", date(2026, 10, 18))
    assert ctx["cadence"] == "daily"
    assert ctx["period_label"] == "2026-10-18"
    assert ctx["telemetry"]["total_tracks"] == 1
    assert ctx["telemetry"]["new_likes"][0]["title"] == "Song A"


def test_assemble_report_context_with_nocturnal_listening(monkeypatch, tmp_path):
    monkeypatch.setenv("YTM_TIMEZONE", "America/Denver")
    output_dir = str(tmp_path)
    os.makedirs(os.path.join(output_dir, "home"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "mixes"), exist_ok=True)

    # Oct 19 Daytime: Ott
    # Oct 19 Late Night (1:00 AM MDT): Dorothy Ashby
    # Oct 20 Daytime: Foxy Shazam
    with open(os.path.join(output_dir, "history.csv"), "w") as f:
        f.write(
            "title,artists,album,inLibrary,likeStatus,duration,duration_seconds,videoId,played_at,run_id\n"
            "Camping '76!,Ott,Heads,False,INDIFFERENT,4:00,240,v_ott,2026-10-19T00:00:00Z,run1\n"
            "Pawky,Dorothy Ashby,Hip Harp,False,LIKE,5:00,300,v_ashby,2026-10-19T00:00:00Z,run2\n"
            "Killin' It,Foxy Shazam,Foxy Shazam,False,LIKE,3:59,239,v_foxy,2026-10-20T00:00:00Z,run3\n"
        )

    # Likes: Dorothy Ashby liked at 1:19 AM MDT (07:19 UTC Oct 20) -> within Oct 19 listening day
    # Foxy Shazam liked at 2:00 PM MDT (20:00 UTC Oct 20) -> belongs to Oct 20
    with open(os.path.join(output_dir, "liked_songs.csv"), "w") as f:
        f.write(
            "title,artists,album,duration,duration_seconds,videoId,liked_at,run_id\n"
            "Pawky,Dorothy Ashby,Hip Harp,5:00,300,v_ashby,2026-10-20T07:19:00Z,run2\n"
            "Killin' It,Foxy Shazam,Foxy Shazam,3:59,239,v_foxy,2026-10-20T20:00:00Z,run3\n"
        )

    ctx = assemble_report_context(output_dir, "daily", date(2026, 10, 19))
    assert ctx["cadence"] == "daily"
    assert ctx["period_label"] == "2026-10-19"
    # Both Ott and Dorothy Ashby must be included, but Foxy Shazam excluded
    assert ctx["telemetry"]["total_tracks"] == 2
    artist_names = {t["artist"] for t in ctx["telemetry"]["top_artists"]}
    assert "Ott" in artist_names
    assert "Dorothy Ashby" in artist_names
    assert "Foxy Shazam" not in artist_names

    # Only Dorothy Ashby in new_likes for Oct 19
    assert len(ctx["telemetry"]["new_likes"]) == 1
    assert ctx["telemetry"]["new_likes"][0]["title"] == "Pawky"
