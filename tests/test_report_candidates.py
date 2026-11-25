"""Unit tests for src/reports/candidates.py."""

import os
from datetime import UTC, date, datetime

from src.reports.candidates import (
    extract_forgotten_favorites,
    extract_long_form_picks,
    extract_radar_candidates,
)


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
