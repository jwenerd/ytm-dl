"""Integration tests for src/reports/aggregator.py context assembly facade."""

import os
from datetime import date, datetime

from src.reports.aggregator import (
    aggregate_listening_telemetry,
    assemble_report_context,
    extract_radar_candidates,
)


def test_aggregator_reexports_public_helpers():
    assert callable(aggregate_listening_telemetry)
    assert callable(extract_radar_candidates)


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

    ctx_dt = assemble_report_context(output_dir, "daily", datetime(2026, 10, 19, 18, 0))
    assert ctx_dt["period_label"] == "2026-10-19"
    ctx_default = assemble_report_context(output_dir, "daily", None)
    assert ctx_default["cadence"] == "daily"
