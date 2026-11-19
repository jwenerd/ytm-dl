"""Unit tests for src/reports/rotator.py"""

import csv
import os
from datetime import UTC, datetime
from unittest.mock import patch

from src.reports.rotator import (
    get_target_period_info,
    read_reports_meta,
    rotate_and_write_report,
    run_reports,
    should_run_cadence,
    update_reports_readme,
    write_reports_meta,
)


def test_meta_read_write(tmp_path):
    meta_path = os.path.join(str(tmp_path), "reports.yaml")
    assert read_reports_meta(meta_path) == {}

    data = {"daily": {"last_period": "2026-10-18"}}
    write_reports_meta(meta_path, data)
    assert read_reports_meta(meta_path) == data


def test_get_target_period_info():
    # 2026-10-19 is a Monday
    now_dt = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)

    # Daily: target is Sunday 2026-10-18
    p_key, t_date, arc_path = get_target_period_info("daily", now_dt)
    assert p_key == "2026-10-18"
    assert t_date.strftime("%Y-%m-%d") == "2026-10-18"
    assert arc_path == os.path.join("archive", "daily", "2026", "2026-10-18.md")

    # Weekly: target is the completed week (week 42)
    p_key_w, _, arc_path_w = get_target_period_info("weekly", now_dt)
    assert "2026-W" in p_key_w
    assert arc_path_w.startswith(os.path.join("archive", "weekly", "2026"))

    # Monthly: target is 2026-09
    p_key_m, _, arc_path_m = get_target_period_info("monthly", now_dt)
    assert p_key_m == "2026-09"
    assert arc_path_m == os.path.join("archive", "monthly", "2026", "2026-09.md")


def test_should_run_cadence():
    now_dt = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)

    # Case 1: Empty meta -> True
    should_run, p_key, _ = should_run_cadence("daily", {}, now_dt)
    assert should_run is True
    assert p_key == "2026-10-18"

    # Case 2: Already ran for 2026-10-18 -> False
    meta = {"daily": {"last_period": "2026-10-18"}}
    should_run, _, _ = should_run_cadence("daily", meta, now_dt)
    assert should_run is False

    # Case 3: Last ran for older day 2026-10-17 -> True
    meta_old = {"daily": {"last_period": "2026-10-17"}}
    should_run, _, _ = should_run_cadence("daily", meta_old, now_dt)
    assert should_run is True


def test_rotate_and_write_report(tmp_path):
    output_dir = str(tmp_path)
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

    # Check live file
    live_file = os.path.join(output_dir, "reports", "daily.md")
    assert os.path.isfile(live_file)
    with open(live_file) as f:
        assert f.read() == content

    # Check archive file
    archive_file = os.path.join(output_dir, "reports", "archive", "daily", "2026", "2026-10-18.md")
    assert os.path.isfile(archive_file)
    with open(archive_file) as f:
        assert f.read() == content

    # Check meta updated
    updated_meta = read_reports_meta(meta_path)
    assert updated_meta["daily"]["last_period"] == "2026-10-18"


def test_update_reports_readme(tmp_path):
    output_dir = str(tmp_path)
    reports_dir = os.path.join(output_dir, "reports")
    arc_dir = os.path.join(reports_dir, "archive", "daily", "2026")
    os.makedirs(arc_dir, exist_ok=True)

    with open(os.path.join(arc_dir, "2026-10-17.md"), "w") as f:
        f.write("content 17")
    with open(os.path.join(arc_dir, "2026-10-18.md"), "w") as f:
        f.write("content 18")

    update_reports_readme(output_dir)

    readme_file = os.path.join(reports_dir, "README.md")
    assert os.path.isfile(readme_file)
    with open(readme_file) as f:
        readme_text = f.read()
        assert "2026-10-18" in readme_text
        assert "2026-10-17" in readme_text
        assert "[daily.md](daily.md)" in readme_text


def _write_history_csv(output_dir: str, played_at_dates: list[str]) -> None:
    """Helper to seed output/history.csv with plays on given ISO date/timestamp strings."""
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


@patch("src.reports.rotator.generate_report", return_value="# Mocked Report Content\n")
def test_run_reports_lazy_man_flow(mock_gen, tmp_path):
    output_dir = str(tmp_path)
    now_dt = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)

    # Seed plays in daily (2026-10-18), weekly (2026-W42), and monthly (2026-09) windows
    _write_history_csv(
        output_dir,
        [
            "2026-10-18T12:00:00Z",
            "2026-09-15T12:00:00Z",
        ],
    )

    # First run -> generates daily, weekly, monthly
    generated = run_reports(output_dir=output_dir, now_dt=now_dt)
    assert "daily" in generated
    assert "weekly" in generated
    assert "monthly" in generated
    assert mock_gen.call_count == 3

    # Verify files created
    assert os.path.isfile(os.path.join(output_dir, "reports", "daily.md"))
    assert os.path.isfile(os.path.join(output_dir, "reports", "weekly.md"))
    assert os.path.isfile(os.path.join(output_dir, "reports", "monthly.md"))
    assert os.path.isfile(os.path.join(output_dir, "reports", "README.md"))

    # Second run immediately after -> should be skipped because periods are already completed
    second_run = run_reports(output_dir=output_dir, now_dt=now_dt)
    assert second_run == []

    # Forced run -> should run even if already completed
    forced_run = run_reports(output_dir=output_dir, force_cadence="daily", now_dt=now_dt)
    assert forced_run == ["daily"]
    assert mock_gen.call_count == 4


@patch("src.reports.rotator.generate_report", return_value="# Should Not Run\n")
def test_run_reports_skips_zero_activity(mock_gen, tmp_path):
    output_dir = str(tmp_path)
    now_dt = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)

    # No history.csv -> 0 tracks for daily, weekly, monthly
    generated = run_reports(output_dir=output_dir, now_dt=now_dt)
    assert generated == []
    mock_gen.assert_not_called()

    # No report files, archive, README, or metadata written
    assert not os.path.exists(os.path.join(output_dir, "reports"))
    assert not os.path.exists(os.path.join(output_dir, "meta", "reports.yaml"))

    # Even forced cadences skip when there are 0 plays
    forced = run_reports(output_dir=output_dir, force_cadence="all", now_dt=now_dt)
    assert forced == []
    mock_gen.assert_not_called()


@patch("src.reports.rotator.generate_report")
def test_run_reports_preserves_previous_report_on_inactive_day(mock_gen, tmp_path):
    output_dir = str(tmp_path)
    mock_gen.side_effect = [
        "# Daily Report 2026-10-18\n",
        "# Daily Report 2026-10-19\n",
    ]
    meta_path = os.path.join(output_dir, "meta", "reports.yaml")
    write_reports_meta(
        meta_path,
        {
            "weekly": {"last_period": "2026-W42"},
            "monthly": {"last_period": "2026-09"},
        },
    )

    # Day 1 (2026-10-18) has plays
    _write_history_csv(output_dir, ["2026-10-18T12:00:00Z"])
    day1_now = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)
    assert run_reports(output_dir=output_dir, now_dt=day1_now) == ["daily"]

    live_daily = os.path.join(output_dir, "reports", "daily.md")
    with open(live_daily) as f:
        assert f.read() == "# Daily Report 2026-10-18\n"
    assert read_reports_meta(meta_path)["daily"]["last_period"] == "2026-10-18"

    # Day 2 (2026-10-19) has 0 plays -> skipped cleanly without touching live file or meta
    day2_now = datetime(2026, 10, 20, 10, 0, 0, tzinfo=UTC)
    assert run_reports(output_dir=output_dir, now_dt=day2_now) == []
    assert mock_gen.call_count == 1
    with open(live_daily) as f:
        assert f.read() == "# Daily Report 2026-10-18\n"
    assert not os.path.exists(
        os.path.join(output_dir, "reports", "archive", "daily", "2026", "2026-10-19.md")
    )
    assert read_reports_meta(meta_path)["daily"]["last_period"] == "2026-10-18"

    # Late-arriving plays for 2026-10-19 arrive later -> next run picks them up
    _write_history_csv(output_dir, ["2026-10-19T22:00:00Z", "2026-10-18T12:00:00Z"])
    assert run_reports(output_dir=output_dir, now_dt=day2_now) == ["daily"]
    assert mock_gen.call_count == 2
    with open(live_daily) as f:
        assert f.read() == "# Daily Report 2026-10-19\n"
    assert read_reports_meta(meta_path)["daily"]["last_period"] == "2026-10-19"


@patch("src.reports.rotator.generate_report", return_value="# Active Report\n")
def test_run_reports_partial_activity_across_cadences(mock_gen, tmp_path):
    output_dir = str(tmp_path)
    # Monday 2026-10-19: daily=2026-10-18, weekly=2026-W42 (Oct 12-18), monthly=2026-09
    now_dt = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)

    # Plays exist in previous week (Oct 15) and previous month (Sep 10), but NOT yesterday (Oct 18)
    _write_history_csv(
        output_dir,
        [
            "2026-10-15T12:00:00Z",
            "2026-09-10T12:00:00Z",
        ],
    )

    generated = run_reports(output_dir=output_dir, now_dt=now_dt)
    assert generated == ["weekly", "monthly"]
    assert mock_gen.call_count == 2
    assert not os.path.exists(os.path.join(output_dir, "reports", "daily.md"))
    assert os.path.isfile(os.path.join(output_dir, "reports", "weekly.md"))
    assert os.path.isfile(os.path.join(output_dir, "reports", "monthly.md"))


def test_should_run_cadence_evening_vs_nocturnal_timing(monkeypatch):
    monkeypatch.setenv("YTM_TIMEZONE", "America/Denver")
    meta = {"daily": {"last_period": "2026-10-18"}}

    # 1. Monday 6:19 PM MDT (00:19 UTC Oct 20)
    # UTC rolled over, but in Denver it is still Monday evening.
    # The report for Monday (Oct 19) must NOT run yet.
    dt_evening_early = datetime(2026, 10, 20, 0, 19, 0, tzinfo=UTC)
    should_run, period_key, _ = should_run_cadence("daily", meta, dt_evening_early)
    assert should_run is False
    assert period_key == "2026-10-18"

    # 2. Monday 10:49 PM MDT (04:49 UTC Oct 20)
    # Late evening listening: still Monday, must NOT run daily report yet.
    dt_evening_late = datetime(2026, 10, 20, 4, 49, 0, tzinfo=UTC)
    should_run, period_key, _ = should_run_cadence("daily", meta, dt_evening_late)
    assert should_run is False
    assert period_key == "2026-10-18"

    # 3. Tuesday 1:19 AM MDT (07:19 UTC Oct 20)
    # Calendar date in Denver is now Tuesday. The first run of the day executes.
    # It SHOULD run for Monday Oct 19!
    dt_1am = datetime(2026, 10, 20, 7, 19, 0, tzinfo=UTC)
    should_run, period_key, _ = should_run_cadence("daily", meta, dt_1am)
    assert should_run is True
    assert period_key == "2026-10-19"

    # 4. Tuesday 3:19 AM MDT (09:19 UTC Oct 20) with refresh_nocturnal
    # If report was already generated at 1am, but more plays arrived before 4am, refresh allows updating.
    meta_updated = {"daily": {"last_period": "2026-10-19"}}
    dt_3am = datetime(2026, 10, 20, 9, 19, 0, tzinfo=UTC)
    should_run_no_refresh, _, _ = should_run_cadence(
        "daily", meta_updated, dt_3am, refresh_nocturnal=False
    )
    assert should_run_no_refresh is False

    should_run_refresh, period_key_refresh, _ = should_run_cadence(
        "daily", meta_updated, dt_3am, refresh_nocturnal=True
    )
    assert should_run_refresh is True
    assert period_key_refresh == "2026-10-19"

    # 5. Tuesday 6:19 AM MDT (12:19 UTC Oct 20)
    # After the 4am cutoff, even with refresh_nocturnal, the window is closed.
    dt_6am = datetime(2026, 10, 20, 12, 19, 0, tzinfo=UTC)
    should_run_morning, _, _ = should_run_cadence(
        "daily", meta_updated, dt_6am, refresh_nocturnal=True
    )
    assert should_run_morning is False
