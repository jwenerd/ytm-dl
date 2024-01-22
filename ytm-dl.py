import sys
import concurrent.futures
import resource

from src.api import ApiMethod
from src.output import Output
from src.meta import write_meta

def ytmusic_to_file(file):
	records, meta = ApiMethod(f'get_{file}').perform()
	result = Output(file, records, meta).write_files()
	if result is None:
		return
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
	output_updates = len(files_written) > 0

	ApiMethod.save_api_artifact()
	write_meta(output_updates)


if __name__ == "__main__":
		option = ''
		if len(sys.argv) >= 2:
			option = sys.argv[1]

		do_updates(option)
