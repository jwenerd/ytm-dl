from ytmusicapi import YTMusic
from .util import write_file
from .meta import MetaStore
import yaml
import time
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

class ApiMethod:

	all_api_results = {}

	@staticmethod
	def save_api_artifact():
		data = MetaStore.get('api_results').data
		if len(data) == 0:
			return
		time_str = time.strftime("%Y_%m_%d_%H_%M")
		write_file(f'artifacts/api_results_{time_str}.yaml', yaml.dump(data))

	def __init__(self, method):
		self.client = get_thread_client()
		self.method = method
		self.methodfn = getattr(self.client, method)
		self.method_args = {
			'get_history': {},
			'get_liked_songs': { 'limit': 500 },
			'get_library_songs': { 'limit': 500, 'order': 'recently_added' }
		}.get(method, { 'limit': 2500, 'order': 'recently_added' })

	def perform(self):
		start_time = time.time()
		api_results = self.methodfn(**self.method_args)
		elapsed_time = round(time.time() - start_time, 3)

		records, meta = records_from_response(api_results.copy())
		meta['API'] = {
			'method': self.method, 'args': self.method_args,
			'records_length': len(records), 'time': elapsed_time
		}
		MetaStore.get('api_results').add(self.method, api_results)
		MetaStore.get('api').add(self.method, meta['API'])
		return [records, meta]
