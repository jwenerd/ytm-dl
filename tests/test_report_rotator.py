"""Unit tests for src/reports/rotator.py"""

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

    content = "# 🎧 Daily Listening Log: 2026-10-18\nTest Content"
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


@patch("src.reports.rotator.generate_report", return_value="# Mocked Report Content\n")
def test_run_reports_lazy_man_flow(mock_gen, tmp_path):
    output_dir = str(tmp_path)
    now_dt = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)

    # First run without API key -> falls back to deterministic and generates daily, weekly, monthly
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
