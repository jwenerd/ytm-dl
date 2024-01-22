import glob
import os
import subprocess
import yaml
from .util import output_path, write_file, write_output_file, deep_merge, deep_sort_keys, make_dict_readonly
from .markdown import md_expand, md_lines, md_table

GITHUB_META_KEYS = ['event_name', 'event_schedule', 'job', 'ref_name', 'run_attempt', 'repository', 'run_id', 'run_number', 'sha', 'workflow']
GITHUB_META_KEYS = tuple(['github_' + v for v in GITHUB_META_KEYS])
GITHUB_META = {k.lower().replace('github_',''): v for k, v in os.environ.items() if k.lower() in GITHUB_META_KEYS}
make_dict_readonly(GITHUB_META)
IS_GITHUB = len(GITHUB_META) > 0

class MetaOutput:
	def __init__(self, file, existing_meta = {}):
		self.file = file
		self.file_path = output_path(f'{file}.csv')
		self.meta_dict = self.get_default_meta(existing_meta)

	def get_default_meta(self, existing_meta):
		meta = {}
		deep_merge(meta, existing_meta)
		return meta

	def add_meta(self, label_key, value):
		deep_merge(self.meta_dict, { label_key: value } )

	def clean_up_meta(self):
		self.meta_dict = { k: v for k, v in self.meta_dict.items() if len(v) > 0 }
		self.meta_dict = deep_sort_keys(self.meta_dict)

	def update_file_meta(self):
		self.add_meta('CSV File', file_sizes(self.file_path))

	def write_files(self):
		self.update_file_meta()
		self.clean_up_meta()
		write_output_file(f'meta/{self.file}', yaml.dump(self.meta_dict))

def file_sizes(file):
	cmds = ' && '.join([f'wc -l {file}',
									f'du -h {file}',
									f'wc -c {file}'])
	file_meta_cmd = f"({cmds}) | xargs -n2 | cut -d ' ' -f 1"
	lines, size, size_bytes = subprocess.check_output([file_meta_cmd], shell=True).decode().split()

	return { 'lines': int(lines), 'size': size, 'bytes': int(size_bytes) }

OUTPUT_PATH = output_path()

def file_list():
	csv_files = glob.glob(f'{OUTPUT_PATH}/**/*.csv', recursive = True)
	return [ { 'file': f, **(file_sizes(f))  } for f in csv_files ]

def write_readme():
	rm = ['# 📝  output ']
	if IS_GITHUB:
		href = f"https://github.com/{GITHUB_META['repository']}/actions/runs/{GITHUB_META['run_id']}"
		rm += [f'## ⚙️ [{GITHUB_META["job"]} #{GITHUB_META["run_number"]}]({href})']

	# file table
	to_link = lambda file: f'[{quote(file)} ]({file})'
	fmt_file = lambda file: to_link(file.replace(f'{dir}/', ''))
	quote = lambda v: f'`{str(v)}`'

	data = [{k: fmt_file(v) if k == 'file' else v for k, v in d.items()} for d in file_list()]
	data = [{'' if k == 'file' else k: v for k, v in d.items()} for d in data]

	rm += [
		md_expand('### 📁 Files',
		md_table(data)),
	]
	write_output_file('README.md', md_lines(rm))

def write_api_meta():
	data = list(MetaStore.get('api').data.values())
	md = md_lines('### 🤖 API Info', md_table(data))
	write_file('tmp/step_output/api_info.md', md)

def write_meta(updated = False):
	if updated:
		write_readme()

	if updated and IS_GITHUB:
		url = f"https://github.com/{GITHUB_META['repository']}/commit/__OUTPUTCOMMIT__?diff=unified&w=1"
		write_file('tmp/commit_link.md', f"### ± [Output Commit]({url})" + "\n\n")

	write_api_meta()

class MetaStore:
	instances = {}

	@staticmethod
	def get(name):
		if MetaStore.instances.get(name,None) is None:
			MetaStore.instances[name] = MetaStore(name)
		return MetaStore.instances[name]

	def __init__(self, name):
		self.name = name
		self.data = {}

	def add(self, key, value):
		self.data[key] = value
