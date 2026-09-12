# AGENTS.md — Repository Guide & Instructions for AI Agents

Welcome to `ytm-dl`! This document provides architectural context, development workflows, coding conventions, and operational guidelines for AI agents working in this repository.

---

## 1. Project Overview

`ytm-dl` is an automated synchronization tool that downloads YouTube Music library data, listening history, liked songs, recommendations (home feed), subscriptions, uploads, and search suggestions into structured CSV and YAML datasets.

### Key Capabilities
- **Incremental Sync & Prepending**: Fetches recent activity and seamlessly prepends new items to existing CSV files without duplicating records.
- **History Partitioning**: Organizes the continuous listening history (`output/history.csv`) into monthly archive files (`output/history/YYYY-MM.csv`).
- **Data Provenance & Timestamps**: Snaps relative YouTube Music timestamps (`Today`, `Yesterday`, relative months) to UTC midnight ISO timestamps and tags rows with `run_id` (e.g. `gh-<run_number>` or local timestamps).
- **Automated Workflow**: Runs on scheduled cron and webhook triggers via GitHub Actions (`.github/workflows/run.yml`), publishing data to the dedicated `main-output` branch and syncing to Google Sheets via Google Apps Script (`appscript/`).

---

## 2. Repository Structure

```
ytm-dl/
├── ytm-dl.py                     # Main CLI entrypoint and execution orchestrator
├── src/
│   ├── api.py                   # ytmusicapi client wrapper, auth handling, API call dispatch
│   ├── mapping.py               # Marshmallow schemas, field mappings, timestamp/run_id enrichment
│   ├── output.py                # Output manager, CSV/YAML writes, prepend orchestrator
│   ├── prepend.py               # Sequence alignment & deduplication logic for prepending
│   ├── history_partition.py     # Partitioning history CSV into monthly archives
│   ├── meta.py                  # Metadata tracking, file statistics, step summaries, README generation
│   ├── markdown.py              # GitHub-flavored Markdown and table helpers
│   ├── util.py                  # File I/O, hash calculation, dict helpers
│   └── cloud_functions/         # Webhook handler (Google Cloud Functions) to trigger GitHub Actions
│       ├── main.py
│       └── requirements.txt
├── tests/                       # Pytest test suite
│   ├── test_history_partition.py
│   ├── test_mapping.py
│   └── test_prepend.py
├── appscript/                   # Google Apps Script for syncing output CSVs into Google Sheets
│   ├── Code.js
│   ├── Settings.js
│   └── appsscript.json
├── .github/workflows/
│   └── run.yml                  # GitHub Actions workflow for scheduled and manual extraction
├── pyproject.toml               # Project metadata, Ruff & Pytest configuration
├── requirements.txt             # Production dependencies
├── requirements-dev.txt         # Development & testing dependencies
└── .pre-commit-config.yaml      # Pre-commit hooks configuration
```

---

## 3. Development Setup & Commands

### Virtual Environment
Always execute tests and scripts within the virtual environment:

```bash
# Activate existing virtualenv
source venv/bin/activate

# Or run tools directly via venv path:
./venv/bin/pytest
./venv/bin/ruff check .
./venv/bin/python ytm-dl.py frequent
```

### Running Tests
Run the full test suite using `pytest`:

```bash
./venv/bin/pytest
```

To run a specific test file or test case:
```bash
./venv/bin/pytest tests/test_history_partition.py
./venv/bin/pytest tests/test_prepend.py -k "test_find_history_overlap"
```

### Linting & Formatting
The codebase enforces strict linting and formatting via **Ruff**:
- **Line length**: 100 characters
- **Target Python**: Python 3.12+
- **Selected Rules**: `E`, `W`, `F`, `I` (isort), `UP` (pyupgrade), `B` (flake8-bugbear)

```bash
# Check linting and formatting
./venv/bin/ruff check .
./venv/bin/ruff format --check .

# Auto-fix lint issues and format files
./venv/bin/ruff check --fix .
./venv/bin/ruff format .
```

### Pre-commit Hooks
```bash
./venv/bin/pre-commit run --all-files
```

---

## 4. Architecture & Core Concepts

### 4.1. Execution Flow (`ytm-dl.py`)
1. **Invocation**: Accepts `all` or `frequent` CLI arguments:
   - `frequent`: Fetches `liked_songs`, `library_songs`, and `history`.
   - `all`: Fetches frequent items plus `home`, `library_subscriptions`, `library_artists`, `library_albums`, `library_upload_*`, and search suggestions (`search/suggest_by_letter.yaml`).
2. **Parallel Fetching**: Uses `concurrent.futures.ThreadPoolExecutor` to query endpoints concurrently.
3. **Output & Prepending**: Each endpoint passes through `Output(file, records, meta).write_files()`.
4. **Metadata & Artifacts**: Writes API execution metadata, file statistics, step summaries, and raw API responses to `artifacts/api_results_<timestamp>.yaml`.

### 4.2. Schema & Mapping Layer (`src/mapping.py`)
- **Marshmallow Schemas**: `SongSchema`, `HistorySchema`, `LikedSongSchema`, `ArtistSchema`, `AlbumSchema`, `HomeSchema`.
- **Primary Keys**:
  - Songs / History / Liked Songs: `videoId`
  - Artists / Albums: `browseId`
  - Home: `id` (resolved from `browseId`, `playlistId`, or `videoId`)
- **Timestamp Enrichment**:
  - `history.csv`: Uses `snap_relative_played_at()` to convert relative YTM strings (`Today`, `Yesterday`, `This week`, `Last week`, `Month Year`) into ISO UTC midnight timestamps (`YYYY-MM-DDTHH:MM:SSZ`).
  - `home.csv` & `liked_songs.csv`: Attaches `captured_at` or `liked_at` and `run_id`.

### 4.3. Prepend & Sequence Matching (`src/prepend.py`)
- **History Alignment**: YouTube Music history does not provide precise timestamps for historical plays. `find_history_overlap()` uses `difflib.SequenceMatcher` to find where newly fetched plays join the existing head of `history.csv`, avoiding duplicated plays while capturing repeated song listens.
- **Collection Deduplication**: Deduplicates collections (liked songs, library subscriptions/artists/albums) by primary key while preserving new additions at the top of the CSV.
- **Home Feed**: Snapshots each execution with current timestamp and prepends entire batch.

### 4.4. Monthly History Partitioning (`src/history_partition.py`)
- Master history lives in `output/history.csv`.
- `partition_history_csv()` splits records by `played_at` into `output/history/YYYY-MM.csv`.
- For incremental runs, only touched months (`target_months`) are regenerated to minimize I/O.

### 4.5. Authentication (`src/api.py`)
- Authentication is handled by `ytmusicapi` via either:
  1. `browser.json` (exported browser session headers)
  2. `oauth.json` (OAuth2 token credentials with `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET`)
- Thread-local client management (`get_thread_client()`) ensures thread safety during parallel execution.

---

## 5. Coding Guidelines & Best Practices for Agents

1. **Test Coverage**:
   - Any modifications to data transformation, schemas (`src/mapping.py`), prepending logic (`src/prepend.py`), or partitioning (`src/history_partition.py`) must be accompanied by comprehensive unit tests in `tests/`.
   - Maintain 100% test suite passing rate (`./venv/bin/pytest`).

2. **Code Style & Tooling**:
   - Use Python 3.11+ syntax (e.g. type unions `X | Y`, built-in generics).
   - Format with `ruff format` and ensure `ruff check .` passes without errors.
   - Keep docstrings clean and accurate for core algorithms.

3. **Data Integrity & Schema Consistency**:
   - When modifying schemas or column ordering, verify that column indexes in helper methods (e.g. `key_index`, `played_at_idx`) are dynamically resolved from `columns` where possible rather than hardcoded.
   - Never remove or mutate primary keys without updating all dependent modules (`output.py`, `prepend.py`, `mapping.py`).

4. **Safety & Secrets**:
   - **NEVER** commit `browser.json`, `oauth.json`, or `.env` files containing real API credentials.
   - Sensitive tokens (`YTM_BROWSER_AUTH`, `YTM_OAUTH`, `YTM_GITHUB_TOKEN`, `YTM_SHEET_UPDATE_URL`) are injected via environment variables in GitHub Actions.

5. **Branching Model Awareness**:
   - `main`: Application codebase, configuration, tests, workflows.
   - `main-output`: Automated target branch containing exported CSV/YAML datasets in `output/`.
