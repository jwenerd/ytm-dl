import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

script_path = (
    Path(__file__).resolve().parents[1] / ".agents/skills/update-ytm-auth/scripts/update_auth.py"
)
spec = importlib.util.spec_from_file_location("update_auth", script_path)
update_auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update_auth)

build_browser_data = update_auth.build_browser_data
extract_headers = update_auth.extract_headers
extract_headers_from_curl = update_auth.extract_headers_from_curl
extract_headers_from_fetch = update_auth.extract_headers_from_fetch
extract_headers_from_raw = update_auth.extract_headers_from_raw
sync_github_secret = update_auth.sync_github_secret
trigger_workflow_run = update_auth.trigger_workflow_run
validate_browser_data = update_auth.validate_browser_data


def test_extract_headers_from_fetch():
    snippet = """
    fetch("https://music.youtube.com/youtubei/v1/browse?prettyPrint=false", {
      "headers": {
        "accept": "*/*",
        "authorization": "SAPISIDHASH 12345_hash",
        "cookie": "GPS=1; SID=abc; SAPISID=xyz",
      },
      "body": "{\\"userAgent\\": \\"Mozilla/5.0 CustomAgent/1.0\\"}",
      "method": "POST"
    });
    """
    headers = extract_headers_from_fetch(snippet)
    assert headers["accept"] == "*/*"
    assert headers["authorization"] == "SAPISIDHASH 12345_hash"
    assert "GPS=1" in headers["cookie"]
    assert headers["user-agent"] == "Mozilla/5.0 CustomAgent/1.0"


def test_extract_headers_from_curl():
    curl_cmd = """
    curl 'https://music.youtube.com/youtubei/v1/browse' \\
      -H 'accept: */*' \\
      -H 'authorization: SAPISIDHASH 99999_hash' \\
      -H 'cookie: SID=secret; SAPISID=secret'
    """
    headers = extract_headers_from_curl(curl_cmd)
    assert headers["accept"] == "*/*"
    assert headers["authorization"] == "SAPISIDHASH 99999_hash"
    assert "SID=secret" in headers["cookie"]


def test_extract_headers_from_raw():
    raw = """
    accept: */*
    authorization: SAPISIDHASH 88888_hash
    cookie: SID=foo; SAPISID=bar
    user-agent: CustomUA/2.0
    """
    headers = extract_headers_from_raw(raw)
    assert headers["accept"] == "*/*"
    assert headers["authorization"] == "SAPISIDHASH 88888_hash"
    assert headers["cookie"] == "SID=foo; SAPISID=bar"
    assert headers["user-agent"] == "CustomUA/2.0"


def test_extract_headers_json():
    data = {
        "authorization": "SAPISIDHASH 77777_hash",
        "cookie": "SID=test",
    }
    headers = extract_headers(json.dumps(data))
    assert headers["authorization"] == "SAPISIDHASH 77777_hash"
    assert headers["cookie"] == "SID=test"


def test_build_browser_data_valid():
    headers = {
        "authorization": "SAPISIDHASH 123_hash",
        "cookie": "SAPISID=test",
        "accept": "*/*",
        "user-agent": "TestBrowser/1.0",
        "x-goog-visitor-id": "visitor123",
    }
    data = build_browser_data(headers)
    assert data["authorization"] == "SAPISIDHASH 123_hash"
    assert data["cookie"] == "SAPISID=test"
    assert data["user-agent"] == "TestBrowser/1.0"
    assert data["origin"] == "https://music.youtube.com"
    assert data["x-goog-visitor-id"] == "visitor123"


def test_build_browser_data_missing_cookie():
    headers = {
        "authorization": "SAPISIDHASH 123_hash",
    }
    with pytest.raises(ValueError, match="Missing 'cookie' header"):
        build_browser_data(headers)


def test_build_browser_data_missing_authorization():
    headers = {
        "cookie": "SAPISID=test",
    }
    with pytest.raises(ValueError, match="Missing 'authorization' header"):
        build_browser_data(headers)


def test_validate_browser_data_mock(tmp_path):
    browser_data = {
        "authorization": "SAPISIDHASH 123_hash",
        "cookie": "SAPISID=test",
    }
    mock_client = MagicMock()
    mock_client.get_liked_songs.return_value = {"tracks": [{"videoId": "123"}]}

    with patch("ytmusicapi.YTMusic", return_value=mock_client):
        res = validate_browser_data(browser_data, tmp_path)
        assert res["valid"] is True
        assert res["sample_count"] == 1


def test_sync_github_secret(tmp_path):
    browser_json = tmp_path / "browser.json"
    browser_json.write_text('{"cookie": "test"}', encoding="utf-8")

    mock_proc = MagicMock(returncode=0, stderr="")
    with patch("subprocess.run", return_value=mock_proc):
        ok = sync_github_secret(tmp_path)
        assert ok is True


def test_trigger_workflow_run(tmp_path):
    mock_proc = MagicMock(returncode=0, stderr="")
    with patch("subprocess.run", return_value=mock_proc):
        ok = trigger_workflow_run(tmp_path, run_option="all")
        assert ok is True
