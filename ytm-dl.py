import sys
import time
import concurrent.futures
import threading
import yaml
import time

from src.api import get_api_client
from src.output import Output
from src.meta import write_readme

def get_records(response):
	meta = {}
	if isinstance(response, dict) and 'tracks' in response.keys():
		records = response['tracks']
		del response['tracks']
		meta['Tracks'] = response
	else:
		records = response

	return [records, meta]

def save_api_results():
	timestr = time.strftime("%Y_%m_%d_%H_%M")
	with open(f'api_results_{timestr}.yaml', 'w') as f:
		f.write(yaml.dump(save_api_results.store))

save_api_results.store = {}

thread_local = threading.local()

def ytmusic_to_file(file):
	api_method = 'get_' + file
	if not hasattr(thread_local, "ytmusic"):
			thread_local.ytmusic = get_api_client()

	api_args = {
		'get_history': {},
		'get_liked_songs': { 'limit': 2500 }
	}.get(api_method, { 'limit': 2500, 'order': 'recently_added' })

	start_time = time.time()
	api_fn = getattr(thread_local.ytmusic, api_method)
	elapsed_time = round(time.time() - start_time, 2)

	api_results = api_fn(**api_args)
	records, meta = get_records(api_results.copy())

	meta['API'] = {
		'records_length': len(records), 'method': api_method,
		'method_args': api_args, 'response_time': elapsed_time
	}

	result = Output(file, records, meta).write_files()
	if result is None:
		return

	save_api_results.store[api_method] = api_results
	return result

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
		files_written = list(executor.map(lambda file: ytmusic_to_file(file), files))

	files_written = set(filter(None, files_written))
	if len(files_written) > 0:
		write_readme()
		save_api_results()

if __name__ == "__main__":
		option = ''
		if len(sys.argv) >= 2:
			option = sys.argv[1]

		do_updates(option)
