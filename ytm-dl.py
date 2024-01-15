import sys
from src.api import get_api_client
from src.file import write_files
from src.mapping import Mapping
import concurrent.futures
import threading

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
	response = api_fn(**api_args)

	meta = {}
	if isinstance(response, dict) and 'tracks' in response.keys():
		meta = {}
		for k in list(response.keys()):
			v = response[k]
			if (not isinstance(v,list) and not isinstance(v,dict)):
				meta[k]=v

		records = response['tracks']
	else:
		records = response
		

	rows = Mapping(file, records).get_rows()
	write_files(file, rows, meta)

def do_updates(option):
	if not option in ['all', 'frequent']:
		print('Option must be all or frequent')
		print('  given: ' + str(option))
		sys.exit(1)

	files = ['liked_songs', 'library_songs', 'history']
	if option == 'all':
		files = files +  ['library_subscriptions', 'library_artists', 'library_albums']

	with concurrent.futures.ThreadPoolExecutor() as executor:
		list(executor.map(lambda file: ytmusic_to_file(file), files))

if __name__ == "__main__":
		option = ''
		if len(sys.argv) >= 2:
			option = sys.argv[1]

		do_updates(option)