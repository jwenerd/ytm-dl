import os
import hashlib
from functools import lru_cache


OUTPUT_DIR = 'output'

def output_path(file):
	return f'{OUTPUT_DIR}/{file}'

def file_hash(file):
	file = output_path(file)
	if not os.path.isfile(file):
		return ''

	with open(file) as f:
		data = f.read()
		hash = hashlib.sha256(data.encode()).hexdigest()
	return hash

def write_file(file, content):
	output = content

	if isinstance(content, dict):
		keys = list(content)
		keys.sort()
		output = ""
		for key in keys:
			output += key + "=" + str(content.get(key,'')) + "\n"

	print('write')
	print(output_path(file))
	print(file)
	with open(output_path(file), 'w') as f:
		f.write(output)

GITHUB_META_KEYS = ['actor', 'event_name', 'job', 'ref_name', 'run_attempt', 'repository', 'run_id', 'run_number', 'sha', 'workflow']
GITHUB_META_KEYS = tuple(['github_' + v for v in GITHUB_META_KEYS])

def github_meta():
	return {k.lower(): v for k, v in os.environ.items() if k.lower() in GITHUB_META_KEYS}

def is_github():
	return 'GITHUB_REPOSITORY' in os.environ
