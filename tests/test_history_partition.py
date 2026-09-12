import csv
import os
import tempfile

from src.history_partition import (
    extract_month_from_timestamp,
    get_months_from_rows,
    partition_history_csv,
)


def test_extract_month_from_timestamp():
    assert extract_month_from_timestamp("2026-09-12T01:30:00Z") == "2026-09"
    assert extract_month_from_timestamp("2024-01-01T00:00:00Z") == "2024-01"
    assert extract_month_from_timestamp("2025-12-31T23:59:59-07:00") == "2025-12"
    # Fallback to current year-month on empty/invalid
    fallback = extract_month_from_timestamp("")
    assert len(fallback) == 7 and fallback[4] == "-"


def test_get_months_from_rows():
    rows = [
        [
            "Song 1",
            "Artist 1",
            "Album",
            "true",
            "LIKE",
            "3:00",
            "180",
            "vid1",
            "2026-09-10T12:00:00Z",
            "gh-1",
        ],
        [
            "Song 2",
            "Artist 2",
            "Album",
            "true",
            "LIKE",
            "3:00",
            "180",
            "vid2",
            "2026-09-01T12:00:00Z",
            "gh-1",
        ],
        [
            "Song 3",
            "Artist 3",
            "Album",
            "false",
            "INDIFFERENT",
            "3:00",
            "180",
            "vid3",
            "2026-08-31T23:50:00Z",
            "gh-1",
        ],
    ]
    months = get_months_from_rows(rows, played_at_idx=8)
    assert months == {"2026-09", "2026-08"}


def test_partition_history_csv_full():
    header = [
        "title",
        "artists",
        "album",
        "inLibrary",
        "likeStatus",
        "duration",
        "duration_seconds",
        "videoId",
        "played_at",
        "run_id",
    ]
    rows = [
        [
            "Song 1",
            "Artist 1",
            "Album 1",
            "true",
            "LIKE",
            "3:30",
            "210",
            "vid1",
            "2026-09-12T00:00:00Z",
            "gh-100",
        ],
        [
            "Song 2",
            "Artist 2",
            "Album 2",
            "true",
            "LIKE",
            "4:00",
            "240",
            "vid2",
            "2026-09-10T00:00:00Z",
            "gh-99",
        ],
        [
            "Song 3",
            "Artist 3",
            "Album 3",
            "false",
            "INDIFFERENT",
            "2:45",
            "165",
            "vid3",
            "2026-08-15T00:00:00Z",
            "gh-98",
        ],
        [
            "Song 4",
            "Artist 4",
            "Album 4",
            "false",
            "INDIFFERENT",
            "3:15",
            "195",
            "vid4",
            "2025-12-25T00:00:00Z",
            "gh-97",
        ],
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        master_csv = os.path.join(tmp_dir, "history.csv")
        history_dir = os.path.join(tmp_dir, "history")

        with open(master_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)

        results = partition_history_csv(master_csv, output_dir=history_dir)

        assert results == {
            "2026-09": 2,
            "2026-08": 1,
            "2025-12": 1,
        }

        # Check 2026-09.csv content & order
        sep_csv = os.path.join(history_dir, "2026-09.csv")
        assert os.path.exists(sep_csv)
        with open(sep_csv, newline="", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            assert reader[0] == header
            assert len(reader) == 3
            assert reader[1][0] == "Song 1"  # Preserves newest first
            assert reader[2][0] == "Song 2"

        # Check 2026-08.csv
        aug_csv = os.path.join(history_dir, "2026-08.csv")
        assert os.path.exists(aug_csv)
        with open(aug_csv, newline="", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            assert len(reader) == 2
            assert reader[1][0] == "Song 3"


def test_partition_history_csv_targeted():
    header = [
        "title",
        "artists",
        "album",
        "inLibrary",
        "likeStatus",
        "duration",
        "duration_seconds",
        "videoId",
        "played_at",
        "run_id",
    ]
    rows = [
        [
            "Song New",
            "Artist 1",
            "Album 1",
            "true",
            "LIKE",
            "3:30",
            "210",
            "vidNew",
            "2026-09-15T00:00:00Z",
            "gh-101",
        ],
        [
            "Song 1",
            "Artist 1",
            "Album 1",
            "true",
            "LIKE",
            "3:30",
            "210",
            "vid1",
            "2026-09-12T00:00:00Z",
            "gh-100",
        ],
        [
            "Song Old",
            "Artist Old",
            "Album Old",
            "false",
            "INDIFFERENT",
            "3:00",
            "180",
            "vidOld",
            "2026-07-01T00:00:00Z",
            "gh-50",
        ],
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        master_csv = os.path.join(tmp_dir, "history.csv")
        history_dir = os.path.join(tmp_dir, "history")

        with open(master_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)

        # Regenerate ONLY 2026-09
        results = partition_history_csv(
            master_csv, output_dir=history_dir, target_months=["2026-09"]
        )

        assert results == {"2026-09": 2}
        assert os.path.exists(os.path.join(history_dir, "2026-09.csv"))
        assert not os.path.exists(os.path.join(history_dir, "2026-07.csv"))


def test_output_history_integration(monkeypatch):
    import src.output as output_module
    from src.output import Output

    with tempfile.TemporaryDirectory() as tmp_dir:

        def mock_output_path(file=""):
            if file:
                return os.path.join(tmp_dir, file)
            return tmp_dir

        monkeypatch.setattr(output_module, "output_path", mock_output_path)
        monkeypatch.setattr("src.meta.output_path", mock_output_path)
        monkeypatch.setattr("src.util.output_path", mock_output_path)

        records = [
            {
                "title": "Song A",
                "artists": [{"name": "Artist A"}],
                "album": {"name": "Album A"},
                "duration": "3:00",
                "duration_seconds": 180,
                "videoId": "vidA",
                "played": "Today",
            },
            {
                "title": "Song B",
                "artists": [{"name": "Artist B"}],
                "album": {"name": "Album B"},
                "duration": "4:00",
                "duration_seconds": 240,
                "videoId": "vidB",
                "played": "Today",
            },
        ]

        out = Output("history", records)
        out.write_files()

        # Check master history.csv
        master_csv = os.path.join(tmp_dir, "history.csv")
        assert os.path.exists(master_csv)

        # Check monthly history file
        month_dir = os.path.join(tmp_dir, "history")
        assert os.path.isdir(month_dir)
        files = os.listdir(month_dir)
        assert len(files) == 1
        month_file = os.path.join(month_dir, files[0])
        with open(month_file, newline="", encoding="utf-8") as f:
            lines = list(csv.reader(f))
            assert len(lines) == 3  # Header + 2 songs
            assert lines[0][0] == "title"
