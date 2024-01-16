import csv
import os.path
import subprocess
import shutil
from .mapping import Mapping
from datetime import datetime
from .append import filter_based_on_existing
from .util import file_hash, write_file, output_path, is_github, github_meta




class Output:
	readme_written = False

	def __init__(self, file, records, extra_meta = {}):
		self.file = file
		self.is_history = file == 'history'
		self.mapping = Mapping(file, records)
		self.fetched_len = len(records)
		self.csv_file = self.file + '.csv'
		self.csv_file_with_path = output_path(self.csv_file)
		self.hash_before = file_hash(self.csv_file)
		self.extra_meta = extra_meta


	def get_meta(self):
		meta = { 'fetched_length': self.fetched_len, 'fetch_time':  datetime.now().isoformat() }
		meta.update(github_meta())
		meta.update(self.extra_meta)

		file_meta_cmd = f"(wc -l {self.csv_file_with_path} && du -h {self.csv_file_with_path}) | xargs -n2 | cut -d ' ' -f 1"
		file_lines, file_size = subprocess.check_output([file_meta_cmd], shell=True).decode().split()
		meta.update({ 'file_lines': file_lines, 'file_size': file_size })
		return meta

	def write_csv(self):
		with open(self.csv_file_with_path, 'w', newline='') as csvfile:
			writer = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
			writer.writerows([self.mapping.columns] + self.rows)

	def append_to_new(self):
		prev_file = f'{self.csv_file_with_path}.old'
		with open(prev_file, 'r') as old_file, open(self.csv_file_with_path , 'a+') as new_file:
			for index, line in enumerate(old_file):
					if index > 0: # skip header
						new_file.write(line)
		os.unlink(prev_file)

	def write_history_file(self):
		filtered_rows = filter_based_on_existing(self.csv_file_with_path, self.rows)

		if filtered_rows is None or len(filtered_rows) == 0:
			print('no updates to history')
			return

		shutil.move(self.csv_file_with_path, f'{self.csv_file_with_path}.old')

		self.rows = filtered_rows
		self.write_csv()
		self.append_to_new()
		self._log_write()


	def write_files(self):
		self.rows = self.mapping.get_rows()
		if self.is_history:
			self.write_history_file()
		else:
			self.write_csv()

		if self.hash_before == file_hash(self.csv_file):
			if not self.is_history:
				print('no updates to ' + self.file)
			return

		self._write_meta()
		if not self.is_history:
			self._log_write()

	def _write_meta(self):
		self.meta = self.get_meta()
		write_file(f'meta/{self.file}', self.get_meta())
		self._write_readme()

	def _write_readme(self):
		if Output.readme_written:  # only doe this once per run
			return
		content = 'manual runs 🙃'
		if is_github():
			action_href = f"https://github.com/{self.meta['github_repository']}/actions/runs/{self.meta['github_run_id']}"
			content = '## ⚙️ [Action](' + action_href + ')'

		write_file('README.md', content)
		Output.readme_written = True

	def _log_write(self):
		print('wrote ' + self.file + ' with ' + str(len(self.rows)) + ' rows')
