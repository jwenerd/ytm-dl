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


def parse_duration_seconds(record):
    """Extract or parse duration_seconds from a record dict."""
    duration = record.get("duration_seconds")
    if duration is not None and isinstance(duration, (int, float)) and duration > 0:
        return int(duration)
    d_str = record.get("duration")
    if d_str and isinstance(d_str, str) and ":" in d_str:
        parts = d_str.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            pass
    return None


def enrich_history_records(records, run_time=None, run_id=None):
    """
    Project playback timestamps backwards from run_time using duration_seconds
    and assign run_id for provenance tracking.
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

    current_time = run_time
    for record in records:
        if not isinstance(record, dict):
            continue
        duration = parse_duration_seconds(record)
        if "played_at" not in record or not record["played_at"]:
            if duration and duration > 0:
                current_time = current_time - timedelta(seconds=duration)
                record["played_at"] = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                record["played_at"] = ""
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
