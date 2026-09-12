import yaml

from src.catalog import (
    get_catalog_paths,
    merge_catalog_items,
    read_catalog,
    write_catalog_csv,
    write_catalog_yaml,
)
from src.util import resolve_meta_dir


def test_read_catalog_nonexistent(tmp_path):
    csv_path = str(tmp_path / "missing.csv")
    rows, lookup = read_catalog(csv_path, key_field="id")
    assert rows == []
    assert lookup == {}


def test_write_and_read_catalog_csv(tmp_path):
    csv_path = str(tmp_path / "test_catalog.csv")
    columns = ["id", "title", "first_seen", "last_seen", "times_recommended", "latest_position"]
    rows = [
        {
            "id": "1",
            "title": "Item 1",
            "first_seen": "2026-09-12T10:00:00Z",
            "last_seen": "2026-09-12T10:00:00Z",
            "times_recommended": "1",
            "latest_position": "1",
        },
        {
            "id": "2",
            "title": "Item 2",
            "first_seen": "2026-09-12T10:00:00Z",
            "last_seen": "2026-09-12T10:00:00Z",
            "times_recommended": "2",
            "latest_position": "2",
        },
    ]

    write_catalog_csv(csv_path, columns, rows)
    loaded_rows, lookup = read_catalog(csv_path, key_field="id")

    assert len(loaded_rows) == 2
    assert loaded_rows[0]["id"] == "1"
    assert loaded_rows[1]["id"] == "2"
    assert "1" in lookup
    assert "2" in lookup
    assert lookup["2"]["times_recommended"] == "2"


def test_merge_catalog_items_inplace_and_prepend():
    now_iso = "2026-09-12T12:00:00Z"
    existing_rows = [
        {
            "id": "item_A",
            "title": "Item A",
            "first_seen": "2026-09-01T00:00:00Z",
            "last_seen": "2026-09-01T00:00:00Z",
            "times_recommended": "1",
            "latest_position": "1",
        },
        {
            "id": "item_B",
            "title": "Item B",
            "first_seen": "2026-09-01T00:00:00Z",
            "last_seen": "2026-09-01T00:00:00Z",
            "times_recommended": "3",
            "latest_position": "2",
        },
    ]
    existing_lookup = {r["id"]: r for r in existing_rows}

    # Incoming items: item_C (new) and item_A (existing)
    new_items = [
        {"id": "item_C", "title": "Item C"},
        {"id": "item_A", "title": "Item A Updated"},
    ]

    def make_new(item, pos, dt_iso):
        return {
            "id": item["id"],
            "title": item["title"],
            "first_seen": dt_iso,
            "last_seen": dt_iso,
            "times_recommended": "1",
            "latest_position": str(pos),
        }

    merged, new_count, updated_count = merge_catalog_items(
        existing_rows=existing_rows,
        existing_lookup=existing_lookup,
        new_items=new_items,
        key_field="id",
        now_iso=now_iso,
        make_new_row_fn=make_new,
    )

    assert new_count == 1
    assert updated_count == 1
    assert len(merged) == 3

    # item_C must be prepended at index 0
    assert merged[0]["id"] == "item_C"
    assert merged[0]["first_seen"] == now_iso
    assert merged[0]["last_seen"] == now_iso
    assert merged[0]["times_recommended"] == "1"
    assert merged[0]["latest_position"] == "1"

    # item_A remains at index 1 (its original line) and is updated in-place
    assert merged[1]["id"] == "item_A"
    assert merged[1]["first_seen"] == "2026-09-01T00:00:00Z"
    assert merged[1]["last_seen"] == now_iso
    assert merged[1]["times_recommended"] == "2"
    assert merged[1]["latest_position"] == "2"

    # item_B remains at index 2 untouched
    assert merged[2]["id"] == "item_B"
    assert merged[2]["times_recommended"] == "3"


def test_write_catalog_yaml_preserves_first_captured(tmp_path):
    yaml_path = str(tmp_path / "test_meta.yaml")

    meta_run1 = {
        "title": "Shelf 1",
        "first_captured": "2026-09-01T00:00:00Z",
        "last_captured": "2026-09-01T00:00:00Z",
        "total_items": 10,
    }
    write_catalog_yaml(yaml_path, meta_run1)

    meta_run2 = {
        "title": "Shelf 1",
        "first_captured": "2026-09-12T12:00:00Z",  # should be overwritten by original
        "last_captured": "2026-09-12T12:00:00Z",
        "total_items": 15,
    }
    write_catalog_yaml(yaml_path, meta_run2)

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    assert data["first_captured"] == "2026-09-01T00:00:00Z"
    assert data["last_captured"] == "2026-09-12T12:00:00Z"
    assert data["total_items"] == 15


def test_resolve_meta_dir():
    assert resolve_meta_dir("output/mixes") == "output/meta/mixes"
    assert resolve_meta_dir("output/home") == "output/meta/home"
    assert resolve_meta_dir("/tmp/test/home") == "/tmp/test/meta/home"
    assert resolve_meta_dir("home") == "meta/home"


def test_get_catalog_paths():
    csv_path, yaml_path = get_catalog_paths("output/mixes", "chill_supermix")
    assert csv_path == "output/mixes/chill_supermix.csv"
    assert yaml_path == "output/meta/mixes/chill_supermix.yaml"

    csv_custom, yaml_custom = get_catalog_paths(
        "output/home", "quick_picks", meta_base_dir="custom/meta"
    )
    assert csv_custom == "output/home/quick_picks.csv"
    assert yaml_custom == "custom/meta/quick_picks.yaml"
