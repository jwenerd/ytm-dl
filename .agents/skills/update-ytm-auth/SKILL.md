---
name: update-ytm-auth
description: >-
  Updates YouTube Music browser authentication when session cookies or headers expire.
  Use this skill whenever the user pastes a fetch snippet, cURL command, raw request headers,
  or asks to refresh browser.json, update the GitHub repository secret (YTM_BROWSER_AUTH),
  or re-trigger a failed sync run due to expired authentication.
---

# Update YouTube Music Browser Authentication

This skill guides you through refreshing YouTube Music authentication when session credentials expire, validating the new credentials against the YouTube Music API, updating the GitHub Actions secret `YTM_BROWSER_AUTH`, and re-triggering the sync workflow.

---

## Background & Critical Caveats

1. **Authentication Mechanism**:
   - `ytmusicapi` requires both `authorization` (`SAPISIDHASH`) and `cookie` (containing `__Secure-3PAPISID`, `SID`, etc.).
   - `YTMusic` dynamically re-computes `authorization` using the timestamp and `__Secure-3PAPISID` from the cookie for every request.
2. **Chrome "Copy as fetch" Gotcha**:
   - In Chrome DevTools, selecting **"Copy as fetch"** automatically **omits** the `cookie` header from the snippet (replacing it with `"credentials": "include"`).
   - If the user pastes a fetch snippet without `cookie`, prompt them to copy the `Cookie:` header line from the Network tab Headers pane (or copy using **"Copy request headers"** / **"Copy as cURL"**).

---

## Quick Execution via Helper Script

A dedicated helper script is included with this skill:
[update_auth.py](./scripts/update_auth.py)

### 1. Run Automated Update (Local + Validate + GitHub Secret + Workflow Trigger)

If the user pasted the snippet in chat or saved it to a file:

```bash
# From file or piped snippet
./venv/bin/python .agents/skills/update-ytm-auth/scripts/update_auth.py --all --file snippet.txt

# Or from macOS clipboard
pbpaste | ./venv/bin/python .agents/skills/update-ytm-auth/scripts/update_auth.py --all

# Or if cookie was copied separately:
./venv/bin/python .agents/skills/update-ytm-auth/scripts/update_auth.py --all --cookie "<COOKIE_STRING>" "<FETCH_SNIPPET>"
```

### 2. Flags Reference:
- `--all` (`-a`): Update `browser.json` &rarr; validate locally &rarr; sync GitHub secret `YTM_BROWSER_AUTH` &rarr; trigger `run.yml` with `run_option: all`.
- `--dry-run`: Parse and validate authentication against YouTube Music without modifying any files or secrets.
- `--sync-github` (`-g`): Sync `browser.json` to GitHub Actions secret `YTM_BROWSER_AUTH`.
- `--trigger-run` (`-t`): Trigger GitHub Actions workflow `run.yml` (`run_option: all`).
- `--cookie` (`-c`): Pass explicit cookie header string if missing from the pasted fetch snippet.

---

## Step-by-Step Manual Workflow

If executing manually without the helper script:

### Step 1: Update `browser.json`
Construct or update `browser.json` in the repository root with the following JSON structure:

```json
{
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "authorization": "SAPISIDHASH <timestamp>_<hash> ...",
    "content-type": "application/json",
    "origin": "https://music.youtube.com",
    "x-origin": "https://music.youtube.com",
    "user-agent": "Mozilla/5.0 ...",
    "cookie": "GPS=1; ...; __Secure-3PAPISID=...; SID=...",
    "x-goog-authuser": "0",
    "x-goog-visitor-id": "..."
}
```

> [!WARNING]
> Never commit `browser.json` to git! Ensure it remains ignored in `.gitignore`.

### Step 2: Validate Authentication Locally
Run the proactive auth validator:

```bash
./venv/bin/python ytm-dl.py auth
```

Expected output on success:
```text
✓ YouTube Music authentication is valid!
  Auth Mode:        browser.json
  Session Captured: YYYY-MM-DD HH:MM:SSZ (<age> old)
  Probe Result:     Successfully verified 200 liked track sample.
```

If validation fails with `'Sign in to listen to your liked tracks'`, the cookie is expired or missing.

### Step 3: Update GitHub Secret
Use the GitHub CLI (`gh`) to update the secret:

```bash
gh secret set YTM_BROWSER_AUTH < browser.json
```

Verify the update timestamp:
```bash
gh secret list
```

### Step 4: Trigger the GitHub Actions Workflow
Dispatch the workflow for a full sync:

```bash
gh workflow run run.yml -f run_option=all
```

### Step 5: Monitor Run Status
Check the status of the dispatched workflow:

```bash
gh run list --limit 3
gh run view <run_id>
```
Verify that the `Validate Auth 🔑` step and subsequent extraction jobs complete successfully.
