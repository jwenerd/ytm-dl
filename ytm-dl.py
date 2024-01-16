import sys
import os
import concurrent.futures
import threading
from datetime import datetime

from src.api import get_api_client
from src.file import Output

def get_records(response):
	meta = {}
	if isinstance(response, dict) and 'tracks' in response.keys():
		merge = {k: v for k, v in response.items() if isinstance(v, (str, int, float, bool))}
		meta.update(merge)
		records = response['tracks']
	else:
		records = response

	meta.update({ 'fetched': len(records), 'time':  datetime.now().isoformat() })
	return [records, meta]

thread_local = threading.local()

def ytmusic_to_file(file):
	api_method = 'get_' + file
	if not hasattr(thread_local, "ytmusic"):
			thread_local.ytmusic = get_api_client()

	api_args = {
		'get_history': {},
		'get_liked_songs': { 'limit': 2500 }
	}.get(api_method, { 'limit': 2500, 'order': 'recently_added' })

	api_fn = getattr(thread_local.ytmusic, api_method)
	records, meta = get_records(api_fn(**api_args))

	output = Output(file, records, meta)
	output.write_files()

def do_updates(option):
	if not option in ['all', 'frequent']:
		print('Option must be all or frequent')
		print('  given: ' + str(option))
		sys.exit(1)

	files = ['liked_songs', 'library_songs', 'history']
	if option == 'all':
		files = files +  ['library_subscriptions', 'library_artists', 'library_albums']

	print('starting ' + option + ' updates')
	with concurrent.futures.ThreadPoolExecutor() as executor:
		list(executor.map(lambda file: ytmusic_to_file(file), files))

if __name__ == "__main__":
		option = ''
		if len(sys.argv) >= 2:
			option = sys.argv[1]

		do_updates(option)
