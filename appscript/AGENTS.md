# Google Apps Script Integration — ytm-dl

This directory contains the Google Apps Script project powering Google Sheets data synchronization and listening log email delivery via GmailApp for `ytm-dl`.

---

## 1. Architecture & Overview

Google Apps Script acts as the serverless downstream consumer of data published by `ytm-dl`:

1. **Google Sheets Synchronization**:
   - Master datasets (`output/history.csv`, `output/liked_songs.csv`, `output/library_albums.csv`) on GitHub branch `main-output` are fetched via GitHub Raw API.
   - Values are parsed and overwritten directly to corresponding Google Spreadsheets defined in `Settings.js` (`FILES`).
   - Runs asynchronously via a time-driven trigger (`ScriptApp.newTrigger`) to acknowledge webhook requests in `< 500ms`, avoiding burning GitHub Actions runner minutes.

2. **Listening Log Email Dispatch**:
   - `src/reports/mailer.py` renders dark-mode HTML listening summaries and dispatches them to this Apps Script Web App.
   - Handled synchronously by `dispatchEmailFromPayload()` using Google Workspace's native `GmailApp.sendEmail()`.

---

## 2. Clasp Configuration & Project Details

The project is managed locally and deployed using Google's Command Line Apps Script Projects (`clasp`) tool:

| Parameter | Value |
|---|---|
| **Script ID** | `1S7m53A6j9-4qEqgyUObpQTBqwc2mq2f-ndwsJ5Ui0qiB4ef-4ufayzZI` |
| **Clasp Config** | [appscript/.clasp.json](file:///Users/jared/projects/ytm-dl/appscript/.clasp.json) |
| **Active Deployment ID** | `AKfycbxkFOjKQWxI9EifEg00ZMsNbfE-FQu-EMqXlC0tUZfIgrBbBDJN7WTl2W4HLVuo8B7Xxw` |
| **Deployment Name** | `ReportMailer v6` |
| **Secret Mapping** | GitHub Secret `YTM_SHEET_UPDATE_URL` points directly to this deployment's `/exec` URL |
| **Execution Identity** | `USER_DEPLOYING` (runs with the script owner's Google account permissions) |
| **Access Control** | Passkey authorization checked in `Settings.js` via `ASM.useSecret` / query param `passkey` |

---

## 3. Clasp Commands & Workflow

Because the npm package is `@google/clasp`, commands should be invoked using `npx @google/clasp` from the `appscript/` directory.

### 3.1. Check Status & Fetch Code
```bash
# Check local vs remote file tracking status
cd appscript && npx @google/clasp status

# List all deployments and their associated version numbers
cd appscript && npx @google/clasp deployments
```

### 3.2. Push Changes & Deploy to Production
> [!IMPORTANT]
> When redeploying, **always redeploy using the existing deployment ID (`-i`)**. Creating a new deployment generates a new Web App URL, which breaks the GitHub Secret `YTM_SHEET_UPDATE_URL` until manually updated.

```bash
cd appscript

# 1. Push local changes to the Apps Script project
npx @google/clasp push

# 2. Redeploy the existing production deployment in-place
npx @google/clasp deploy \
  -i AKfycbxkFOjKQWxI9EifEg00ZMsNbfE-FQu-EMqXlC0tUZfIgrBbBDJN7WTl2W4HLVuo8B7Xxw \
  -d "Async CSV sync with instant ACK"
```

### 3.3. View Live Execution Logs
```bash
cd appscript && npx @google/clasp logs
```

---

## 4. Webhook API Specification (`doPost`)

The Web App handles incoming `POST` requests according to payload content:

### 4.1. CSV Sync Request (Default Async)
- **Sender**: GitHub Actions (`.github/workflows/run.yml` -> `Update Google Sheets`)
- **Body**: Empty (`-d ''`) or `{}` with URL parameter `?passkey=...`
- **Behavior**:
  1. Validates passkey.
  2. Prunes any orphaned triggers for `asyncSaveCSVs`.
  3. Schedules `asyncSaveCSVs` 1 second in the future via `ScriptApp.newTrigger`.
  4. Returns immediate HTTP 200 JSON acknowledgment in `< 500ms`.
- **Response**:
  ```json
  {
    "status": "queued",
    "message": "CSV synchronization job accepted and scheduled"
  }
  ```
- **Synchronous Override**: Appending `?sync=true` forces synchronous execution and returns `{ "sheets": [...] }`.

### 4.2. Email Dispatch Request
- **Sender**: `ReportMailer` (`python ytm-dl.py mail [cadence]`)
- **Body**:
  ```json
  {
    "action": "send_email",
    "cadence": "daily",
    "subject": "🎧 Daily Listening Log",
    "html_body": "<!DOCTYPE html>...",
    "recipient": "user@example.com"
  }
  ```
- **Behavior**: Calls `GmailApp.sendEmail()`, logs recipient and byte size, and returns `{ "status": "success", ... }`.

---

## 5. Quotas, Triggers & Safety Rules

1. **Trigger Quota (20 Max per Script)**:
   - Google Apps Script enforces a hard limit of 20 active triggers per script/user.
   - `_cleanupTriggers("asyncSaveCSVs")` runs both *before* creating a trigger and inside the *finally* block of `asyncSaveCSVs()`.
   - This prevents stale trigger accumulation across repeated sync runs.

2. **Branch Boundaries & Secret Protection**:
   - `appscript/` source files (`Code.js`, `Settings.js`, `appsscript.json`) are tracked on `main`.
   - `.clasp.json` contains only public project metadata (Script ID).
   - `.clasprc.json` contains sensitive OAuth2 tokens and is strictly blocked by `.gitignore` and `scripts/check_boundaries.py`. **NEVER** commit `.clasprc.json` to any branch.
