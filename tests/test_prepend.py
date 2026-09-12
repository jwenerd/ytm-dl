import os
import csv
import pytest
from src.prepend import (
    get_existing_ids,
    find_history_overlap,
    prepend_rows_for_file,
)


def test_find_history_overlap_empty():
    assert find_history_overlap([], ["v1", "v2"]) == 2


def test_find_history_overlap_no_new():
    existing = ["v1", "v2", "v3", "v4"]
    new = ["v1", "v2", "v3", "v4"]
    assert find_history_overlap(existing, new) == 0


def test_find_history_overlap_new_plays():
    existing = ["v3", "v4", "v5"]
    new = ["v1", "v2", "v3", "v4", "v5"]
    assert find_history_overlap(existing, new) == 2


def test_find_history_overlap_with_repeats():
    # User listened to v1, then v2, then v1 again (newest is v1, then v2)
    # Previous history started with [v1, v3, v4]
    existing = ["v1", "v3", "v4"]
    new = ["v1", "v2", "v1", "v3", "v4"]
    # Overlap starts at index 2 where new[2:] == ["v1", "v3", "v4"]
    assert find_history_overlap(existing, new) == 2


def test_find_history_overlap_disjoint():
    existing = ["v10", "v11", "v12"]
    new = ["v1", "v2", "v3"]
    assert find_history_overlap(existing, new) is None


def test_find_history_overlap_approximate():
    # One song missing from new fetch compared to existing (e.g. video deleted)
    existing = ["v1", "v2", "v_deleted", "v3", "v4", "v5"]
    new = ["v_new", "v1", "v2", "v3", "v4", "v5"]
    # Should match at index 1 with sequence similarity
    assert find_history_overlap(existing, new, min_ratio=0.7) == 1


def test_prepend_rows_for_history(tmp_path):
    csv_file = tmp_path / "history.csv"
    # Write header and existing rows
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "artist", "videoId"])
        writer.writerow(["Song 2", "Artist 2", "vid2"])
        writer.writerow(["Song 3", "Artist 3", "vid3"])

    # New batch has Song 1 (new play) followed by Song 2 and Song 3
    new_rows = [
        ["Song 1", "Artist 1", "vid1"],
        ["Song 2", "Artist 2", "vid2"],
        ["Song 3", "Artist 3", "vid3"],
    ]

    rows_to_prepend = prepend_rows_for_file(
        str(csv_file), new_rows, is_history=True, key_index=2
    )
    assert len(rows_to_prepend) == 1
    assert rows_to_prepend[0] == ["Song 1", "Artist 1", "vid1"]


def test_prepend_rows_for_collections(tmp_path):
    csv_file = tmp_path / "liked_songs.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "artist", "videoId"])
        writer.writerow(["Song 2", "Artist 2", "vid2"])
        writer.writerow(["Song 3", "Artist 3", "vid3"])

    # New batch has a new song (vid1) and existing songs (vid2, vid3)
    new_rows = [
        ["Song 1", "Artist 1", "vid1"],
        ["Song 2", "Artist 2", "vid2"],
        ["Song 1 Duplicate", "Artist 1", "vid1"],  # duplicate in batch
    ]

    rows_to_prepend = prepend_rows_for_file(
        str(csv_file), new_rows, is_history=False, key_index=2
    )
    assert len(rows_to_prepend) == 1
    assert rows_to_prepend[0] == ["Song 1", "Artist 1", "vid1"]


def test_prepend_rows_for_home(tmp_path):
    csv_file = tmp_path / "home.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["home", "home_index", "type", "title", "artists", "description", "id", "captured_at", "run_id"])
        writer.writerow(["Listen again", "1", "Song", "Song 2", "Artist 2", "", "vid2", "2026-09-10T00:00:00Z", "gh-1"])

    # New home snapshot includes previously seen items with new timestamp
    new_snapshot = [
        ["Listen again", "1", "Song", "Song 1", "Artist 1", "", "vid1", "2026-09-12T00:00:00Z", "gh-2"],
        ["Listen again", "1", "Song", "Song 2", "Artist 2", "", "vid2", "2026-09-12T00:00:00Z", "gh-2"],
    ]

    rows_to_prepend = prepend_rows_for_file(
        str(csv_file), new_snapshot, is_home=True
    )
    # Entire snapshot should be returned for prepending
    assert len(rows_to_prepend) == 2
    assert rows_to_prepend == new_snapshot


def test_get_existing_ids(tmp_path):
    csv_file = tmp_path / "test.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["col0", "col1", "col2"])
        writer.writerow(["a", "b", "c"])
        writer.writerow(["d", "e", "f"])

    assert get_existing_ids(str(csv_file), key_index=0) == ["a", "d"]
    assert get_existing_ids(str(csv_file), key_index=1) == ["b", "e"]
    assert get_existing_ids(str(csv_file), key_index=2) == ["c", "f"]
