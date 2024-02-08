from ytmusicapi import YTMusic
from .util import write_file, make_dict_readonly
from .meta import MetaStore
import yaml
from time import time, strftime
import threading

def records_from_response(response):
	meta = {}
	if isinstance(response, dict) and 'tracks' in response.keys():
		records = response['tracks']
		del response['tracks']
		meta['Tracks'] = response
	else:
		records = response
	return [records, meta]

thread_local = threading.local()
def get_thread_client():
	if not hasattr(thread_local, "ytmusic"):
			thread_local.ytmusic = YTMusic("oauth.json")
	return thread_local.ytmusic


API_ARGUMENTS = {
	'get_history': {},
	'get_liked_songs': { 'limit': 500 },
	'get_library_songs': { 'limit': 500, 'order': 'recently_added' },
	'get_library_subscriptions': { 'limit': 25, 'order': 'recently_added' },
	'get_library_upload_songs': { 'limit': 500, 'order': 'recently_added' },
	'get_library_upload_artists': { 'limit': 50, 'order': 'recently_added' },
	'get_library_upload_albums': { 'limit': 50, 'order': 'recently_added' },
}
DEFAULT_ARGUMENTS = { 'limit': 2500, 'order': 'recently_added' }
make_dict_readonly(DEFAULT_ARGUMENTS)
make_dict_readonly(API_ARGUMENTS)

def suggest_search(search):
	return [search, get_thread_client().get_search_suggestions(search)]

class ApiMethod:
	@staticmethod
	def save_api_artifact():
		data = MetaStore.get('api_results').data
		if len(data) == 0:
			return
		time_str = strftime("%Y_%m_%d_%H_%M")
		write_file(f'artifacts/api_results_{time_str}.yaml', yaml.dump(data))

	def __init__(self, method):
		self.client = get_thread_client()
		self.method = method
		self.methodfn = getattr(self.client, method)
		self.method_args = dict(API_ARGUMENTS.get(method, DEFAULT_ARGUMENTS))


	def perform(self):
		start_time = time()
		api_results = self.methodfn(**self.method_args)
		self.elapsed_time = round(time() - start_time, 2)

		self.records, meta = records_from_response(api_results.copy())
		meta['API'] = self.api_meta

		MetaStore.get('api_results').add(self.method, api_results)
		MetaStore.get('api').add(self.method, meta['API'])
		return [self.records, meta]

	@property
	def api_meta(self):
		return  {
			'method': self.method,
			'args': self.method_args,
			'records_length': len(self.records),
			'time': self.elapsed_time
		}
