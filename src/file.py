import csv
import os.path
import shutil
from .mapping import Mapping
from datetime import datetime
from .append import filter_based_on_existing
from .util import file_hash, write_file

GITHUB_META_KEYS = ['actor', 'event_name', 'job', 'ref_name', 'run_attempt', 'repository', 'run_id', 'run_number', 'sha', 'workflow']
GITHUB_META_KEYS = tuple(['github_' + v for v in GITHUB_META_KEYS])

class Output:
	readme_written = False

	def __init__(self, file, records, extra_meta = {}):
		self.file = file
		self.mapping = Mapping(file, records)
		self.fetched_len = len(records)
		self.meta = self.get_meta(extra_meta)
		self.csv_file = 'output/' + self.file + '.csv'

	def get_meta(self, extra_meta = {}):
		meta = { 'fetched': self.fetched_len, 'time':  datetime.now().isoformat() }
		gh_meta = {k: v for k, v in os.environ.items() if k.lower() in GITHUB_META_KEYS}
		meta.update(gh_meta)
		meta.update(extra_meta)
		return meta

	def write_csv(self):
		with open('output/' + self.file + '.csv', 'w', newline='') as csvfile:
			writer = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
			writer.writerows([self.mapping.columns] + self.rows)

	def append_to_new(self):
		with open(self.csv_file + '.old', 'r') as old_file, open(self.csv_file , 'a') as wr:
			for index, line in enumerate(old_file):
					if index > 0: # skip header
						wr.write(line)
		os.unlink(self.csv_file + '.old')

	def write_history_file(self):
		filtered_rows = filter_based_on_existing(self.csv_file, self.rows)

		if filtered_rows is None or len(filtered_rows) == 0:
			print('no updates to history')
			return

		shutil.move(self.csv_file, self.csv_file + '.old')

		self.rows = filtered_rows
		self.write_csv()
		self.append_to_new()
		self._log_write()

	def write_files(self):
		history = self.file == 'history'

		csv_file = 'output/' + self.file + '.csv'
		hash_before = file_hash(csv_file)

		self.rows = self.mapping.get_rows()
		if history:
			self.write_history_file()
		else:
			self.write_csv()

		if hash_before == file_hash(csv_file):
			if not history:
				print('no updates to ' + self.file)
			return

		self._write_meta()
		if not history:
			self._log_write()

	def _write_meta(self):
		write_file('output/meta/' + self.file, self.meta)
		self._write_readme()

	def _write_readme(self):
		if Output.readme_written:  # only doe this once per run
			return
		content = 'manual runs 🙃'
		if 'GITHUB_RUN_ID' in self.meta:
			action_link = "https://github.com/" + self.meta['GITHUB_REPOSITORY'] + '/actions/runs/' + self.meta['GITHUB_RUN_ID']
			content = '## ⚙️ [Action](' + action_link + ')'

		write_file('output/README.md', content)
		Output.readme_written = True

	def _log_write(self):
		print('wrote ' + self.file + ' with ' + str(len(self.rows)) + ' rows')
