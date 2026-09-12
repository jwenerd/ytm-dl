import os
from datetime import datetime, timezone, timedelta
import operator
from marshmallow import Schema, fields

class BaseSchema(Schema):
    primary_key: str = "id"

    @property
    def keys(self):
        return list(self.declared_fields.keys())


class ExtractNameStr(fields.String):
    def _serialize(self, value, attr, data, **kwargs) -> str | None:
        key = "name"
        if isinstance(value, list):
            value = self._join_list_value(value, key)
        if isinstance(value, dict) and key in value.keys():
            value = value[key]
        return super()._serialize(value, attr, data, **kwargs)

    def _join_list_value(self, values, key="name"):
        plucked = sorted(set(map(lambda t: t[key], values)))
        return ", ".join(plucked)


class SongSchema(BaseSchema):
    primary_key = "videoId"

    title = fields.Str()
    artists = ExtractNameStr()
    album = ExtractNameStr()
    duration = fields.Str()
    duration_seconds = fields.Int()
    videoId = fields.Str()

    @property
    def keys(self):
        keys = super().keys
        keys.remove("videoId")
        return keys + ["videoId"]


class HistorySchema(SongSchema):
    primary_key = "videoId"

    inLibrary = fields.Str()
    likeStatus = fields.Str()
    played_at = fields.Str()
    run_id = fields.Str()

    @property
    def keys(self):
        middle = ["inLibrary", "likeStatus"]
        trailing = ["played_at", "run_id"]
        keys = [k for k in super().keys if k not in middle and k not in trailing]
        for m in reversed(middle):
            keys.insert(keys.index("album") + 1, m)
        return keys + trailing


class ArtistSchema(BaseSchema):
    primary_key = "browseId"

    artist = fields.Str()
    browseId = fields.Str()


class AlbumSchema(BaseSchema):
    primary_key = "browseId"

    artists = ExtractNameStr()
    title = fields.Str()
    type = fields.Str()
    year = fields.Str()
    browseId = fields.Str()


class HomeSchema(BaseSchema):
    primary_key = "id"

    home = fields.Str()
    home_index = fields.Str()
    type = fields.Str()
    title = fields.Str()
    artists = ExtractNameStr()
    description = fields.Str()
    id = fields.Str()


SCHEMA_MAPPING = {
    "home": HomeSchema,
    "history": HistorySchema,
    "library_subscriptions": ArtistSchema,
    "_songs": SongSchema,
    "_artists": ArtistSchema,
    "_albums": AlbumSchema,
}


MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def snap_relative_played_at(played_str, run_time=None):
    """
    Snaps a relative 'played' string from YouTube Music (e.g. 'Today', 'Yesterday',
    'This week', 'Last week', 'August 2026') to a clean UTC midnight ISO timestamp.
    """
    if run_time is None:
        run_time = datetime.now(timezone.utc)

    ref_date = run_time.date() if isinstance(run_time, datetime) else run_time

    if not played_str or not isinstance(played_str, str):
        return f"{ref_date.isoformat()}T00:00:00Z"

    cleaned = played_str.strip().lower()

    if cleaned == "today":
        return f"{ref_date.isoformat()}T00:00:00Z"

    if cleaned == "yesterday":
        target_date = ref_date - timedelta(days=1)
        return f"{target_date.isoformat()}T00:00:00Z"

    if cleaned == "this week":
        # Snap to Monday (start) of current week
        target_date = ref_date - timedelta(days=ref_date.weekday())
        return f"{target_date.isoformat()}T00:00:00Z"

    if cleaned == "last week":
        # Snap to Monday (start) of previous week
        target_date = ref_date - timedelta(days=ref_date.weekday() + 7)
        return f"{target_date.isoformat()}T00:00:00Z"

    # Check for "<Month> <Year>" (e.g. "August 2026" or "Feb 2025")
    parts = cleaned.split()
    if len(parts) == 2:
        month_part, year_part = parts[0], parts[1]
        if month_part in MONTH_NAMES and year_part.isdigit() and len(year_part) == 4:
            month = MONTH_NAMES[month_part]
            year = int(year_part)
            return f"{year:04d}-{month:02d}-01T00:00:00Z"

    # Try parsing standard ISO date if passed
    try:
        dt = datetime.fromisoformat(played_str.strip())
        return f"{dt.date().isoformat()}T00:00:00Z"
    except Exception:
        pass

    # Default fallback: snap to run_time date at midnight
    return f"{ref_date.isoformat()}T00:00:00Z"


def enrich_history_records(records, run_time=None, run_id=None):
    """
    Snaps playback timestamps to relative midnight boundaries based on YTM's 'played' field
    and assigns run_id for provenance tracking.
    """
    if not records:
        return records

    if run_time is None:
        run_time = datetime.now(timezone.utc)
    if run_id is None:
        github_run = os.environ.get("GITHUB_RUN_NUMBER") or os.environ.get("GITHUB_RUN_ID")
        if github_run:
            run_id = f"gh-{github_run}"
        else:
            run_id = f"local_{run_time.strftime('%Y%m%d_%H%M%S')}"

    for record in records:
        if not isinstance(record, dict):
            continue
        if "played_at" not in record or not record["played_at"]:
            played_raw = record.get("played", "")
            record["played_at"] = snap_relative_played_at(played_raw, run_time)
        if "run_id" not in record or not record["run_id"]:
            record["run_id"] = run_id

    return records


class Mapping:
    def __init__(self, file, records):
        self.file: str = file
        self.records: list = records
        self.schema = self._find_schema()
        self.get_values = operator.itemgetter(*(self.columns))

    @property
    def columns(self):
        return self.schema.keys

    @property
    def primary_key(self):
        return getattr(self.schema, "primary_key", "id")

    @property
    def key_index(self):
        pk = self.primary_key
        if pk in self.columns:
            return self.columns.index(pk)
        return len(self.columns) - 1

    def _find_schema(self) -> BaseSchema:
        schema = SCHEMA_MAPPING.get(self.file, None)
        if not schema:
            key = [k for k in SCHEMA_MAPPING.keys() if self.file.endswith(k)]
            if key:
                schema = SCHEMA_MAPPING[key[0]]
        if not schema:
            raise Exception(f"Unable to locate schema for {self.file}")
        return schema()

    def _get_values(self, row):
        values = []
        for col in self.columns:
            values += [row.get(col, '')]
        return values

    def get_rows(self):
        records = self.records
        if self.file == "history":
            records = enrich_history_records(records)
        rows = self.schema.dump(records, many=True)
        return [self._get_values(row) for row in rows]
