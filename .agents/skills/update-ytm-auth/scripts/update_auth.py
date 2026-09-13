#!/usr/bin/env python3
"""
Helper script to parse browser request data (fetch snippets, cURL commands,
raw headers, or JSON), update browser.json, validate authentication, and
optionally update GitHub Secrets and trigger Actions workflow.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def find_repo_root() -> Path:
    """Find the root directory of the ytm-dl repository."""
    current = Path(__file__).resolve().parent
    for p in [current, *current.parents]:
        if (p / "ytm-dl.py").is_file():
            return p
    return Path.cwd()


def extract_headers_from_fetch(text: str) -> dict[str, str]:
    """Extracts headers and user-agent from a JS fetch(...) call snippet."""
    headers: dict[str, str] = {}

    m = re.search(r"['\"]?headers['\"]?\s*:\s*\{", text)
    if m:
        start = m.end() - 1
        depth = 0
        end = -1
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end != -1:
            raw_block = text[start:end]
            cleaned = re.sub(r",\s*\}", "}", raw_block)
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    headers.update({k.lower(): str(v) for k, v in parsed.items()})
            except Exception:
                for line in raw_block.splitlines():
                    line_m = re.match(
                        r"^\s*['\"]?([^'\":]+)['\"]?\s*:\s*['\"]?(.*?)['\"]?\s*,?\s*$", line
                    )
                    if line_m:
                        k, v = line_m.group(1).strip().lower(), line_m.group(2).strip()
                        if k not in ("{", "}"):
                            headers[k] = v

    if "user-agent" not in headers:
        ua_m = re.search(r"""\\?["\']?userAgent\\?["\']?\s*:\s*\\?["\']([^"\\\']+)""", text)
        if ua_m:
            headers["user-agent"] = ua_m.group(1)

    return headers


def extract_headers_from_curl(text: str) -> dict[str, str]:
    """Extracts headers from a curl command string."""
    headers: dict[str, str] = {}
    pattern = re.compile(r"""(?:-H|--header)\s+['"]([^'"]+)['"]""")
    for match in pattern.finditer(text):
        hdr = match.group(1)
        if ":" in hdr:
            k, v = hdr.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return headers


def extract_headers_from_raw(text: str) -> dict[str, str]:
    """Extracts headers from raw header lines (Key: Value)."""
    headers: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(":") or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k_clean = k.strip().lower().strip("'\"")
            v_clean = v.strip().strip("'\"")
            if k_clean and v_clean:
                headers[k_clean] = v_clean
    return headers


def extract_headers(text: str) -> dict[str, str]:
    """Auto-detects format and extracts headers dict."""
    text = text.strip()
    if not text:
        return {}

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            if "headers" in data and isinstance(data["headers"], dict):
                data = data["headers"]
            return {k.lower(): str(v) for k, v in data.items()}
    except Exception:
        pass

    if "fetch(" in text or '"headers":' in text or "'headers':" in text:
        res = extract_headers_from_fetch(text)
        if res:
            return res

    if "curl " in text or "-H " in text:
        res = extract_headers_from_curl(text)
        if res:
            return res

    return extract_headers_from_raw(text)


def build_browser_data(
    headers: dict[str, str], cookie_override: str | None = None
) -> dict[str, str]:
    """Builds clean, valid browser.json dictionary."""
    cookie = cookie_override or headers.get("cookie")
    if not cookie:
        raise ValueError(
            "Missing 'cookie' header.\n"
            "Note: Chrome's 'Copy as fetch' omits the Cookie header for security.\n"
            "To get the cookie: In Chrome DevTools Network tab, copy the 'Cookie:' line\n"
            "from the request headers, or use 'Copy request headers' / 'Copy as cURL'."
        )

    auth = headers.get("authorization")
    if not auth:
        raise ValueError("Missing 'authorization' header (SAPISIDHASH).")

    ua = headers.get(
        "user-agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36,gzip(gfe)",
    )
    origin = headers.get("origin", headers.get("x-origin", "https://music.youtube.com"))
    x_origin = headers.get("x-origin", origin)

    data = {
        "accept": headers.get("accept", "*/*"),
        "accept-language": headers.get("accept-language", "en-US,en;q=0.9"),
        "authorization": auth,
        "content-type": headers.get("content-type", "application/json"),
        "origin": origin,
        "x-origin": x_origin,
        "user-agent": ua,
        "cookie": cookie,
    }

    if "x-goog-authuser" in headers:
        data["x-goog-authuser"] = headers["x-goog-authuser"]
    if "x-goog-visitor-id" in headers:
        data["x-goog-visitor-id"] = headers["x-goog-visitor-id"]

    return data


def validate_browser_data(browser_data: dict[str, str], repo_root: Path) -> dict[str, Any]:
    """Validates the authentication in-memory using YTMusic."""
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from ytmusicapi import YTMusic

    client = YTMusic(auth=browser_data)
    res = client.get_liked_songs(limit=1)
    sample_count = len(res.get("tracks", [])) if isinstance(res, dict) else 0
    return {"valid": True, "sample_count": sample_count}


def sync_github_secret(repo_root: Path) -> bool:
    """Updates GitHub Actions secret YTM_BROWSER_AUTH using gh CLI."""
    browser_json_path = repo_root / "browser.json"
    if not browser_json_path.exists():
        print(f"Error: {browser_json_path} does not exist.", file=sys.stderr)
        return False

    cmd = ["gh", "secret", "set", "YTM_BROWSER_AUTH"]
    with open(browser_json_path, "rb") as f:
        res = subprocess.run(cmd, stdin=f, cwd=repo_root, capture_output=True, text=True)

    if res.returncode == 0:
        print("✓ Updated GitHub secret 'YTM_BROWSER_AUTH'")
        return True
    else:
        print(f"Failed to update GitHub secret: {res.stderr}", file=sys.stderr)
        return False


def trigger_workflow_run(repo_root: Path, run_option: str = "all") -> bool:
    """Triggers GitHub Actions workflow run.yml."""
    cmd = ["gh", "workflow", "run", "run.yml", "-f", f"run_option={run_option}"]
    res = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"✓ Triggered GitHub Actions workflow run.yml (run_option: {run_option})")
        return True
    else:
        print(f"Failed to trigger workflow: {res.stderr}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update YouTube Music browser auth from fetch/curl/headers snippet."
    )
    parser.add_argument("snippet", nargs="?", help="Raw snippet string (optional if reading stdin)")
    parser.add_argument("--file", "-f", help="Path to file containing snippet")
    parser.add_argument("--cookie", "-c", help="Explicit cookie string if missing from snippet")
    parser.add_argument(
        "--sync-github", "-g", action="store_true", help="Sync to GitHub secret YTM_BROWSER_AUTH"
    )
    parser.add_argument(
        "--trigger-run", "-t", action="store_true", help="Trigger GitHub Actions workflow run.yml"
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Update + validate + sync GitHub + trigger workflow",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Test parse and validate without writing files"
    )

    args = parser.parse_args()
    repo_root = find_repo_root()

    text = ""
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.snippet:
        text = args.snippet
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        # Check pbpaste on macOS
        try:
            pb = subprocess.run(["pbpaste"], capture_output=True, text=True)
            if "music.youtube.com" in pb.stdout and (
                "headers" in pb.stdout or "authorization" in pb.stdout
            ):
                print("📋 Detected YouTube Music snippet in clipboard.")
                text = pb.stdout
        except Exception:
            pass

    if not text:
        print(
            "Error: No snippet provided.\n"
            "Usage:\n"
            "  python update_auth.py --all < snippet.txt\n"
            "  pbpaste | python update_auth.py --all\n"
            "  python update_auth.py --file fetch_snippet.js --all",
            file=sys.stderr,
        )
        return 1

    try:
        headers = extract_headers(text)
        browser_data = build_browser_data(headers, cookie_override=args.cookie)
    except Exception as e:
        print(f"\n❌ Error parsing input: {e}\n", file=sys.stderr)
        return 1

    print("🔎 Probing YouTube Music authentication...")
    try:
        val_res = validate_browser_data(browser_data, repo_root)
        print(
            f"✓ Authentication is valid! (Verified {val_res['sample_count']} liked tracks sample)"
        )
    except Exception as e:
        print(f"\n❌ Probe failed: {e}\n", file=sys.stderr)
        return 1

    if args.dry_run:
        print("✓ Dry run successful! No files were modified.")
        return 0

    browser_json_path = repo_root / "browser.json"
    with open(browser_json_path, "w", encoding="utf-8") as f:
        json.dump(browser_data, f, indent=4)
    print(f"✓ Saved updated credentials to {browser_json_path}")

    # Verify using ytm-dl.py auth if available
    auth_script = repo_root / "ytm-dl.py"
    if auth_script.exists():
        subprocess.run([sys.executable, str(auth_script), "auth"], cwd=repo_root)

    should_sync = args.sync_github or args.all
    should_trigger = args.trigger_run or args.all

    if should_sync:
        sync_ok = sync_github_secret(repo_root)
        if not sync_ok:
            return 1

    if should_trigger:
        trigger_ok = trigger_workflow_run(repo_root, run_option="all")
        if not trigger_ok:
            return 1

    print("\n🎉 All done! YouTube Music authentication successfully updated and synced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
