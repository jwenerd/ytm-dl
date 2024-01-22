import csv
import os.path
import shutil
import yaml
from .mapping import Mapping
from .prepend import prepend_rows_for_file
from .util import file_hash, output_path, write_output_file
from .meta import MetaOutput

def write_output_yaml(file, records):
	write_output_file(f'{file}.yaml', yaml.dump(records))

# todo: rename this output
class Output:
	readme_written = False

	def __init__(self, file, records, meta = {}):
		self.file = file
		self.csv_file = self.file + '.csv'
		self.csv_file_with_path = output_path(self.csv_file)

		self.prepend = file in ['history', 'liked_songs', 'library_songs', 'library_subscriptions']
		self.by_key = file in ['library_subscriptions']

		self.mapping = Mapping(file, records)
		self.hash_before = file_hash(self.csv_file)
		self.meta = MetaOutput(file, meta)
		self.rows = []

	def write_csv(self):
		with open(self.csv_file_with_path, 'w', newline='') as csvfile:
			writer = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
			writer.writerows([self.mapping.columns] + self.rows)

	def prepend_to_csv(self):
		# first copy the existing csv
		prev_file = f'{self.csv_file_with_path}.old'
		shutil.move(self.csv_file_with_path, prev_file)

		# write a csv the newly added values
		self.write_csv()

		# move all the values from the previous file to the new file; open in append
		# mode so starts at the end of the file
		with open(prev_file, 'r') as old_file, open(self.csv_file_with_path , 'a+') as new_file:
			for index, line in enumerate(old_file):
				if index == 0: continue
				new_file.write(line)

		# lastly - delete the old data
		os.unlink(prev_file)

	def write_files(self):
		self.rows = self.mapping.get_rows()

		if self.prepend or self.by_key:
			self.rows = prepend_rows_for_file(self.csv_file_with_path, self.rows, self.by_key)
			self.meta.add_meta('CSV File', { 'lines_added': len(self.rows) })
			# todo: if doing other files need to pass different look aahead
			# todo: need some thing here for if starting brand new file
			if len(self.rows) > 0:
				self.prepend_to_csv()
		else:
			self.write_csv()

		if self.hash_before == file_hash(self.csv_file):
			return	print('no updates to ' + self.file)

		self.meta.write_files()
		length_rows = str(len(self.rows))

		log = f'added {length_rows} to {self.file}' if self.prepend else f'created {self.file} with {length_rows} rows'
		print(log)

		return self.file
