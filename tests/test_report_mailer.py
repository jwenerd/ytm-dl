"""Unit tests for src/reports/mailer.py"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.reports.mailer import ReportMailer


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
