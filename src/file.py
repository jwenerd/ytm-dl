import csv
import os.path
import hashlib
from .mapping import Mapping
from datetime import datetime

GITHUB_META_KEYS = ['actor', 'event_name', 'job', 'ref_name', 'run_attempt', 'repository', 'run_id', 'run_number', 'sha', 'workflow']
GITHUB_META_KEYS = tuple(['github_' + v for v in GITHUB_META_KEYS])

def file_hash(file):
	hash = ''
	if not os.path.isfile(file):
		return ''
	with open(file) as f:
		data = f.read()
		hash = hashlib.sha256(data.encode()).hexdigest()
	return hash

class Output:
	readme_written = False

	def __init__(self, file, records, extra_meta = {}):
		self.file = file
		self.mapping = Mapping(file, records)
		self.len = len(records)
		self.meta = self.get_meta(extra_meta)

	def get_meta(self, extra_meta = {}):
		meta = { 'fetched': self.len, 'time':  datetime.now().isoformat() }
		gh_meta = {k: v for k, v in os.environ.items() if k.lower() in GITHUB_META_KEYS}
		meta.update(gh_meta)
		meta.update(extra_meta)
		return meta

	def write_files(self):
		csv_file = 'output/' + self.file + '.csv'

		hash_before = file_hash(csv_file)
		with open(csv_file, 'w', newline='') as csvfile:
			writer = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
			rows = [self.mapping.columns] + self.mapping.get_rows()
			writer.writerows(rows)

		if hash_before == file_hash(csv_file):
			print('no updates to ' + self.file)
			return

		self._write_meta()
		print('wrote ' + self.file + ' with ' + str(self.len) + ' rows')

	def _write_meta(self):
		with open('output/.' + self.file + '_meta', 'w', newline='') as metafile:
			keys = list(self.meta.keys())
			keys.sort()
			for key in keys:
				value = self.meta.get(key,'')
				metafile.writelines(key + "=" + str(value) + "\n")

		self._write_readme()

	def _write_readme(self):
		if Output.readme_written:
			# only doe this once per run
			return

		with open('output/README.md', 'w') as file:
			print('writing readme')
			content = None
			if 'GITHUB_RUN_ID' in self.meta:
				action_link = "https://github.com/" + self.meta['GITHUB_REPOSITORY'] + '/actions/runs/' + self.meta['GITHUB_RUN_ID']
				content = '## ⚙️ [Action](' + action_link + ')'
			if content is None:
				content = 'manual'
			file.write(content)
			Output.readme_written = True
