import sys
import concurrent.futures
import resource
import string
import yaml

from src.api import ApiMethod, suggest_search
from src.output import Output, write_output_yaml
from src.meta import write_meta
from src.util import write_output_file


def ytmusic_to_file(file):
	records, meta = ApiMethod(f'get_{file}').perform()
	result = Output(file, records, meta).write_files()
	if result is None:
		return
	return result

def write_search_suggest():
	with concurrent.futures.ThreadPoolExecutor() as executor:
		search_results = list(executor.map(lambda l: suggest_search(l), list(string.ascii_lowercase)))
	write_output_yaml('search/suggest_by_letter', {row[0]: row[1] for row in search_results})
	print('created suggest_by_letter')
	return 'search/suggest_by_letter'

def do_updates(option):
	if not option in ['all', 'frequent']:
		print('Option must be all or frequent')
		print('  given: ' + str(option))
		sys.exit(1)

	files = ['liked_songs', 'library_songs', 'history']
	if option == 'all':
		files = files +  ['library_subscriptions', 'library_artists', 'library_albums']

	files_written = []
	with concurrent.futures.ThreadPoolExecutor() as executor:
		files_written += list(executor.map(lambda file: ytmusic_to_file(file), files))

	if option == 'all':
		files_written += write_search_suggest()

	files_written = set(filter(None, files_written))
	output_updates = len(files_written) > 0

	ApiMethod.save_api_artifact()
	write_meta(output_updates)


if __name__ == "__main__":
		option = ''
		if len(sys.argv) >= 2:
			option = sys.argv[1]

		do_updates(option)
