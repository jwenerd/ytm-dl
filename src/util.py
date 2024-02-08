import os
import hashlib
from types import MappingProxyType
import yaml

# todo output file class

def create_directory(path):
	if not os.path.exists(path):
		os.makedirs(path)

def output_path(file=''):
	if len(file) > 0:
		file = f'/{file}'
	return f'output{file}'

def file_exists(file):
	return os.path.isfile(file)

def new_file(file):
	return not file_exists(file)

def file_hash(file):
	file = output_path(file)
	if not file_exists(file):
		return ''

	with open(file) as f:
		data = f.read()
		hash = hashlib.sha256(data.encode()).hexdigest()
	return hash

def write_file(file, content):
	create_directory(os.path.dirname(file))
	with open(file, 'w') as f:
		f.write(str(content))

def write_output_yaml(file, records):
	write_output_file(f'{file}', yaml.dump(records))

def read_output_yaml(file):
	try:
		with open(output_path(file), 'r') as f:
			data = yaml.safe_load(f)
		return data
	except OSError as e:
		return

def write_output_file(file, content):
	write_file(output_path(file), content)

def deep_merge(dict1, dict2):
	for key, value in dict2.items():
		if isinstance(value, dict) and key in dict1:
				deep_merge(dict1[key], value)
		else:
				dict1[key] = value



def make_dict_readonly(d):
	for k, v in d.items():
		if isinstance(v, dict):
			make_dict_readonly(v)
			d[k] = MappingProxyType(v)

def deep_sort_keys(d):
	if isinstance(d, dict):
		sorted_keys = sorted(d.keys())
		return {key: deep_sort_keys(d[key]) for key in sorted_keys}
	else:
		return d
