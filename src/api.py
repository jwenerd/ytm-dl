import json
import os
import sys
import threading
from datetime import UTC, datetime
from time import strftime, time
from types import MappingProxyType

import yaml
from ytmusicapi import OAuthCredentials, YTMusic

from .meta import MetaStore
from .util import make_dict_readonly, write_file

OAUTH_CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID")
OAUTH_CLIENT_SECRET = os.environ.get("OAUTH_CLIENT_SECRET")


class AuthenticationExpiredError(Exception):
    """Raised when YouTube Music session cookies / headers have expired."""

    pass


def get_auth_info() -> dict:
    """
    Extracts metadata about active auth method (browser.json vs oauth.json),
    including original SAPISIDHASH timestamp and session age.
    """
    info = {"auth_type": "unknown", "valid": False}
    if os.path.exists("browser.json"):
        info["auth_type"] = "browser.json"
        try:
            with open("browser.json", encoding="utf-8") as f:
                data = json.load(f)
                auth_hdr = data.get("authorization", "")
                if "SAPISIDHASH" in auth_hdr:
                    parts = auth_hdr.split()
                    for p in parts:
                        if "_" in p:
                            ts_str = p.split("_")[0]
                            if ts_str.isdigit():
                                ts = int(ts_str)
                                dt = datetime.fromtimestamp(ts, UTC)
                                info["captured_at"] = dt.strftime("%Y-%m-%d %H:%M:%SZ")
                                age_seconds = (datetime.now(UTC) - dt).total_seconds()
                                if age_seconds < 3600:
                                    info["age"] = f"{int(max(0, age_seconds // 60))}m old"
                                elif age_seconds < 86400:
                                    info["age"] = f"{int(age_seconds // 3600)}h old"
                                else:
                                    info["age"] = f"{int(age_seconds // 86400)}d old"
                                break
        except Exception as e:
            info["error"] = str(e)
    elif os.path.exists("oauth.json"):
        info["auth_type"] = "oauth.json"
    return info


def validate_auth(client=None) -> dict:
    """
    Proactively probes YouTube Music authentication by requesting 1 liked song.
    Returns auth diagnostic dict if valid, raises AuthenticationExpiredError if expired.
    """
    if client is None:
        client = get_thread_client()
    auth_info = get_auth_info()
    try:
        res = client.get_liked_songs(limit=1)
        if isinstance(res, dict) and "tracks" in res:
            auth_info["valid"] = True
            auth_info["sample_count"] = len(res.get("tracks", []))
            MetaStore.get("auth").add("info", auth_info)
            return auth_info
        auth_info["valid"] = True
        MetaStore.get("auth").add("info", auth_info)
        return auth_info
    except Exception as e:
        err_msg = str(e)
        if (
            "twoColumnBrowseResultsRenderer" in err_msg
            or "Sign in" in err_msg
            or "Looking for what you’ve liked" in err_msg
            or "Looking for what you've liked" in err_msg
        ):
            auth_info["valid"] = False
            raise AuthenticationExpiredError(
                "YouTube Music session (browser.json / oauth.json) is expired or unauthenticated.\n"
                "YouTube Music responded: 'Sign in to listen to your liked tracks'."
            ) from e
        raise


def report_auth_failure(error: str | Exception) -> None:
    """Formats and prints a clean terminal alert and CI error annotations on auth failure."""
    auth_info = get_auth_info()
    captured = auth_info.get("captured_at", "Unknown")
    age = auth_info.get("age", "Unknown")
    auth_type = auth_info.get("auth_type", "browser.json")

    msg = (
        "\n" + "=" * 80 + "\n"
        "🚨 YOUTUBE MUSIC AUTHENTICATION EXPIRED / INVALID\n" + "=" * 80 + "\n"
        f"Auth Mode: {auth_type}\n"
    )
    if "captured_at" in auth_info:
        msg += f"Session Captured: {captured} ({age})\n"
    msg += f"\nDetails:\n  {error}\n\n"
    msg += "💡 HOW TO FIX:\n"
    msg += "  - Local: Copy request headers from YouTube Music browser tab into browser.json.\n"
    msg += "  - GitHub Actions: Update repository secret YTM_BROWSER_AUTH in repo settings.\n"
    msg += "=" * 80 + "\n"

    print(msg, file=sys.stderr)

    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(
            "::error title=YTM Session Expired::Your YTM_BROWSER_AUTH session has expired. "
            "Please update the secret in repository settings.",
            file=sys.stderr,
        )
        step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary:
            try:
                with open(step_summary, "a", encoding="utf-8") as f:
                    f.write(
                        "\n## 🚨 YouTube Music Authentication Expired\n\n"
                        "> [!CAUTION]\n"
                        f"> The active session (`{auth_type}`) is expired or unauthenticated.\n"
                        f"> **Session Age**: {age} (Captured: `{captured}`)\n>\n"
                        "> **How to Fix**:\n"
                        "> 1. Open YouTube Music in your browser.\n"
                        "> 2. Copy request headers from DevTools Network tab.\n"
                        "> 3. Update the `YTM_BROWSER_AUTH` secret in GitHub Repository Settings.\n\n"
                    )
            except Exception:
                pass


def records_from_response(response):
    meta = {}
    if isinstance(response, dict) and "tracks" in response.keys():
        records = response["tracks"]
        del response["tracks"]
        meta["Tracks"] = response
    else:
        records = response
    return [records, meta]


thread_local = threading.local()


def get_thread_client():
    if not hasattr(thread_local, "ytmusic"):
        if os.path.exists("browser.json"):
            thread_local.ytmusic = YTMusic("browser.json")
        elif os.path.exists("oauth.json") and OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET:
            thread_local.ytmusic = YTMusic(
                "oauth.json",
                oauth_credentials=OAuthCredentials(
                    client_id=OAUTH_CLIENT_ID, client_secret=OAUTH_CLIENT_SECRET
                ),
            )
        else:
            raise RuntimeError("No valid authentication file found (browser.json or oauth.json)")
    return thread_local.ytmusic


API_ARGUMENTS = {
    "get_history": {},
    "get_home": 9,
    "get_liked_songs": {"limit": 500},
    "get_library_songs": {"limit": 500, "order": "recently_added"},
    "get_library_subscriptions": {"limit": 25, "order": "recently_added"},
    "get_library_upload_songs": {"limit": 500, "order": "recently_added"},
    "get_library_upload_artists": {"limit": 50, "order": "recently_added"},
    "get_library_upload_albums": {"limit": 50, "order": "recently_added"},
    "get_library_artists": {"limit": 50, "order": "recently_added"},
    "get_library_albums": {"limit": 150, "order": "recently_added"},
}
DEFAULT_ARGUMENTS = {"limit": 2500, "order": "recently_added"}
make_dict_readonly(DEFAULT_ARGUMENTS)
make_dict_readonly(API_ARGUMENTS)


def suggest_search(search):
    return [search, get_thread_client().get_search_suggestions(search)]


def build_home_records(records):
    rows = []
    i = 0
    for tab in records:
        i = i + 1
        home_title = tab["title"]
        for row in tab["contents"]:
            artists = row.get("artists", [])
            if len(artists) and artists[0].get("name") == "Song" and not artists[0].get("id"):
                row["type"] = "Song"
                artists.pop(0)
            if not row.get("type") and row.get("playlistId"):
                row["type"] = "Playlist" if not row.get("videoId") else "Video"
            if not row.get("type") and row.get("subscribers"):
                row["type"] = "Artist"
            row["home"] = home_title
            row["home_index"] = i
            row["id"] = row.get("browseId")
            if not row["id"]:
                row["id"] = row.get("playlistId")
            if not row["id"]:
                row["id"] = row.get("videoId")

            rows.append(row)
    return rows


class ApiMethod:
    @staticmethod
    def save_api_artifact():
        data = MetaStore.get("api_results").data
        if len(data) == 0:
            return
        time_str = strftime("%Y_%m_%d_%H_%M")
        write_file(f"artifacts/api_results_{time_str}.yaml", yaml.dump(data))

    def __init__(self, method):
        self.client = get_thread_client()
        self.method = method
        self.methodfn = getattr(self.client, method)
        self.method_args = API_ARGUMENTS.get(method, DEFAULT_ARGUMENTS)
        if isinstance(self.method_args, MappingProxyType):
            self.method_args = dict(self.method_args)

    def perform(self):
        start_time = time()
        api_results = self.api_results()
        self.elapsed_time = round(time() - start_time, 2)

        self.records, meta = records_from_response(api_results.copy())
        if self.method == "get_home":
            self.records = build_home_records(self.records)

        meta["API"] = self.api_meta

        MetaStore.get("api_results").add(self.method, api_results)
        MetaStore.get("api").add(self.method, meta["API"])
        return [self.records, meta]

    def api_results(self):
        if isinstance(self.method_args, dict):
            return self.methodfn(**(self.method_args))
        return self.methodfn(self.method_args)

    @property
    def api_meta(self):
        return {
            "method": self.method,
            "args": self.method_args,
            "records_length": len(self.records),
            "time": self.elapsed_time,
        }
