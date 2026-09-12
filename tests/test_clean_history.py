import pytest
from src.clean_history import clean_history, find_duplicate_slices, NOISE_TRACK_IDS


def test_clean_history_synthetic_overlap():
    # Synthetic batch overlap:
    # Run 1: [D, E, F, G]
    # Run 2 prepended [A, B, C, D, E, F] (failed to trim [D, E, F])
    # Sequence is [A, B, C, D, E, F, D, E, F, G]
    rows = [
        ["Track A", "vA"],
        ["Track B", "vB"],
        ["Track C", "vC"],
        ["Track D", "vD"],
        ["Track E", "vE"],
        ["Track F", "vF"],
        ["Track D", "vD"],
        ["Track E", "vE"],
        ["Track F", "vF"],
        ["Track G", "vG"],
    ]
    cleaned, stats = clean_history(rows, key_idx=1, min_overlap=3, max_distance=10)
    assert stats["duplicate_blocks_found"] == 1
    assert stats["duplicate_rows_removed"] == 3
    # Expected: [A, B, C, D, E, F, G]
    expected_ids = ["vA", "vB", "vC", "vD", "vE", "vF", "vG"]
    assert [r[1] for r in cleaned] == expected_ids


def test_clean_history_preserves_legitimate_replays():
    # User listened to Track A, then B, C, D, and much later Track A, then E, F, G
    # These are not consecutive sub-sequences of length >= 4
    rows = [
        ["Track A", "vA"],
        ["Track B", "vB"],
        ["Track C", "vC"],
        ["Track D", "vD"],
        ["Track A", "vA"],  # Same track replayed later
        ["Track E", "vE"],
        ["Track F", "vF"],
        ["Track G", "vG"],
    ]
    cleaned, stats = clean_history(rows, key_idx=1, min_overlap=3, max_distance=10)
    assert stats["duplicate_blocks_found"] == 0
    assert stats["duplicate_rows_removed"] == 0
    assert len(cleaned) == 8


def test_clean_history_removes_noise_tracks():
    noise_key = list(NOISE_TRACK_IDS)[0]
    rows = [
        ["Normal Track 1", "v1"],
        ["Sleep Noise", noise_key],
        ["Normal Track 2", "v2"],
    ]
    cleaned, stats = clean_history(rows, key_idx=1, remove_noise=True)
    assert stats["noise_tracks_removed"] == 1
    assert len(cleaned) == 2
    assert [r[1] for r in cleaned] == ["v1", "v2"]


def test_clean_history_idempotent():
    rows = [
        ["Track A", "vA"],
        ["Track B", "vB"],
        ["Track C", "vC"],
        ["Track D", "vD"],
        ["Track B", "vB"],
        ["Track C", "vC"],
        ["Track D", "vD"],
        ["Track E", "vE"],
    ]
    cleaned_1, stats_1 = clean_history(rows, key_idx=1, min_overlap=3)
    cleaned_2, stats_2 = clean_history(cleaned_1, key_idx=1, min_overlap=3)
    assert stats_2["duplicate_blocks_found"] == 0
    assert cleaned_1 == cleaned_2
