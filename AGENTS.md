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

ytm-dl/
├── ytm-dl.py                     # Main CLI entrypoint and execution orchestrator
├── scripts/                      # Developer and agent workflow automation
│   ├── dev.py                   # Unified pre-flight CI check, lint, format, and test CLI
│   ├── check_boundaries.py      # Branch boundary and secret leak enforcement
│   └── format_pr_coverage.py    # Scoped PR coverage comment formatter
├── src/
│   ├── api.py                   # ytmusicapi client wrapper, auth handling, API call dispatch
│   ├── catalog.py               # Shared tabular catalog export engine
│   ├── changes.py               # Runtime changes and step summary tracker
│   ├── history_partition.py     # Partitioning history CSV into monthly archives
│   ├── home_catalog.py          # Recommendations and home catalog extraction
│   ├── mapping.py               # Marshmallow schemas, field mappings, timestamp/run_id enrichment
│   ├── markdown.py              # GitHub-flavored Markdown and table helpers
│   ├── meta.py                  # Metadata tracking, file statistics, step summaries, README generation
│   ├── mood_mixes.py            # Mood and energy mix discovery engine
│   ├── output.py                # Output manager, CSV/YAML writes, prepend orchestrator
│   ├── prepend.py               # Sequence alignment & deduplication logic for prepending
│   ├── reports/                 # AI listening reports & discovery radar engine
│   │   ├── aggregator.py        # Telemetry aggregation & recommendation radar filtering
│   │   ├── email_template.py    # Rich dark-mode HTML email template generator
│   │   ├── generator.py         # Lightweight Gemini REST client (requests)
│   │   ├── mailer.py            # Report mailer and webhook dispatcher
│   │   ├── prompt.py            # Musicologist prompt engineering & deterministic fallback
│   │   └── rotator.py           # Lazy-man cron cadence checker & archive rotation
│   ├── util.py                  # File I/O, hash calculation, dict helpers
│   └── cloud_functions/         # Webhook handler (Google Cloud Functions) to trigger GitHub Actions
│       ├── main.py
│       └── requirements.txt
├── tests/                       # Pytest test suite
│   ├── test_branch_boundaries.py
│   ├── test_coverage_formatter.py
│   ├── test_dev_runner.py
│   ├── test_history_partition.py
│   ├── test_mapping.py
│   ├── test_prepend.py
│   ├── test_report_aggregator.py
│   ├── test_report_generator.py
│   └── test_report_rotator.py
├── .githooks/                   # Git hooks preventing accidental direct pushes to main
│   └── pre-push
├── .github/
│   ├── pull_request_template.md # PR quality and verification checklist
│   └── workflows/
│       ├── run.yml              # Scheduled and manual sync extraction
│       ├── pr.yml               # Automated PR CI validation & coverage commenting
│       └── guard-main.yml       # Branch boundary and PR commit auditor
├── pyproject.toml               # Project metadata, Ruff, coverage, and Pytest configuration
├── requirements.txt             # Production dependencies
├── requirements-dev.txt         # Development, coverage & testing dependencies
└── .pre-commit-config.yaml      # Pre-commit hooks configuration
```

---

## 3. Development Setup & Commands

### 3.1. Unified Developer & Agent CLI (`scripts/dev.py`)
A single orchestrator CLI is provided for local developers and AI agents to ensure complete parity with GitHub Actions CI:

```bash
# Run complete pre-flight check (Branch boundaries -> Ruff lint -> Ruff format -> Pytest + Coverage -> Diff coverage gate)
python scripts/dev.py check

# Fast check (skips diff-cover against base branch)
python scripts/dev.py check --fast

# Auto-fix linting issues, import sorting, and formatting with Ruff
python scripts/dev.py fix

# Check linting and formatting without mutating files
python scripts/dev.py lint

# Run branch boundary audit (verifies no output data, artifacts, or secrets on main)
python scripts/dev.py boundary

# Run pytest test suite (supports all pytest flags like -k or specific files)
python scripts/dev.py test
python scripts/dev.py test -k test_prepend

# Run full test suite with coverage analysis (exports tmp/coverage.md & tmp/coverage.xml)
python scripts/dev.py cov
```

### 3.2. Git Pre-Push Hook (Safety Guard)
To prevent accidental pushes to `main` (which should always be updated via Pull Requests):

```bash
# Configure local repository to use .githooks/
git config core.hooksPath .githooks
```

In the event of an emergency hotfix, the hook can be bypassed:
```bash
ALLOW_MAIN_PUSH=1 git push origin main
```

### 3.3. Virtual Environment
Always execute tests and scripts within the virtual environment:

```bash
# Activate existing virtualenv
source venv/bin/activate

# Or run tools directly via venv path:
./venv/bin/pytest
./venv/bin/ruff check .
./venv/bin/python ytm-dl.py frequent
```

### 3.4. Pre-commit Hooks
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

### 4.6. AI Listening Reports & Discovery Radar (`src/reports/`)
- **Cadence & Rotation**: Automatically generates `daily.md`, `weekly.md`, and `monthly.md` reports in `output/reports/`.
- **Lazy-Man Cron**: During standard sync runs (`frequent` or `all`), `src/reports/rotator.py` checks `output/meta/reports.yaml` to detect if a new day, ISO week, or month threshold has elapsed.
- **Archive Rotation**: Previous reports are automatically rotated to `output/reports/archive/{cadence}/YYYY/{period}.md` and indexed in `output/reports/README.md`.
- **Recommendation Shelves**: Correlates listening history against 5 shelves (`your_daily_discover`, `discover_mix`, `new_releases`, `quick_picks`, `mixed_for_you`).
- **Zero-Dependency Gemini Client**: Uses `requests` with `gemini-3.8-flash` via `GOOGLE_AI_API_KEY`. Gracefully falls back to deterministic markdown when offline.
- **CLI Commands**:
  - `python ytm-dl.py report` (checks lazy-man cadence)
  - `python ytm-dl.py report [daily|weekly|monthly|all]` (forces generation)

### 4.7. Where to Make Changes

| Task | Package File | Facade / Entry Point | Function / Section |
|---|---|---|---|
| **Add or update data schemas** | `src/mapping.py` | — | `SongSchema`, `HistorySchema`, `LikedSongSchema`, etc. |
| **Modify API call or client auth** | `src/api.py` | `src/api.py` | `ApiMethod`, `get_auth_info`, `validate_auth` |
| **Update history alignment & prepend** | `src/prepend.py` | `src/output.py` | `find_history_overlap`, `prepend_rows_for_file` |
| **Modify monthly history partitioning** | `src/history_partition.py` | `src/history_partition.py` | `partition_history_csv` |
| **Home feed & recommendation catalogs** | `src/home_catalog.py` | `ytm-dl.py` | `sync_home_catalogs`, `parse_home_item` |
| **Mood and energy mix discovery** | `src/mood_mixes.py` | `ytm-dl.py` | `sync_all_mood_mixes` |
| **AI report prompts & radar filtering** | `src/reports/prompt.py` & `src/reports/aggregator.py` | `src/reports/rotator.py` | `build_report_prompt`, `assemble_report_context` |
| **Report HTML email rendering** | `src/reports/email_template.py` | `src/reports/mailer.py` | `markdown_to_email_html` |
| **Report mailer & webhook dispatch** | `src/reports/mailer.py` | `ytm-dl.py report` | `send_report_email` |
| **Branch boundary & secret protection** | `scripts/check_boundaries.py` | `scripts/dev.py` | `is_boundary_violation`, `main` |
| **Developer CLI runner & pre-flight** | `scripts/dev.py` | `scripts/dev.py` | `cmd_check`, `cmd_fix`, `cmd_lint`, `cmd_test` |
| **PR coverage formatting & sticky comments**| `scripts/format_pr_coverage.py` | `.github/workflows/pr.yml` | `generate_pr_comment`, `main` |
| **PR CI workflows & commit auditing** | `.github/workflows/` | `pr.yml` & `guard-main.yml` | GitHub Actions steps |

---

## 5. Agent Rules of Engagement & Best Practices

1. **Preserve Branch Boundaries (Rule 1)**:
   - **NEVER** commit `output/` files, runtime artifacts (`artifacts/`), or credentials (`browser.json`, `oauth.json`, `.env`) to `main`.
   - `main-output` is the designated orphan data branch for synchronization exports.
   - Guarded locally and in CI via `python scripts/check_boundaries.py`.

2. **100% PR Diff Coverage Gate**:
   - Any new or modified production code must be accompanied by unit tests in `tests/`.
   - Pull Requests enforce a 100% diff coverage gate via `diff-cover`. Uncovered lines in PR diffs block merging.

3. **Pre-Flight CI Parity**:
   - Before opening or proposing a PR, always execute `python scripts/dev.py check`.
   - Use `python scripts/dev.py fix` to automatically correct formatting and linting.

4. **Data Integrity & Schema Consistency**:
   - When modifying schemas or column ordering in `src/mapping.py`, verify dynamic column resolution (`key_index`) in `output.py` and `prepend.py`.
   - Never alter primary keys without updating dependent modules.

5. **Safety & Secrets**:
   - **NEVER** commit real API credentials or session tokens.
   - Sensitive tokens are injected exclusively via environment variables in GitHub Actions (`YTM_BROWSER_AUTH`, `YTM_OAUTH`, `YTM_GITHUB_TOKEN`).

6. **Git Commit & Push Authorization**:
   - **NEVER** run `git commit` or `git push` to `main` (or any remote branch) without the user explicitly requesting a commit/push in their prompt.
   - Always propose changes, run validations via `scripts/dev.py check`, and await explicit confirmation.
