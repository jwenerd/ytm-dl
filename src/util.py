import os
import hashlib

def output_path(file=''):
	if len(file) > 0:
		file = f'/{file}'
	return f'output{file}'

def file_hash(file):
	file = output_path(file)
	if not os.path.isfile(file):
		return ''

	with open(file) as f:
		data = f.read()
		hash = hashlib.sha256(data.encode()).hexdigest()
	return hash

def write_file(file, content):
	with open(output_path(file), 'w') as f:
		f.write(str(content))

def deep_merge(dict1, dict2):
	for key, value in dict2.items():
		if isinstance(value, dict) and key in dict1:
				deep_merge(dict1[key], value)
		else:
				dict1[key] = value

def deep_sort_keys(d):
	if isinstance(d, dict):
		sorted_keys = sorted(d.keys())
		return {key: deep_sort_keys(d[key]) for key in sorted_keys}
	else:
		return d
