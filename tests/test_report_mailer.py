"""Unit tests for src/reports/mailer.py"""

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.reports.mailer import (
    ReportMailer,
    _extract_report_date,
    _parse_period_to_date,
    dispatch_report_emails,
    load_generated_cadences,
    run_mail_cli,
)


def test_mailer_file_not_found(tmp_path):
    mailer = ReportMailer(cadence="daily", output_dir=str(tmp_path))
    with pytest.raises(FileNotFoundError, match="Report file not found"):
        mailer.read_markdown()


def test_mailer_extract_subject(tmp_path):
    report_file = tmp_path / "reports" / "daily.md"
    report_file.parent.mkdir(parents=True)
    # Test that existing or Gemini-generated leading emojis are stripped cleanly
    report_file.write_text(
        "# 🎧 Daily Listening Log: 2026-10-20\n*Recorded via ytm-dl*\n\nContent",
        encoding="utf-8",
    )

    mailer = ReportMailer(cadence="daily", report_path=str(report_file))
    md = mailer.read_markdown()
    subject = mailer.extract_subject(md)
    assert subject == "Daily Listening Log: 2026-10-20"

    # Test clean title without emoji
    clean_report = tmp_path / "reports" / "clean.md"
    clean_report.write_text("# Daily Listening Log: 2026-10-21\nContent", encoding="utf-8")
    mailer_clean = ReportMailer(cadence="daily", report_path=str(clean_report))
    assert (
        mailer_clean.extract_subject(mailer_clean.read_markdown())
        == "Daily Listening Log: 2026-10-21"
    )

    # Test fallback when no H1 title present
    no_h1 = tmp_path / "reports" / "no_h1.md"
    no_h1.write_text("No header content", encoding="utf-8")
    mailer_fallback = ReportMailer(cadence="daily", report_path=str(no_h1))
    assert mailer_fallback.extract_subject(mailer_fallback.read_markdown()) == "Daily Listening Log"


def test_mailer_render_html_and_preview(tmp_path, monkeypatch):
    report_file = tmp_path / "reports" / "daily.md"
    report_file.parent.mkdir(parents=True)
    report_file.write_text(
        "# Daily Listening Log: 2026-10-20\n\n## 2. Notes\nTested content",
        encoding="utf-8",
    )

    mailer = ReportMailer(cadence="daily", report_path=str(report_file))

    # Mock write_file for preview
    with patch("src.reports.mailer.write_file") as mock_write_file:
        html, preview_path = mailer.render_html(save_preview=True)

        assert "<!DOCTYPE html>" in html
        assert "Tested content" in html
        assert preview_path == os.path.join("tmp", "email_preview_daily.html")
        mock_write_file.assert_called_once()


def test_mailer_send_dry_run(tmp_path):
    report_file = tmp_path / "reports" / "daily.md"
    report_file.parent.mkdir(parents=True)
    report_file.write_text(
        "# Daily Listening Log: 2026-10-20\n\nContent",
        encoding="utf-8",
    )

    mailer = ReportMailer(cadence="daily", report_path=str(report_file))
    res = mailer.send(dry_run=True)

    assert res["status"] == "dry_run"
    assert res["cadence"] == "daily"
    assert res["subject"] == "Daily Listening Log: 2026-10-20"
    assert res["bytes"] > 0
    assert "preview_path" in res


def test_mailer_send_missing_webhook_url(tmp_path, monkeypatch):
    monkeypatch.delenv("YTM_SHEET_UPDATE_URL", raising=False)
    report_file = tmp_path / "reports" / "daily.md"
    report_file.parent.mkdir(parents=True)
    report_file.write_text("# Title\nContent", encoding="utf-8")

    mailer = ReportMailer(cadence="daily", report_path=str(report_file))
    with pytest.raises(ValueError, match="Missing webhook URL"):
        mailer.send(dry_run=False)


@patch("requests.post")
def test_mailer_send_success(mock_post, tmp_path):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "recipient": "user@example.com",
        "bytes": 1234,
    }
    mock_post.return_value = mock_resp

    report_file = tmp_path / "reports" / "daily.md"
    report_file.parent.mkdir(parents=True)
    report_file.write_text("# Daily Listening Log: 2026-10-20\nContent", encoding="utf-8")

    mailer = ReportMailer(cadence="daily", report_path=str(report_file))
    res = mailer.send(
        webhook_url="https://script.google.com/macros/s/TEST/exec?passkey=XYZ",
        recipient="user@example.com",
    )

    assert res["status"] == "sent"
    assert res["status_code"] == 200
    assert res["response"]["status"] == "success"

    # Verify payload
    call_args = mock_post.call_args
    assert "https://script.google.com" in call_args[0][0]
    assert call_args[1]["headers"]["Content-Type"] == "application/json; charset=utf-8"
    sent_data = call_args[1]["data"]
    assert '"action": "send_email"' in sent_data
    assert '"recipient": "user@example.com"' in sent_data


def test_mailer_syncs_milestones_and_adds_subject_tag(tmp_path):
    assert _extract_report_date("# Daily Listening Log: 2026-99-99\n# Date 2026-11-26") is not None
    assert _extract_report_date("No valid date anywhere") is None

    out_dir = tmp_path
    with open(out_dir / "history.csv", "w", encoding="utf-8") as f:
        f.write("title,artists,album,duration_seconds,videoId,played_at\n")
        for i in range(24):
            f.write(f'"Track {i}","Tim Hecker","Virgins",100,vt{i},2026-11-26T00:00:00Z\n')
        for i in range(76):
            f.write(f'"Long {i}","Artist {i}","LP",4800,vl{i},2026-11-26T00:00:00Z\n')

    report_dir = out_dir / "reports"
    report_dir.mkdir(parents=True)
    report_file = report_dir / "daily.md"
    report_file.write_text(
        "# Daily Listening Log: 2026-11-26\n"
        "- **Stats**: 100 plays · 102h · 77 artists · 77 new artists\n\n"
        "Dense drone session.\n",
        encoding="utf-8",
    )

    mailer = ReportMailer(cadence="daily", report_path=str(report_file), output_dir=str(out_dir))
    with patch("src.reports.mailer.write_file") as mock_write_file:
        res = mailer.send(dry_run=True)

    # Milestones must have synced prior to rendering even though milestones.yaml did not exist yet
    assert (out_dir / "meta" / "milestones.yaml").is_file()
    assert (out_dir / "MILESTONES.md").is_file()
    assert res["subject"] == "Daily Listening Log: 2026-11-26 [100h]"
    html_out = mock_write_file.call_args[0][1]
    assert "LINER NOTES  //  ON DECK" in html_out
    assert "listening hours" in html_out
    assert "Tim Hecker" in html_out

    # Report without H1 date falls back cleanly to last_history_date from milestones.yaml
    fallback_ctx = mailer.build_milestone_context("# Daily Digest\nContent\n")
    assert fallback_ctx["milestones"]
    assert fallback_ctx["almost_there"]


def test_period_date_parsing_and_weekly_monthly_contexts(tmp_path):
    assert _extract_report_date("# Weekly Crate Digest: 2026-W47 (Nov 16 - Nov 22)") is not None
    assert (
        _extract_report_date("# Monthly Crate Retrospective: October 2026").strftime("%Y-%m-%d")
        == "2026-10-01"
    )
    assert _parse_period_to_date("2026-10").strftime("%Y-%m-%d") == "2026-10-01"
    assert _parse_period_to_date("2026-W99") is None
    assert _parse_period_to_date("2026-13") is None

    out_dir = tmp_path
    with open(out_dir / "history.csv", "w", encoding="utf-8") as f:
        f.write("title,artists,album,duration_seconds,videoId,played_at\n")
        # October plays (should unlock 25 plays for October Artist in Oct 2026)
        for i in range(25):
            f.write(f'"Oct {i}","October Artist","LP",200,vo{i},2026-10-10T12:00:00Z\n')
        # Newer November play on a different week/month + 7d repeat track at end of W47
        for _i in range(4):
            f.write('"Loop Cut","Loop Artist","LP",200,vlp1,2026-11-22T12:00:00Z\n')
        f.write('"Dec Drift","Dec Artist","LP",200,vd1,2026-12-01T12:00:00Z\n')

    report_dir = out_dir / "reports"
    report_dir.mkdir(parents=True)
    monthly_report = report_dir / "monthly.md"
    monthly_report.write_text(
        "# Monthly Crate Retrospective: October 2026\nBody\n", encoding="utf-8"
    )
    weekly_report = report_dir / "weekly.md"
    weekly_report.write_text(
        "# Weekly Crate Digest: 2026-W47 (Nov 16 - Nov 22)\nBody\n", encoding="utf-8"
    )

    # Monthly email pulls October milestones even though last_history_date is Dec 1, and omits almost_there
    monthly_mailer = ReportMailer(
        cadence="monthly", report_path=str(monthly_report), output_dir=str(out_dir)
    )
    m_ctx = monthly_mailer.build_milestone_context(monthly_mailer.read_markdown())
    assert m_ctx["cadence"] == "monthly"
    assert "almost_there" not in m_ctx
    assert any(m["entity"] == "October Artist" for m in m_ctx["milestones"])
    assert "obsessions" not in m_ctx

    # Weekly email uses reports.yaml fallback when H1 has no date, and attaches W47 obsessions
    meta_dir = out_dir / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "reports.yaml").write_text("weekly:\n  last_period: 2026-W47\n", encoding="utf-8")
    weekly_mailer = ReportMailer(
        cadence="weekly", report_path=str(weekly_report), output_dir=str(out_dir)
    )
    w_ctx = weekly_mailer.build_milestone_context("# Weekly Crate Digest\nNo date in header\n")
    assert w_ctx["cadence"] == "weekly"
    assert "almost_there" not in w_ctx
    assert w_ctx["obsessions"]["tracks_on_repeat"][0]["title"] == "Loop Cut"


@patch("src.reports.mailer.time.sleep")
@patch("requests.post")
def test_mailer_send_retries_and_no_retry_on_400(mock_post, mock_sleep, tmp_path):
    report_file = tmp_path / "reports" / "weekly.md"
    report_file.parent.mkdir(parents=True)
    report_file.write_text("# Weekly Crate Digest: 2026-W47\nBody", encoding="utf-8")
    mailer = ReportMailer(cadence="weekly", report_path=str(report_file), output_dir=str(tmp_path))
    url = "https://script.google.com/macros/s/TEST/exec?passkey=XYZ"

    # 1. RequestException + 502 then 200 succeeds
    resp_502 = MagicMock(ok=False, status_code=502, text="bad gateway")
    resp_502.json.side_effect = ValueError("not json")
    resp_200 = MagicMock(ok=True, status_code=200)
    resp_200.json.return_value = {"status": "success"}
    mock_post.side_effect = [requests.ConnectionError("reset"), resp_502, resp_200]

    res = mailer.send(webhook_url=url, max_retries=2, retry_backoff=0.5)
    assert res["status"] == "sent"
    assert res["cadence"] == "weekly"
    assert mock_post.call_count == 3
    assert [c.args[0] for c in mock_sleep.call_args_list] == [0.5, 1.0]

    # 2. Persistent RequestException exhausts retries and raises
    mock_post.reset_mock()
    mock_post.side_effect = requests.Timeout("timed out")
    with pytest.raises(requests.Timeout):
        mailer.send(webhook_url=url, max_retries=1, retry_backoff=0.1)
    assert mock_post.call_count == 2

    # 3. Non-retryable 400 raises immediately without retry
    mock_post.reset_mock()
    resp_400 = MagicMock(ok=False, status_code=400, text="bad payload")
    resp_400.json.return_value = {"status": "error"}
    mock_post.side_effect = [resp_400]
    with pytest.raises(RuntimeError, match="status 400"):
        mailer.send(webhook_url=url, max_retries=2)
    assert mock_post.call_count == 1


@patch("src.reports.mailer.time.sleep")
@patch("requests.post")
def test_batch_dispatch_generated_file_and_cli(mock_post, mock_sleep, tmp_path):
    out_dir = tmp_path / "out"
    report_dir = out_dir / "reports"
    report_dir.mkdir(parents=True)
    for cad, title in (
        ("daily", "# Daily Listening Log: 2026-11-25\nBody"),
        ("weekly", "# Weekly Crate Digest: 2026-W47\nBody"),
        ("monthly", "# Monthly Crate Retrospective: October 2026\nBody"),
    ):
        (report_dir / f"{cad}.md").write_text(title, encoding="utf-8")

    gen_file = tmp_path / "reports_generated.txt"
    assert load_generated_cadences(str(gen_file)) == []
    gen_file.write_text("monthly\nignored\ndaily\nweekly\ndaily\n", encoding="utf-8")
    assert load_generated_cadences(str(gen_file)) == ["daily", "weekly", "monthly"]

    # Empty --generated CLI run exits cleanly with no errors
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("", encoding="utf-8")
    assert run_mail_cli(["--generated", "--generated-file", str(empty_file)]) == {
        "sent": [],
        "errors": [],
    }

    # Dry-run all via CLI
    with patch("src.reports.mailer.write_file"):
        cli_res = run_mail_cli(["all", "--dry-run", "--output-dir", str(out_dir)])
    assert [r["cadence"] for r in cli_res["sent"]] == ["daily", "weekly", "monthly"]
    assert cli_res["errors"] == []

    # Unknown cadence exits with SystemExit(1)
    with pytest.raises(SystemExit) as exc_info:
        run_mail_cli(["yearly", "--output-dir", str(out_dir)])
    assert exc_info.value.code == 1

    # Partial failure isolation in live dispatch: weekly missing fails, daily & monthly still succeed
    (report_dir / "weekly.md").unlink()
    ok_resp = MagicMock(ok=True, status_code=200)
    ok_resp.json.return_value = {"status": "success"}
    mock_post.return_value = ok_resp

    with (
        patch("src.reports.mailer.write_file"),
        patch.dict(os.environ, {"YTM_SHEET_UPDATE_URL": "https://example.test/webhook"}),
    ):
        results, errors = dispatch_report_emails(
            ["all"],
            output_dir=str(out_dir),
            delay_seconds=1.5,
        )
    assert [r["cadence"] for r in results] == ["daily", "monthly"]
    assert [e["cadence"] for e in errors] == ["weekly"]
    assert mock_sleep.call_count == 2  # between daily->weekly and weekly->monthly

    # CLI --generated propagates non-empty errors as SystemExit(1)
    with (
        patch("src.reports.mailer.write_file"),
        patch.dict(os.environ, {"YTM_SHEET_UPDATE_URL": "https://example.test/webhook"}),
        pytest.raises(SystemExit) as err_exit,
    ):
        run_mail_cli(
            ["--generated", "--generated-file", str(gen_file), "--output-dir", str(out_dir)]
        )
    assert err_exit.value.code == 1
