from marshmallow import Schema, fields
import operator

class BaseSchema(Schema):
    @property
    def keys(self):
        return list(self.declared_fields.keys())


# class HomeType(fields.String):
#     def _serialize(self, value, attr, data, **kwargs) -> str | None:
#         key = "name"
#         if not value and data.get("playlistId"):
#             value = "playlist"
#         value = str(value).lower()
#         return super()._serialize(value, attr, data, **kwargs)

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
    inLibrary = fields.Str()
    likeStatus = fields.Str()

    @property
    def keys(self):
        middle = ["inLibrary", "likeStatus"]
        keys = [k for k in super().keys if (not k in middle)]
        for m in reversed(middle):
            keys.insert(keys.index("album") + 1, m)
        return keys


class ArtistSchema(BaseSchema):
    artist = fields.Str()
    browseId = fields.Str()


class AlbumSchema(BaseSchema):
    artists = ExtractNameStr()
    title = fields.Str()
    type = fields.Str()
    year = fields.Str()
    browseId = fields.Str()

class HomeSchema(BaseSchema):
    home = fields.Str()
    home_index = fields.Str()
    type = fields.Str()
    title = fields.Str()
    artists = ExtractNameStr()
    description = fields.Str()

SCHEMA_MAPPING = {
    "home": HomeSchema,
    "history": HistorySchema,
    "library_subscriptions": ArtistSchema,
    "_songs": SongSchema,
    "_artists": ArtistSchema,
    "_albums": AlbumSchema,
}


class Mapping:
    def __init__(self, file, records):
        self.file: str = file
        self.records: list = records
        self.schema = self._find_schema()
        self.get_values = operator.itemgetter(*(self.columns))

    @property
    def columns(self):
        return self.schema.keys

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
        rows = self.schema.dump(self.records, many=True)
        return [self._get_values(row) for row in rows]
