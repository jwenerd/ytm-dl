from ytmusicapi import YTMusic, OAuthCredentials
from .util import write_file, make_dict_readonly
from .meta import MetaStore
import yaml
from types import MappingProxyType
from time import time, strftime
import threading
import os

OAUTH_CLIENT_ID = os.environ['OAUTH_CLIENT_ID']
OAUTH_CLIENT_SECRET = os.environ['OAUTH_CLIENT_SECRET']

def records_from_response(response):
    meta = {}
    if isinstance(response, dict) and "tracks" in response.keys():
        records = response["tracks"]
        del response["tracks"]
        meta["Tracks"] = response
    else:
        records = response
    return [records, meta]


thread_local = threading.local()


def get_thread_client():
    if not hasattr(thread_local, "ytmusic"):
        thread_local.ytmusic = YTMusic("oauth.json", oauth_credentials=OAuthCredentials(client_id=OAUTH_CLIENT_ID, client_secret=OAUTH_CLIENT_SECRET))
    return thread_local.ytmusic


API_ARGUMENTS = {
    "get_history": {},
    "get_home": 9,
    "get_liked_songs": {"limit": 500},
    "get_library_songs": {"limit": 500, "order": "recently_added"},
    "get_library_subscriptions": {"limit": 25, "order": "recently_added"},
    "get_library_upload_songs": {"limit": 500, "order": "recently_added"},
    "get_library_upload_artists": {"limit": 50, "order": "recently_added"},
    "get_library_upload_albums": {"limit": 50, "order": "recently_added"},
    "get_library_artists": {"limit": 50, "order": "recently_added"},
    "get_library_albums": {"limit": 150, "order": "recently_added"},
}
DEFAULT_ARGUMENTS = {"limit": 2500, "order": "recently_added"}
make_dict_readonly(DEFAULT_ARGUMENTS)
make_dict_readonly(API_ARGUMENTS)


def suggest_search(search):
    return [search, get_thread_client().get_search_suggestions(search)]

def build_home_records(records):
    rows = []
    i = 0
    for tab in records:
        i = i + 1
        home_title = tab['title']
        for row in tab['contents']:
            artists = row.get('artists', [])
            if len(artists) and artists[0].get('name') == 'Song' and not artists[0].get('id'):
                row['type'] = 'Song'
                artists.pop(0)
            if not row.get('type') and row.get('playlistId'):
                row['type'] = 'Playlist' if not row.get('videoId') else 'Video'
            if not row.get('type') and row.get('subscribers'):
                row['type'] = 'Artist'
            row['home'] = home_title
            row['home_index'] = i
            row['id'] = row.get('browseId')
            if not row['id']:
                row['id'] = row.get('playlistId')
            if not row['id']:
                row['id'] = row.get('videoId')

            rows.append(row)
    return rows


class ApiMethod:
    @staticmethod
    def save_api_artifact():
        data = MetaStore.get("api_results").data
        if len(data) == 0:
            return
        time_str = strftime("%Y_%m_%d_%H_%M")
        write_file(f"artifacts/api_results_{time_str}.yaml", yaml.dump(data))

    def __init__(self, method):
        self.client = get_thread_client()
        self.method = method
        self.methodfn = getattr(self.client, method)
        self.method_args = API_ARGUMENTS.get(method, DEFAULT_ARGUMENTS)


    def perform(self):
        start_time = time()
        api_results = self.api_results()
        self.elapsed_time = round(time() - start_time, 2)

        self.records, meta = records_from_response(api_results.copy())
        if self.method == "get_home":
            self.records = build_home_records(self.records)

        meta["API"] = self.api_meta

        MetaStore.get("api_results").add(self.method, api_results)
        MetaStore.get("api").add(self.method, meta["API"])
        return [self.records, meta]

    def api_results(self):
        if isinstance(self.method_args, MappingProxyType):
            return self.methodfn(**dict(self.method_args))
        return self.methodfn(self.method_args)

    @property
    def api_meta(self):
        return {
            "method": self.method,
            "args": self.method_args,
            "records_length": len(self.records),
            "time": self.elapsed_time,
        }
