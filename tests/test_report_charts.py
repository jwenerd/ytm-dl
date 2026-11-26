"""Unit tests for src/reports/charts.py and output README / FILES.md generation."""

import os
from datetime import date

from src import meta
from src.reports.charts import (
    _compute_streaks,
    _heatmap_cell,
    build_readme_charts_markdown,
    load_daily_play_counts,
    load_monthly_history_stats,
    render_activity_heatmap,
    render_monthly_trend_charts,
)


def _write_partition_csv(path: str, rows: list[tuple[str, str]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("title,artists,album,duration_seconds,videoId,played_at\n")
        for idx, (played_at, dur) in enumerate(rows, start=1):
            f.write(f"Song {idx},Artist,Album,{dur},vid{idx},{played_at}\n")


def test_load_monthly_history_stats_filters_before_2026(tmp_path):
    output_dir = str(tmp_path)
    hist_dir = os.path.join(output_dir, "history")

    # Should be ignored: < 2026 and non-YYYY-MM filename
    _write_partition_csv(os.path.join(hist_dir, "2024-12.csv"), [("2024-12-01T00:00:00Z", "180")])
    _write_partition_csv(os.path.join(hist_dir, "2025-05.csv"), [("2025-05-01T00:00:00Z", "180")])
    _write_partition_csv(os.path.join(hist_dir, "notes.csv"), [("2026-06-01T00:00:00Z", "180")])

    # Included: 2026+ out of order on disk, sorted chronologically on return
    _write_partition_csv(
        os.path.join(hist_dir, "2026-07.csv"),
        [
            ("2026-07-02T00:00:00Z", "3600"),
            ("2026-07-02T00:00:00Z", "bad"),
        ],
    )
    _write_partition_csv(
        os.path.join(hist_dir, "2026-04.csv"),
        [
            ("2026-04-01T00:00:00Z", "1800"),
            ("2026-04-03T00:00:00Z", "1800"),
        ],
    )

    stats = load_monthly_history_stats(output_dir, min_year=2026)
    assert [s["month"] for s in stats] == ["2026-04", "2026-07"]
    assert stats[0] == {
        "month": "2026-04",
        "label": "Apr 26",
        "plays": 2,
        "hours": 1.0,
        "active_days": 2,
    }
    assert stats[1]["plays"] == 2
    assert stats[1]["hours"] == 1.0
    assert stats[1]["active_days"] == 1


def test_load_daily_play_counts_spans_24_weeks_and_year_rollover(tmp_path):
    output_dir = str(tmp_path)
    hist_dir = os.path.join(output_dir, "history")

    # End date in early Jan 2027 forces Dec -> Jan year rollover in loader
    end_date = date(2027, 1, 6)
    _write_partition_csv(
        os.path.join(hist_dir, "2026-12.csv"),
        [
            ("2026-12-31T00:00:00Z", "200"),
            ("2026-12-31T00:00:00Z", "200"),
            ("bad-ts", "200"),
        ],
    )
    _write_partition_csv(
        os.path.join(hist_dir, "2027-01.csv"),
        [
            ("2027-01-05T00:00:00Z", "200"),
            ("2027-01-15T00:00:00Z", "200"),  # after end_date -> excluded
        ],
    )

    counts = load_daily_play_counts(output_dir, weeks=24, end_date=end_date)
    assert counts[date(2026, 12, 31)] == 2
    assert counts[date(2027, 1, 5)] == 1
    assert date(2027, 1, 15) not in counts


def test_heatmap_cell_tiers_and_streaks():
    assert _heatmap_cell(None) == "▫️"
    assert _heatmap_cell(0) == "⬛"
    assert _heatmap_cell(5) == "🟩"
    assert _heatmap_cell(15) == "🟨"
    assert _heatmap_cell(45) == "🟧"
    assert _heatmap_cell(75) == "🟥"

    start = date(2026, 11, 16)
    end = date(2026, 11, 22)
    counts = {
        date(2026, 11, 16): 1,
        date(2026, 11, 17): 12,
        date(2026, 11, 18): 35,
        # 19th missed -> breaks best streak of 3
        date(2026, 11, 20): 60,
        date(2026, 11, 21): 2,
        # 22nd (end) is 0 -> current streak still holds 2 through yesterday (20-21)
    }
    cur, best = _compute_streaks(counts, start, end)
    assert cur == 2
    assert best == 3

    md = render_activity_heatmap(counts, weeks=2, end_date=end)
    assert "### 🔥 Listening Activity (Last 2 Weeks)" in md
    assert "**110 plays**" in md
    assert "Current streak: **2d** · Best streak: **3d**" in md
    assert "| Mon |" in md
    assert "| Sun |" in md
    assert "🟩" in md
    assert "🟨" in md
    assert "🟧" in md
    assert "🟥" in md
    assert "⬛" in md
    # Verify upcoming cells appear mid-week (e.g., Wednesday)
    md_wed = render_activity_heatmap(counts, weeks=2, end_date=date(2026, 11, 18))
    assert "▫️" in md_wed


def test_render_monthly_trend_charts_and_combined_builder(tmp_path):
    assert render_monthly_trend_charts([]) == ""
    assert build_readme_charts_markdown(str(tmp_path), end_date=date(2026, 11, 26)) == ""

    output_dir = str(tmp_path)
    _write_partition_csv(
        os.path.join(output_dir, "history", "2026-11.csv"),
        [
            ("2026-11-24T00:00:00Z", "3600"),
            ("2026-11-25T00:00:00Z", "1800"),
        ],
    )
    combined = build_readme_charts_markdown(
        output_dir, weeks=24, min_year=2026, end_date=date(2026, 11, 26)
    )
    assert "### 🔥 Listening Activity (Last 24 Weeks)" in combined
    assert "### 📈 Monthly Trend (2026+)" in combined
    assert "xychart-beta" in combined
    assert 'title "Monthly Listening Hours (2026+)"' in combined
    assert 'title "Monthly Plays (2026+)"' in combined
    assert 'x-axis ["Nov 26"]' in combined
    assert "| 2026-11 | 2 | 1.5h | 2 |" in combined


def test_write_readme_moves_files_to_files_md_and_embeds_charts(tmp_path, monkeypatch):
    out_dir = tmp_path / "output"
    hist_dir = out_dir / "history"
    _write_partition_csv(
        str(hist_dir / "2026-11.csv"),
        [("2026-11-24T00:00:00Z", "3600")],
    )

    written: dict[str, str] = {}

    def fake_output_path(file: str = "") -> str:
        return f"{out_dir}/{file}" if file else str(out_dir)

    def fake_write_output_file(file: str, content: str) -> None:
        written[file] = content

    monkeypatch.setattr(meta, "output_path", fake_output_path)
    monkeypatch.setattr(meta, "write_output_file", fake_write_output_file)
    monkeypatch.setattr(meta, "IS_GITHUB", True)
    monkeypatch.setattr(
        meta,
        "GITHUB_META",
        {"repository": "jwenerd/ytm-dl", "run_id": "42", "job": "run", "run_number": "7109"},
    )

    meta.write_readme()

    assert "FILES.md" in written
    assert "README.md" in written

    files_md = written["FILES.md"]
    assert "# 📁 Output Files" in files_md
    assert "[← Back to README](README.md)" in files_md
    assert "history/2026-11.csv" in files_md

    readme_md = written["README.md"]
    assert "### 📁 Files" not in readme_md
    assert "[📁 Output Files](FILES.md)" in readme_md
    assert "[📰 Listening Reports](reports/README.md)" in readme_md
    assert "run #7109" in readme_md
    assert "### 🔥 Listening Activity (Last 24 Weeks)" in readme_md
    assert "### 📈 Monthly Trend (2026+)" in readme_md

    # Empty dir & IS_GITHUB=False still writes FILES.md and README.md cleanly
    empty_out = tmp_path / "empty_out"
    empty_out.mkdir()
    written.clear()
    monkeypatch.setattr(
        meta, "output_path", lambda file="": f"{empty_out}/{file}" if file else str(empty_out)
    )
    monkeypatch.setattr(meta, "IS_GITHUB", False)
    meta.write_readme()
    assert "# 📁 Output Files" in written["FILES.md"]
    assert "### 🔥 Listening Activity" not in written["README.md"]
