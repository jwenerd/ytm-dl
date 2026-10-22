# ytm-dl

Automated YouTube Music data synchronization engine and continuous private library archive.

---

### 📂 Repository Portals & Archive

- [Output Archive](https://github.com/jwenerd/ytm-dl/tree/main-output/output)
- [Latest Ingestion Commit](https://github.com/jwenerd/ytm-dl/commit/main-output)
- [AI Listening Reports & Discovery Radar](https://github.com/jwenerd/ytm-dl/blob/main-output/output/reports/README.md)
  - [daily](https://github.com/jwenerd/ytm-dl/blob/main-output/output/reports/daily.md) · [weekly](https://github.com/jwenerd/ytm-dl/blob/main-output/output/reports/weekly.md) · [monthly](https://github.com/jwenerd/ytm-dl/blob/main-output/output/reports/monthly.md) · [archive](https://github.com/jwenerd/ytm-dl/tree/main-output/output/reports/archive)
- [Agent & Architecture Guide](AGENTS.md)
- [Commit History](https://github.com/jwenerd/ytm-dl/commits/main-output/output)
  - [yesterday](https://github.com/jwenerd/ytm-dl/compare/main-output@%7Byesterday%7D..main-output?diff=unified&w=1) · [past 3 days](https://github.com/jwenerd/ytm-dl/compare/main-output@%7B3%20days%20ago%7D..main-output?diff=unified&w=1) · [past week](https://github.com/jwenerd/ytm-dl/compare/main-output@%7B1%20week%20ago%7D..main-output?diff=unified&w=1) · [past 2 weeks](https://github.com/jwenerd/ytm-dl/compare/main-output@%7B2%20weeks%20ago%7D..main-output?diff=unified&w=1) · [past month](https://github.com/jwenerd/ytm-dl/compare/main-output@%7B1%20month%20ago%7D..main-output?diff=unified&w=1)

---

### ⚙️ Pipeline Status

[![run](https://github.com/jwenerd/ytm-dl/actions/workflows/run.yml/badge.svg?branch=main&event=schedule)](https://github.com/jwenerd/ytm-dl/actions/workflows/run.yml)
[![pr-ci](https://github.com/jwenerd/ytm-dl/actions/workflows/pr.yml/badge.svg?branch=main)](https://github.com/jwenerd/ytm-dl/actions/workflows/pr.yml)

`🎶 🎸 🎵 🎷 🎶 🪕 🎵 🎻 🎶 🎹 🎵 🔉 🎶`

---

## 📊 Tracked Datasets

All exported datasets reside on the dedicated `main-output` branch:

| Metric / Collection | Dataset | Description |
| :--- | :--- | :--- |
| **Listening History** | [`output/history.csv`](https://github.com/jwenerd/ytm-dl/blob/main-output/output/history.csv) | Continuous sequence-aligned playback history with ISO UTC timestamps |
| **Monthly Archive** | [`output/history/YYYY-MM.csv`](https://github.com/jwenerd/ytm-dl/tree/main-output/output/history) | Partitioned historical listening history by calendar month |
| **Liked Songs** | [`output/liked_songs.csv`](https://github.com/jwenerd/ytm-dl/blob/main-output/output/liked_songs.csv) | Deduplicated liked tracks with like timestamps |
| **Home Feed Radar** | [`output/home.csv`](https://github.com/jwenerd/ytm-dl/blob/main-output/output/home.csv) | Periodic snapshots of recommendation shelves & quick picks |
| **Mood & Energy Mixes** | [`output/mixes/`](https://github.com/jwenerd/ytm-dl/tree/main-output/output/mixes) | Catalogs for Supermix, Energy, Focus, Relax, and Workout mixes |
| **Library Songs** | [`output/library_songs.csv`](https://github.com/jwenerd/ytm-dl/blob/main-output/output/library_songs.csv) | Saved library tracks |
| **Library Artists** | [`output/library_artists.csv`](https://github.com/jwenerd/ytm-dl/blob/main-output/output/library_artists.csv) | Subscribed library artists |
| **Library Albums** | [`output/library_albums.csv`](https://github.com/jwenerd/ytm-dl/blob/main-output/output/library_albums.csv) | Saved library albums |
| **Library Uploads** | [`output/library_upload_*.csv`](https://github.com/jwenerd/ytm-dl/tree/main-output/output) | Personal user uploads (songs, artists, albums) |
| **AI Reports** | [`output/reports/`](https://github.com/jwenerd/ytm-dl/tree/main-output/output/reports) | Daily, weekly, and monthly musicological listening reports |

---

## 🛠️ Local Usage & Execution

```bash
# Frequent sync: history, liked songs, library songs
python ytm-dl.py frequent

# Full sync: frequent + home feed, uploads, subscriptions, mood mixes, search suggestions
python ytm-dl.py all

# Run or force AI listening report generation
python ytm-dl.py report [daily|weekly|monthly|all]
```

---

## 🧪 Development & Quality Assurance

A unified CLI runner is provided for developers and AI agents via `scripts/dev.py`:

```bash
# Run complete pre-flight CI validation (boundaries, ruff, pytest, diff-cover)
python scripts/dev.py check

# Fast check (skips diff-cover gate against origin)
python scripts/dev.py check --fast

# Automatically fix linting, formatting, and imports
python scripts/dev.py fix

# Run pytest suite (supports passthrough flags)
python scripts/dev.py test
python scripts/dev.py test -k test_prepend

# Run test coverage with XML/Markdown export
python scripts/dev.py cov

# Audit branch boundaries (ensures no data files or secrets on main)
python scripts/dev.py boundary
```
