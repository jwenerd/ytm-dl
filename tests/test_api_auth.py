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

    with (
        patch("src.api.get_auth_info", return_value={"auth_type": "browser.json"}),
        pytest.raises(ConnectionError),
    ):
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


def test_write_auth_meta(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.meta import write_auth_meta

    with patch(
        "src.api.get_auth_info",
        return_value={
            "auth_type": "browser.json",
            "captured_at": "2026-09-12 19:15:39Z",
            "age": "30m old",
        },
    ):
        write_auth_meta()

    auth_md = tmp_path / "tmp" / "step_output" / "auth_info.md"
    assert auth_md.exists()
    content = auth_md.read_text(encoding="utf-8")
    assert "### 🔑 Authentication" in content
    assert "`browser.json`" in content
    assert "Active & Valid" in content


def test_records_from_response():
    from src.api import records_from_response

    # Dict with tracks
    resp = {"tracks": [{"videoId": "v1"}], "title": "My Album"}
    records, meta = records_from_response(resp)
    assert records == [{"videoId": "v1"}]
    assert "Tracks" in meta

    # List response
    records2, meta2 = records_from_response([{"videoId": "v2"}])
    assert records2 == [{"videoId": "v2"}]
    assert meta2 == {}


def test_get_thread_client_browser_json(monkeypatch):
    from src.api import get_thread_client, thread_local

    if hasattr(thread_local, "ytmusic"):
        del thread_local.ytmusic

    monkeypatch.setattr("os.path.exists", lambda path: path == "browser.json")
    mock_ytmusic = MagicMock()
    with patch("src.api.YTMusic", return_value=mock_ytmusic):
        client = get_thread_client()
        assert client == mock_ytmusic

    if hasattr(thread_local, "ytmusic"):
        del thread_local.ytmusic


def test_get_thread_client_oauth(monkeypatch):
    from src.api import get_thread_client, thread_local

    if hasattr(thread_local, "ytmusic"):
        del thread_local.ytmusic

    monkeypatch.setattr("os.path.exists", lambda path: path == "oauth.json")
    monkeypatch.setattr("src.api.OAUTH_CLIENT_ID", "test_client_id")
    monkeypatch.setattr("src.api.OAUTH_CLIENT_SECRET", "test_client_secret")

    mock_ytmusic = MagicMock()
    with patch("src.api.YTMusic", return_value=mock_ytmusic), patch("src.api.OAuthCredentials"):
        client = get_thread_client()
        assert client == mock_ytmusic

    if hasattr(thread_local, "ytmusic"):
        del thread_local.ytmusic


def test_get_thread_client_no_auth(monkeypatch):
    from src.api import get_thread_client, thread_local

    if hasattr(thread_local, "ytmusic"):
        del thread_local.ytmusic

    monkeypatch.setattr("os.path.exists", lambda path: False)
    with pytest.raises(RuntimeError, match="No valid authentication file found"):
        get_thread_client()

    if hasattr(thread_local, "ytmusic"):
        del thread_local.ytmusic


def test_suggest_search(monkeypatch):
    from src.api import suggest_search, thread_local

    mock_client = MagicMock()
    mock_client.get_search_suggestions.return_value = ["acoustic", "ambient"]
    thread_local.ytmusic = mock_client

    try:
        res = suggest_search("a")
        assert res == ["a", ["acoustic", "ambient"]]
        mock_client.get_search_suggestions.assert_called_once_with("a")
    finally:
        if hasattr(thread_local, "ytmusic"):
            del thread_local.ytmusic


def test_api_method_perform_and_meta(monkeypatch):
    from src.api import ApiMethod, thread_local
    from src.meta import MetaStore

    mock_client = MagicMock()
    mock_client.get_liked_songs.return_value = {
        "tracks": [{"videoId": "song1", "title": "Track 1"}],
        "title": "Liked Tracks",
    }
    thread_local.ytmusic = mock_client

    try:
        api_method = ApiMethod("get_liked_songs")
        records, meta = api_method.perform()
        assert records == [{"videoId": "song1", "title": "Track 1"}]
        assert "API" in meta
        assert meta["API"]["method"] == "get_liked_songs"
        assert meta["API"]["records_length"] == 1
        assert "Tracks" in meta

        # Verify stored in MetaStore
        assert "get_liked_songs" in MetaStore.get("api_results").data
        assert "get_liked_songs" in MetaStore.get("api").data
    finally:
        if hasattr(thread_local, "ytmusic"):
            del thread_local.ytmusic


def test_api_method_perform_list_response(monkeypatch):
    from src.api import ApiMethod, thread_local

    mock_client = MagicMock()
    mock_client.get_history.return_value = [{"videoId": "h1"}]
    mock_client.custom_method.return_value = [{"videoId": "c1"}]
    thread_local.ytmusic = mock_client

    try:
        api_method = ApiMethod("get_history")
        records, meta = api_method.perform()
        assert records == [{"videoId": "h1"}]
        assert meta["API"]["method"] == "get_history"
        assert meta["API"]["records_length"] == 1

        # Test positional arg (non-dict)
        custom_api = ApiMethod("custom_method")
        custom_api.method_args = 42
        assert custom_api.api_results() == [{"videoId": "c1"}]
        mock_client.custom_method.assert_called_once_with(42)
    finally:
        if hasattr(thread_local, "ytmusic"):
            del thread_local.ytmusic


def test_api_method_save_api_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.api import ApiMethod
    from src.meta import MetaStore

    # Empty data should return without writing
    MetaStore.get("api_results").data.clear()
    ApiMethod.save_api_artifact()
    artifacts_dir = tmp_path / "artifacts"
    assert not artifacts_dir.exists()

    # Populated data should write YAML
    MetaStore.get("api_results").add("test_method", {"key": "val"})
    ApiMethod.save_api_artifact()
    assert artifacts_dir.exists()
    yaml_files = list(artifacts_dir.glob("api_results_*.yaml"))
    assert len(yaml_files) == 1
    content = yaml_files[0].read_text(encoding="utf-8")
    assert "test_method:" in content
