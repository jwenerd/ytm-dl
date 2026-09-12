import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.api import (
    AuthenticationExpiredError,
    get_auth_info,
    report_auth_failure,
    validate_auth,
)


def test_get_auth_info_browser_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    now_ts = int(datetime.now(UTC).timestamp())
    browser_data = {
        "User-Agent": "Mozilla/5.0",
        "authorization": f"SAPISIDHASH {now_ts - 3600}_abc123def456",
        "cookie": "SID=test; SAPISID=test",
    }
    (tmp_path / "browser.json").write_text(json.dumps(browser_data), encoding="utf-8")

    info = get_auth_info()
    assert info["auth_type"] == "browser.json"
    assert "captured_at" in info
    assert "1h old" in info["age"]


def test_get_auth_info_browser_json_minutes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    now_ts = int(datetime.now(UTC).timestamp())
    browser_data = {
        "authorization": f"SAPISIDHASH {now_ts - 600}_abc123def456",
    }
    (tmp_path / "browser.json").write_text(json.dumps(browser_data), encoding="utf-8")

    info = get_auth_info()
    assert info["auth_type"] == "browser.json"
    assert "10m old" in info["age"]


def test_get_auth_info_browser_json_days(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    now_ts = int(datetime.now(UTC).timestamp())
    browser_data = {
        "authorization": f"SAPISIDHASH {now_ts - 172800}_abc123def456",
    }
    (tmp_path / "browser.json").write_text(json.dumps(browser_data), encoding="utf-8")

    info = get_auth_info()
    assert info["auth_type"] == "browser.json"
    assert "2d old" in info["age"]


def test_get_auth_info_oauth(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "oauth.json").write_text('{"access_token": "abc"}', encoding="utf-8")

    info = get_auth_info()
    assert info["auth_type"] == "oauth.json"


def test_get_auth_info_unknown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    info = get_auth_info()
    assert info["auth_type"] == "unknown"


def test_validate_auth_success():
    mock_client = MagicMock()
    mock_client.get_liked_songs.return_value = {"tracks": [{"videoId": "test1234"}]}

    with patch("src.api.get_auth_info", return_value={"auth_type": "browser.json"}):
        result = validate_auth(client=mock_client)
        assert result["valid"] is True
        assert result["sample_count"] == 1
        mock_client.get_liked_songs.assert_called_once_with(limit=1)


def test_validate_auth_expired_two_column_renderer():
    mock_client = MagicMock()
    mock_client.get_liked_songs.side_effect = KeyError("twoColumnBrowseResultsRenderer")

    with patch("src.api.get_auth_info", return_value={"auth_type": "browser.json"}):
        with pytest.raises(AuthenticationExpiredError) as exc_info:
            validate_auth(client=mock_client)
        assert "expired or unauthenticated" in str(exc_info.value)


def test_validate_auth_expired_sign_in_message():
    mock_client = MagicMock()
    mock_client.get_liked_songs.side_effect = Exception("Sign in to listen to your tracks")

    with patch("src.api.get_auth_info", return_value={"auth_type": "browser.json"}):
        with pytest.raises(AuthenticationExpiredError) as exc_info:
            validate_auth(client=mock_client)
        assert "expired or unauthenticated" in str(exc_info.value)


def test_validate_auth_unexpected_error():
    mock_client = MagicMock()
    mock_client.get_liked_songs.side_effect = ConnectionError("Network unreachable")

    with patch("src.api.get_auth_info", return_value={"auth_type": "browser.json"}):
        with pytest.raises(ConnectionError):
            validate_auth(client=mock_client)


def test_report_auth_failure_ci_output(tmp_path, monkeypatch, capsys):
    summary_file = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    with patch(
        "src.api.get_auth_info",
        return_value={
            "auth_type": "browser.json",
            "captured_at": "2026-09-12 12:00:00Z",
            "age": "2h old",
        },
    ):
        err = AuthenticationExpiredError("Session expired test")
        report_auth_failure(err)

    captured = capsys.readouterr()
    assert "YOUTUBE MUSIC AUTHENTICATION EXPIRED" in captured.err
    assert "::error title=YTM Session Expired::" in captured.err

    assert summary_file.exists()
    content = summary_file.read_text(encoding="utf-8")
    assert "YouTube Music Authentication Expired" in content
    assert "2h old" in content
