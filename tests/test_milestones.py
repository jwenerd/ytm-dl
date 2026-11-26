"""Unit tests for src/reports/milestones.py."""

import os
from datetime import date, datetime, timedelta

from src.reports.artist_tags import write_artist_tags
from src.reports.milestones import (
    _crossed,
    _next_tier,
    _prev_tier,
    _safe_duration,
    _step_ratio,
    detect_obsessions,
    evaluate_milestones,
    get_period_milestones,
    read_milestones,
    render_milestones_markdown,
    run_milestones_cli,
    sync_milestones,
    write_milestones,
)


def _write_history(output_dir: str, rows: list[tuple[str, str, str, str, str, str]]) -> None:
    """Writes `(title, artists, album, duration_seconds, videoId, played_at)` newest-first."""
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "history.csv"), "w", encoding="utf-8") as f:
        f.write("title,artists,album,duration_seconds,videoId,played_at\n")
        for title, artists, album, dur, vid, played_at in rows:
            t_esc = title.replace('"', '""')
            a_esc = artists.replace('"', '""')
            al_esc = album.replace('"', '""')
            f.write(f'"{t_esc}","{a_esc}","{al_esc}",{dur},{vid},{played_at}\n')


def test_linear_threshold_helpers():
    assert _crossed("catalog_hours", 0, 100) == [100]
    assert _crossed("catalog_hours", 100, 350) == [200, 300]
    assert _crossed("catalog_hours", 250, 250) == []
    assert _next_tier("catalog_hours", 0) == 100
    assert _next_tier("catalog_hours", 100) == 200
    assert _next_tier("catalog_hours", 550) == 600

    assert _crossed("artist_plays", 24, 50) == [25, 50]
    assert _crossed("artist_plays", 50, 150) == [100, 150]
    assert _next_tier("artist_plays", 20) == 25
    assert _next_tier("artist_plays", 25) == 50
    assert _next_tier("artist_plays", 50) == 100
    assert _next_tier("artist_plays", 120) == 150

    assert _crossed("artist_tracks", 0, 50) == [25, 50]
    assert _next_tier("artist_tracks", 40) == 50

    assert _crossed("streak_days", 6, 30) == [7, 14, 30]
    assert _next_tier("streak_days", 5) == 7
    assert _next_tier("streak_days", 10) == 14
    assert _next_tier("streak_days", 20) == 30
    assert _next_tier("streak_days", 45) == 60


def test_atomic_store_corrupt_yaml_and_safe_duration(tmp_path, monkeypatch):
    meta_path = os.path.join(str(tmp_path), "meta", "milestones.yaml")
    default = read_milestones(meta_path)
    assert default["unlocked"] == {}
    assert default["records"]["longest_streak_days"] == 0

    store = read_milestones(meta_path)
    store["unlocked"]["catalog:plays:1000"] = {
        "category": "catalog_plays",
        "entity": "Library",
        "threshold": 1000,
        "date": "2026-11-20",
        "backfilled": True,
    }
    now = datetime(2026, 11, 26, 10, 0, tzinfo=datetime.now().astimezone().tzinfo)
    write_milestones(meta_path, store, now_dt=now)
    assert not os.path.exists(f"{meta_path}.tmp")
    loaded = read_milestones(meta_path)
    assert loaded["meta"]["total_unlocked"] == 1
    assert "catalog:plays:1000" in loaded["unlocked"]

    # Empty dirname atomic write
    monkeypatch.chdir(tmp_path)
    write_milestones("milestones.yaml", store, now_dt=now)
    assert os.path.isfile(os.path.join(str(tmp_path), "milestones.yaml"))
    assert not os.path.exists(os.path.join(str(tmp_path), "milestones.yaml.tmp"))

    # Partial dict, non-dict YAML, and invalid YAML fall back safely
    with open(meta_path, "w") as f:
        f.write("meta:\n  schema_version: 1\nrecords:\n  peak_day_plays: 5\nunlocked: {}\n")
    assert read_milestones(meta_path)["records"]["peak_day_plays"] == 5

    with open(meta_path, "w") as f:
        f.write("- list not dict\n")
    assert read_milestones(meta_path)["unlocked"] == {}

    with open(meta_path, "w") as f:
        f.write("::: [invalid")
    assert read_milestones(meta_path)["unlocked"] == {}

    assert _safe_duration("240") == 240
    assert _safe_duration("bad") == 0
    assert _safe_duration(None) == 0


def test_evaluate_milestones_backfill_tiers_depth_and_almost_there(tmp_path):
    output_dir = str(tmp_path)
    # Empty directory handles cleanly
    empty_store, empty_new, empty_stats, empty_almost = evaluate_milestones(
        output_dir, reference_date=date(2026, 11, 20), backfill=False
    )
    assert empty_new == []
    assert empty_stats["total_plays"] == 0
    assert empty_almost == []

    # Render empty milestones markdown cleanly with zero emojis
    empty_md = render_milestones_markdown(
        empty_store,
        empty_stats,
        empty_almost,
        {
            "window_14d_plays": 0,
            "tracks_on_repeat": [],
            "artist_signals": [],
            "album_binges": [],
            "taste_phases": [],
        },
        "2026-11-20",
    )
    assert "No milestones unlocked yet." in empty_md
    assert "Quiet stretch (0 plays / 14d). No active obsessions." in empty_md
    assert "## Recorded Totals & Peaks" in empty_md
    assert "| Recorded |" in empty_md
    assert "Lifetime" not in empty_md

    # Mark Uploader Channel as uploader so it is excluded from artist milestones
    write_artist_tags(
        os.path.join(output_dir, "meta", "artist_tags.yaml"),
        {
            "artists": {
                "uploader channel": {
                    "name": "Uploader Channel",
                    "primary_genre": "Uploader / Channel",
                    "subgenres": [],
                    "era": "Unknown",
                    "country": "Unknown",
                    "moods": [],
                    "is_uploader": True,
                }
            }
        },
    )

    # Build chronological rows, then reverse to store newest-first like history.csv
    chrono: list[tuple[str, str, str, str, str, str]] = []
    # Stale artist (>180 days ago, 23/25 plays) -> must NOT appear in Almost There
    for i in range(23):
        chrono.append((f"Stale {i}", "Stale Artist", "", "180", f"st{i}", "2026-01-10T00:00:00Z"))

    # Active stretch across 15 consecutive days (2026-11-06..2026-11-20)
    # Phish: 1 early odd-cased play + 49 regular plays across 26 unique tracks & 26 album plays
    # Average duration high enough to cross 100 catalog hours and 10 artist hours
    chrono.append(("Early Song", "PHISH", "Junta", "1800", "ph0", "2026-11-06T00:00:00Z"))
    for i in range(1, 50):
        day = date(2026, 11, 6) + timedelta(days=i % 15)
        vid = f"ph{i % 26}"
        chrono.append(
            (f"Track {i % 26}", "Phish", "Junta", "1800", vid, f"{day.isoformat()}T00:00:00Z")
        )

    # Repeated single track hitting 10 plays + recent artist at 22/25 + track at 8/10
    for _ in range(10):
        chrono.append(("Headphones", "Ott", "Skylon", "300", "v_ott_rep", "2026-11-18T00:00:00Z"))
    for i in range(12):
        chrono.append((f"Ott Cut {i}", "Ott", "", "300", f"v_ott_{i}", "2026-11-19T00:00:00Z"))
    for _ in range(8):
        chrono.append(
            ("Almost Track", "Bonobo", "", "240", "v_bonobo_almost", "2026-11-19T00:00:00Z")
        )

    # Uploader channel with 30 plays -> ignored for artist milestones
    for i in range(30):
        chrono.append((f"Mix {i}", "Uploader Channel", "", "600", f"up{i}", "2026-11-15T00:00:00Z"))

    # 900 filler plays across 105 unique artists (~360s each -> crosses 1000 plays, 100h, 100 artists)
    for i in range(900):
        day = date(2026, 11, 6) + timedelta(days=i % 15)
        chrono.append(
            (f"Cut {i}", f"Artist {i % 105}", "", "360", f"fill{i}", f"{day.isoformat()}T00:00:00Z")
        )

    # Row with invalid timestamp and row with bad duration
    chrono.append(("Bad Date", "Nobody", "", "200", "bad1", "not-a-timestamp"))
    chrono.append(("Bad Dur", "Phish", "", "bad", "ph_bad", "2026-11-20T00:00:00Z"))

    _write_history(output_dir, list(reversed(chrono)))

    res_backfill = sync_milestones(
        output_dir=output_dir, backfill=True, reference_date=date(2026, 11, 20)
    )
    assert res_backfill["newly_unlocked"] == 0
    assert res_backfill["total_unlocked"] > 0

    store = read_milestones(os.path.join(output_dir, "meta", "milestones.yaml"))
    unlocked = store["unlocked"]
    assert "catalog:plays:1000" in unlocked
    assert "catalog:hours:100" in unlocked
    assert "catalog:artists:100" in unlocked
    assert unlocked["artist:phish:plays:50"]["entity"] == "Phish"
    assert "artist:phish:hours:10" in unlocked
    assert "artist:phish:tracks:25" in unlocked
    assert "track:v_ott_rep:10" in unlocked
    assert "album:junta:phish:25" in unlocked
    assert "streak:days:7" in unlocked
    assert "streak:days:14" in unlocked
    assert "artist:uploader channel:plays:25" not in unlocked
    assert unlocked["catalog:plays:1000"]["backfilled"] is True

    # Re-evaluating non-backfill with unchanged history yields 0 newly unlocked (idempotent)
    _, sec_new, _, almost = evaluate_milestones(
        output_dir, reference_date=date(2026, 11, 20), backfill=False
    )
    assert sec_new == []
    assert not any(item["tag"] == "HOT" and "Stale Artist" in item["label"] for item in almost)
    almost_labels = [item["label"] for item in almost]
    assert any("Ott" in lbl for lbl in almost_labels)
    assert any("Almost Track" in lbl for lbl in almost_labels)

    # Zero active streak when reference_date is >= 2 days past last play
    _, _, stats_stale, almost_stale = evaluate_milestones(
        output_dir, reference_date=date(2026, 11, 25), backfill=False
    )
    assert stats_stale["current_streak_days"] == 0
    assert not any("Streak" in item["label"] for item in almost_stale)

    # Add 3 new Ott plays (22 -> 25) and run incremental sync
    new_rows = [
        ("New Ott", "Ott", "", "300", f"v_ott_new_{i}", "2026-11-21T00:00:00Z") for i in range(3)
    ] + list(reversed(chrono))
    _write_history(output_dir, new_rows)

    res_inc = run_milestones_cli(["--output-dir", output_dir])
    assert res_inc["newly_unlocked"] >= 1
    period_ms = get_period_milestones(output_dir, date(2026, 11, 20), date(2026, 11, 22))
    assert any(m["category"] == "artist_plays" and m["entity"] == "Ott" for m in period_ms)
    assert all(not m.get("backfilled") for m in period_ms)

    # Active 1-day-behind streak branch (`ref_date - 1d` active)
    _, _, stats_yesterday, _ = evaluate_milestones(
        output_dir, reference_date=date(2026, 11, 22), backfill=False
    )
    assert stats_yesterday["current_streak_days"] >= 14


def test_detect_obsessions_signals_and_low_activity_guards(tmp_path):
    output_dir = str(tmp_path)
    empty_obs = detect_obsessions(output_dir)
    assert empty_obs["window_14d_plays"] == 0
    assert empty_obs["artist_signals"] == []

    # Case 1: Total hiatus (0 other plays in gap) must NOT produce a Comeback
    # Also quiet 14d (<25 plays) must NOT trigger Taste Phase or Nx multiplier (<50 prior 90d)
    hiatus_dir = os.path.join(output_dir, "hiatus")
    write_artist_tags(
        os.path.join(hiatus_dir, "meta", "artist_tags.yaml"),
        {
            "artists": {
                "hiatus artist": {
                    "primary_genre": "Jazz",
                    "subgenres": ["Ethio-jazz"],
                    "era": "1970s",
                    "is_uploader": False,
                },
                "jazz friend": {
                    "primary_genre": "Jazz",
                    "subgenres": ["Ethio-jazz"],
                    "era": "1970s",
                    "is_uploader": False,
                },
            }
        },
    )
    hiatus_rows: list[tuple[str, str, str, str, str, str]] = []
    # 20 plays back in July, then TOTAL silence (0 other plays), then 6 plays in Nov 14d window
    for i in range(20):
        hiatus_rows.append(
            (f"Old {i}", "Hiatus Artist", "", "200", f"hi{i}", "2026-07-01T00:00:00Z")
        )
    for i in range(6):
        hiatus_rows.append(
            (f"Return {i}", "Hiatus Artist", "", "200", f"hr{i}", "2026-11-18T00:00:00Z")
        )
    # Surge artist with 8 plays across 3 tracks in low-baseline (<50 prior 90d) window -> raw tracks context
    for i in range(8):
        hiatus_rows.append(
            (f"S {i % 3}", "Jazz Friend", "", "200", f"jf{i % 3}", "2026-11-19T00:00:00Z")
        )
    _write_history(hiatus_dir, list(reversed(hiatus_rows)))

    hiatus_obs = detect_obsessions(hiatus_dir, reference_date=date(2026, 11, 20))
    assert not any(s["signal"] == "COMEBACK" for s in hiatus_obs["artist_signals"])
    assert hiatus_obs["taste_phases"] == []
    surge_low = next(s for s in hiatus_obs["artist_signals"] if s["artist"] == "Jazz Friend")
    assert surge_low["signal"] == "SURGE"
    assert "tracks / 14d" in surge_low["context"]

    # Case 2: Rich active catalog triggering all 6 obsession signals + future-row filtering + formatting
    rich_dir = os.path.join(output_dir, "rich")
    write_artist_tags(
        os.path.join(rich_dir, "meta", "artist_tags.yaml"),
        {
            "artists": {
                "uploader bot": {
                    "primary_genre": "Uploader / Channel",
                    "subgenres": [],
                    "era": "Unknown",
                    "is_uploader": True,
                },
                "mulatu": {
                    "primary_genre": "Jazz",
                    "subgenres": ["Ethio-jazz"],
                    "era": "1970s",
                    "is_uploader": False,
                },
                "hailu": {
                    "primary_genre": "Jazz",
                    "subgenres": ["Ethio-jazz"],
                    "era": "1970s",
                    "is_uploader": False,
                },
                "solo act": {
                    "primary_genre": "Ambient",
                    "subgenres": ["Drone"],
                    "era": "Unknown",
                    "is_uploader": False,
                },
            }
        },
    )
    chrono: list[tuple[str, str, str, str, str, str]] = []
    # Comeback Artist had 20 lifetime plays in June
    for i in range(20):
        chrono.append((f"C {i}", "Comeback Act", "", "200", f"cb_old_{i}", "2026-06-01T00:00:00Z"))
    # 110 prior-90d baseline plays + 1 prior Mulatu play (so Mulatu is SURGE, not BREAKOUT)
    chrono.append(("Old Ethio", "Mulatu", "Yekatit", "250", "mu_old", "2026-09-10T00:00:00Z"))
    for i in range(110):
        d = date(2026, 8, 20) + timedelta(days=i % 65)
        chrono.append(
            (f"Base {i}", f"Rock Band {i % 10}", "", "200", f"bs{i}", f"{d.isoformat()}T00:00:00Z")
        )
    # 2 recent Solo Act plays in 14d -> low tag count suppressed from taste_phases
    chrono.append(("Low Tag 1", "Solo Act", "", "200", "sa1", "2026-11-18T00:00:00Z"))
    chrono.append(("Low Tag 2", "Solo Act", "", "200", "sa2", "2026-11-18T00:00:00Z"))

    # Inside 14d window (2026-11-07..2026-11-20), ref=2026-11-20:
    # - Track on repeat (5 plays, 3 on peak day) with pipe + bracket characters
    for _ in range(3):
        chrono.append(
            ("Echo [Live] | Take", "Loop | Artist", "", "220", "v_loop", "2026-11-19T00:00:00Z")
        )
    for _ in range(2):
        chrono.append(
            ("Echo [Live] | Take", "Loop | Artist", "", "220", "v_loop", "2026-11-18T00:00:00Z")
        )
    # - Breakout new artist (first seen inside 30d, 10 plays)
    for i in range(10):
        chrono.append((f"Fresh {i}", "Breakout Act", "", "200", f"br{i}", "2026-11-15T00:00:00Z"))
    # - Genuine Comeback (6 plays after 90d + >=100 other plays)
    for i in range(6):
        chrono.append(
            (f"Back {i}", "Comeback Act", "", "200", f"cb_new_{i}", "2026-11-17T00:00:00Z")
        )
    # - Surge + Taste Phase + Album Binge across Mulatu & Hailu (>=10 Ethio-jazz/Jazz/1970s plays across 2 artists)
    for i in range(9):
        chrono.append((f"Ethio {i}", "Mulatu", "Yekatit", "250", f"mu{i}", "2026-11-16T00:00:00Z"))
    for i in range(5):
        chrono.append(
            (f"Lalibela {i}", "Hailu", "Yekatit | LP", "250", f"ha{i}", "2026-11-16T00:00:00Z")
        )
    # - Uploader in 14d (ignored by artist_signals and album_binges)
    for i in range(12):
        chrono.append(
            (f"Tape {i}", "Uploader Bot", "Channel Album", "200", f"ub{i}", "2026-11-18T00:00:00Z")
        )
    # - Future row after ref_date (must be skipped cleanly)
    chrono.append(("Future Cut", "Future Band", "", "200", "fut1", "2026-12-01T00:00:00Z"))

    _write_history(rich_dir, list(reversed(chrono)))
    res = sync_milestones(output_dir=rich_dir, backfill=True, reference_date=date(2026, 11, 20))
    assert res["obsessions_count"] >= 4

    obs = detect_obsessions(rich_dir, reference_date=date(2026, 11, 20))
    assert any(t["plays_7d"] == 5 and t["peak_day"] == 3 for t in obs["tracks_on_repeat"])
    sigs = {s["artist"]: s for s in obs["artist_signals"]}
    assert sigs["Breakout Act"]["signal"] == "BREAKOUT"
    assert sigs["Comeback Act"]["signal"] == "COMEBACK"
    assert sigs["Mulatu"]["signal"] == "SURGE"
    assert "x vs 90d" in sigs["Mulatu"]["context"]
    assert "Uploader Bot" not in sigs
    assert any(a["album"] == "Yekatit" and a["unique_tracks_7d"] == 9 for a in obs["album_binges"])
    assert any(p["label"] == "Ethio-jazz" for p in obs["taste_phases"])

    with open(os.path.join(rich_dir, "MILESTONES.md"), encoding="utf-8") as f:
        md = f.read()
    assert "# Milestones & Obsessions" in md
    assert "## Recorded Totals & Peaks" in md
    assert "Since 2026-06" in md
    assert "Lifetime" not in md
    assert "Echo (Live) \\| Take" in md
    assert "`BREAKOUT`" in md
    assert "`COMEBACK`" in md
    assert "`SURGE`" in md
    assert "`ALBUM`" in md
    assert "`PHASE`" in md
    for emoji in ("🔥", "🏆", "🎯", "🏅", "💿", "🔁", "🎤"):
        assert emoji not in md

    # Unchanged history must not rewrite milestones.yaml timestamp or MILESTONES.md
    meta_file = os.path.join(rich_dir, "meta", "milestones.yaml")
    prev_updated_at = read_milestones(meta_file)["meta"]["updated_at"]
    sync_milestones(
        output_dir=rich_dir,
        backfill=True,
        reference_date=date(2026, 11, 20),
        now_dt=datetime(2026, 11, 20, 23, 59),
    )
    assert read_milestones(meta_file)["meta"]["updated_at"] == prev_updated_at

    cli_res = run_milestones_cli(["--output-dir", rich_dir, "--backfill"])
    assert cli_res["newly_unlocked"] == 0

    rendered = render_milestones_markdown(
        store={
            "unlocked": {},
            "records": {
                "peak_day_plays": 1200,
                "peak_day_date": "2026-11-20",
                "peak_week_plays": 2219,
                "peak_week_label": "2026-W47",
            },
        },
        summary_stats={"total_plays": 1000, "total_hours": 100.0, "unique_artists": 50},
        almost_there=[
            {
                "label": "**Test** — 150 plays",
                "ratio": 149 / 150,
                "progress": "149/150",
                "remaining_display": "1 play",
            }
        ],
        obsessions={
            "window_14d_plays": 0,
            "tracks_on_repeat": [],
            "artist_signals": [],
            "album_binges": [],
            "taste_phases": [],
        },
        updated_date="2026-11-26",
    )
    assert "[#########-] 149/150" in rendered
    assert "| `HOT` |" in rendered
    assert "| 1 play |" in rendered
    assert "1,200 plays" in rendered
    assert "2,219 plays" in rendered


def test_almost_there_hot_step_ratio_and_wildcards(tmp_path):
    assert _prev_tier("artist_plays", 24) == 0
    assert _prev_tier("artist_plays", 49) == 25
    assert _prev_tier("artist_plays", 1140) == 1100
    assert _prev_tier("catalog_hours", 6978) == 6900
    assert _prev_tier("streak_days", 5) == 0
    assert _prev_tier("streak_days", 10) == 7
    assert _prev_tier("streak_days", 20) == 14
    assert _prev_tier("streak_days", 45) == 30
    assert _step_ratio("artist_plays", 24, 25) == 24 / 25
    assert _step_ratio("artist_plays", 1140, 1150) == 40 / 50

    output_dir = str(tmp_path)
    write_artist_tags(
        os.path.join(output_dir, "meta", "artist_tags.yaml"),
        {
            "artists": {
                "popular band": {
                    "primary_genre": "Rock",
                    "subgenres": [],
                    "era": "2000s",
                    "is_uploader": False,
                },
                "era rare act": {
                    "primary_genre": "Rock",
                    "subgenres": [],
                    "era": "1950s",
                    "is_uploader": False,
                },
                "genre rare act": {
                    "primary_genre": "Jazz",
                    "subgenres": [],
                    "era": "1970s",
                    "is_uploader": False,
                },
            }
        },
    )

    chrono: list[tuple[str, str, str, str, str, str]] = []
    # Dominant Rock/2000s catalog (~240 plays -> >=5% share, not rare) near 250 plays
    for i in range(240):
        chrono.append((f"Pop {i}", "Popular Band", "", "200", f"pb{i}", "2026-11-18T00:00:00Z"))
    # Huge artist at 1,089/1,100 played 19d ago -> lower step_ratio * decay than 24/25 played today
    for i in range(1089):
        chrono.append((f"Big {i}", "Hot Big Act", "", "200", f"hb{i}", "2026-11-01T00:00:00Z"))
    # Small recent artist at 24/25 plays & 24/25 tracks today -> wins HOT #1
    for i in range(24):
        chrono.append((f"Sm {i}", "Hot Small Act", "", "200", f"hs{i}", "2026-11-20T00:00:00Z"))
    # Mid recent artist at 48/50 plays today -> takes HOT artist_plays #2 (capping Hot Big Act out)
    for i in range(48):
        chrono.append((f"Mid {i}", "Hot Mid Act", "", "200", f"hm{i}", "2026-11-20T00:00:00Z"))
    # Depth artists + extra SMALL depth artist + 60d-idle SMALL artist (>45d HOT cutoff)
    for i in range(23):
        chrono.append((f"Dp2 {i}", "Second Depth Act", "", "200", f"sd{i}", "2026-11-20T00:00:00Z"))
    for i in range(22):
        chrono.append((f"Dp3 {i}", "Third Depth Act", "", "200", f"td{i}", "2026-11-19T00:00:00Z"))
    for i in range(24):
        chrono.append((f"Warm {i}", "Sixty Day Act", "", "200", f"sx{i}", "2026-09-21T00:00:00Z"))
    # Tracks near +10: Track Artist appears twice to verify 1-per-artist cap across tracks
    for _ in range(9):
        chrono.append(("Track One", "Track Artist", "", "200", "vt1", "2026-11-20T00:00:00Z"))
    for _ in range(8):
        chrono.append(("Track Two", "Track Artist", "", "200", "vt2", "2026-11-20T00:00:00Z"))
    for _ in range(8):
        chrono.append(("Track Three", "Other Artist", "", "200", "vt3", "2026-11-19T00:00:00Z"))
    for _ in range(8):
        chrono.append(("Nameless Cut", "", "", "200", "v_no_art", "2026-11-18T00:00:00Z"))
    # DUSTY artist & track idle 142d (>= 90d), 1 away
    for i in range(24):
        chrono.append((f"Dusty {i}", "Dusty Act", "", "200", f"du{i}", "2026-07-01T00:00:00Z"))
    for _ in range(9):
        chrono.append(("Dusty Cut", "Oldies Act", "", "200", "vdu9", "2026-07-01T00:00:00Z"))
    # RARE era (<3% era '1950s') & RARE genre (<3% genre 'Jazz') artists
    for i in range(21):
        chrono.append((f"OldRock {i}", "Era Rare Act", "", "200", f"er{i}", "2026-11-18T00:00:00Z"))
    for i in range(21):
        chrono.append(
            (f"RareJazz {i}", "Genre Rare Act", "", "200", f"gr{i}", "2026-11-18T00:00:00Z")
        )

    _write_history(output_dir, list(reversed(chrono)))
    sync_res = sync_milestones(
        output_dir=output_dir, backfill=True, reference_date=date(2026, 11, 20)
    )
    assert sync_res["total_unlocked"] > 0

    _, _, _, almost_w47 = evaluate_milestones(
        output_dir, reference_date=date(2026, 11, 20), backfill=False
    )
    hot_items = [x for x in almost_w47 if x["tag"] == "HOT"]
    wild_items = [x for x in almost_w47 if x["tag"] != "HOT"]
    assert len(hot_items) == 6
    assert len(wild_items) == 3
    assert hot_items[0]["label"] == "**Hot Small Act** — 25 plays"
    assert not any("Hot Big Act" in x["label"] for x in hot_items)
    assert not any("Sixty Day Act" in x["label"] for x in hot_items)
    assert not any("Track Two" in x["label"] for x in almost_w47)
    assert len({x["entity_key"] for x in almost_w47}) == len(almost_w47)
    assert all(x["tag"] in {"SMALL", "DUSTY", "RARE", "TRACK"} for x in wild_items)

    # Verify deterministic stability within the same week & valid rendering
    _, _, _, almost_w47_repeat = evaluate_milestones(
        output_dir, reference_date=date(2026, 11, 20), backfill=False
    )
    assert [x["key"] for x in almost_w47_repeat] == [x["key"] for x in almost_w47]

    with open(os.path.join(output_dir, "MILESTONES.md"), encoding="utf-8") as f:
        md = f.read()
    assert "| Target | Tag | Progress | Remaining |" in md
    assert "| `HOT` |" in md
