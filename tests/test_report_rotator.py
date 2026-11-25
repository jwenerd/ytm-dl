"""Unit tests for src/reports/rotator.py"""

import csv
import os
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.reports.rotator import (
    _get_prior_excluded_ids,
    _record_period_picks,
    get_target_period_info,
    read_reports_meta,
    rotate_and_write_report,
    run_reports,
    should_run_cadence,
    update_reports_readme,
    write_reports_meta,
)


def test_meta_read_write_and_corrupt_yaml(tmp_path):
    meta_path = os.path.join(str(tmp_path), "reports.yaml")
    assert read_reports_meta(meta_path) == {}

    data = {"daily": {"last_period": "2026-10-18"}}
    write_reports_meta(meta_path, data)
    assert read_reports_meta(meta_path) == data

    with open(meta_path, "w") as f:
        f.write(":::invalid_yaml: [")
    assert read_reports_meta(meta_path) == {}


def test_get_target_period_info():
    now_dt = datetime(2026, 10, 19, 10, 0, 0)  # naive UTC supported

    p_key, t_date, arc_path = get_target_period_info("daily", now_dt)
    assert p_key == "2026-10-18"
    assert t_date.strftime("%Y-%m-%d") == "2026-10-18"
    assert arc_path == os.path.join("archive", "daily", "2026", "2026-10-18.md")

    p_key_w, _, arc_path_w = get_target_period_info("weekly", now_dt)
    assert "2026-W" in p_key_w
    assert arc_path_w.startswith(os.path.join("archive", "weekly", "2026"))

    p_key_m, _, arc_path_m = get_target_period_info("monthly", now_dt)
    assert p_key_m == "2026-09"
    assert arc_path_m == os.path.join("archive", "monthly", "2026", "2026-09.md")

    with pytest.raises(ValueError, match="Unknown cadence"):
        get_target_period_info("yearly", now_dt)


def test_should_run_cadence():
    now_dt = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)

    should_run, p_key, _ = should_run_cadence("daily", {}, now_dt)
    assert should_run is True
    assert p_key == "2026-10-18"

    meta = {"daily": {"last_period": "2026-10-18"}}
    should_run, _, _ = should_run_cadence("daily", meta, now_dt)
    assert should_run is False

    meta_old = {"daily": {"last_period": "2026-10-17"}}
    should_run, _, _ = should_run_cadence("daily", meta_old, now_dt)
    assert should_run is True


def test_rotate_and_write_report_and_readme(tmp_path):
    output_dir = str(tmp_path)
    # Missing reports dir returns cleanly
    update_reports_readme(output_dir)

    meta_path = os.path.join(output_dir, "meta", "reports.yaml")
    now_dt = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)
    meta = {}

    content = "# Daily Listening Log: 2026-10-18\nTest Content"
    rotate_and_write_report(
        output_dir=output_dir,
        cadence="daily",
        period_key="2026-10-18",
        content=content,
        meta=meta,
        meta_path=meta_path,
        now_dt=now_dt,
    )

    live_file = os.path.join(output_dir, "reports", "daily.md")
    assert os.path.isfile(live_file)
    update_reports_readme(output_dir)
    readme_file = os.path.join(output_dir, "reports", "README.md")
    assert os.path.isfile(readme_file)


def _write_history_csv(output_dir: str, played_at_dates: list[str]) -> None:
    history_path = os.path.join(output_dir, "history.csv")
    os.makedirs(output_dir, exist_ok=True)
    fieldnames = [
        "videoId",
        "title",
        "artists",
        "album",
        "duration_seconds",
        "inLibrary",
        "played_at",
    ]
    with open(history_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for idx, ts in enumerate(played_at_dates, start=1):
            writer.writerow(
                {
                    "videoId": f"vid-{idx}",
                    "title": f"Track {idx}",
                    "artists": "Test Artist",
                    "album": "Test Album",
                    "duration_seconds": "200",
                    "inLibrary": "True",
                    "played_at": ts,
                }
            )


@patch(
    "src.reports.rotator.sync_daily_radar_playlist",
    return_value="https://music.youtube.com/playlist?list=PL_RADAR",
)
@patch(
    "src.reports.rotator.generate_report",
    return_value=(
        "# Daily Listening Log: 2026-10-18\n"
        "*Recorded via ytm-dl | Crate-Digger Daily*\n\n"
        "## Today's Radar\n"
        "- **[Pick](https://music.youtube.com/watch?v=vid_pick1)** — Artist\n"
    ),
)
def test_run_reports_lazy_man_flow_with_playlist_banner(mock_gen, mock_sync, tmp_path):
    output_dir = str(tmp_path)
    now_dt = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)

    _write_history_csv(
        output_dir,
        [
            "2026-10-18T12:00:00Z",
            "2026-09-15T12:00:00Z",
        ],
    )

    generated = run_reports(output_dir=output_dir, now_dt=now_dt)
    assert generated == ["daily", "weekly", "monthly"]
    mock_sync.assert_called_once()

    with open(os.path.join(output_dir, "reports", "daily.md")) as f:
        daily_text = f.read()
    assert "Play Rolling Daily Radar Playlist" in daily_text
    assert "PL_RADAR" in daily_text

    meta = read_reports_meta(os.path.join(output_dir, "meta", "reports.yaml"))
    assert meta["recent_radar_ids"] == ["vid_pick1"]

    # Second run skipped
    assert run_reports(output_dir=output_dir, now_dt=now_dt) == []

    # Forced run without playlist sync
    forced = run_reports(
        output_dir=output_dir, force_cadence="daily", now_dt=now_dt, sync_playlist=False
    )
    assert forced == ["daily"]


@patch("src.reports.rotator.generate_report", return_value="# Should Not Run\n")
def test_run_reports_skips_zero_activity(mock_gen, tmp_path):
    output_dir = str(tmp_path)
    generated = run_reports(output_dir=output_dir, now_dt=None)
    assert generated == []
    mock_gen.assert_not_called()


def test_should_run_cadence_evening_vs_nocturnal_timing(monkeypatch):
    monkeypatch.setenv("YTM_TIMEZONE", "America/Denver")
    meta_updated = {"daily": {"last_period": "2026-10-19"}}
    # Naive datetime at 09:19 UTC -> 3:19 AM MDT (< 4am nocturnal refresh)
    dt_3am_naive = datetime(2026, 10, 20, 9, 19, 0)
    should_run_refresh, period_key_refresh, _ = should_run_cadence(
        "daily", meta_updated, dt_3am_naive, refresh_nocturnal=True
    )
    assert should_run_refresh is True
    assert period_key_refresh == "2026-10-19"

    dt_6am = datetime(2026, 10, 20, 12, 19, 0, tzinfo=UTC)
    should_run_morning, _, _ = should_run_cadence(
        "daily", meta_updated, dt_6am, refresh_nocturnal=True
    )
    assert should_run_morning is False


def test_prior_excluded_ids_and_period_recording():
    # Legacy fallback excludes when last_period != current_period, skips when equal
    legacy_meta = {
        "daily": {"last_period": "2026-11-23"},
        "recent_radar_ids": ["v_old1", "v_old2"],
    }
    assert _get_prior_excluded_ids(legacy_meta, "2026-11-24") == {"v_old1", "v_old2"}
    assert _get_prior_excluded_ids(legacy_meta, "2026-11-23") == set()

    # Period-keyed exclusions never exclude current_period during nocturnal refreshes
    meta: dict = {}
    _record_period_picks(meta, "2026-11-23", ["v_23", "MPREb_alb1"])
    _record_period_picks(meta, "2026-11-24", ["v_24", "v_23"])
    assert _get_prior_excluded_ids(meta, "2026-11-24") == {"v_23", "MPREb_alb1"}
    assert _get_prior_excluded_ids(meta, "2026-11-25") == {"v_24", "v_23", "MPREb_alb1"}
