import csv
from datetime import datetime
import os.path
import hashlib

def file_hash(file):
	hash = ''
	if not os.path.isfile(file):
		return ''
	with open(file) as f:
		data = f.read()
		hash = hashlib.sha256(data.encode()).hexdigest()
	return hash

def write_files(name, rows, meta = {}):
	csv_file = 'output/' + name + '.csv'
	hash_before = file_hash(csv_file)

	with open(csv_file, 'w', newline='') as csvfile:
		writer = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
		writer.writerows(rows)

	hash_after = file_hash(csv_file)
	if hash_before == hash_after:
		print('no updates to ' + name)
		return

	with open('output/.' + name + '_meta', 'w', newline='') as metafile:
		metafile.writelines("fetched=" + str(len(rows) - 1) + "\n")
		metafile.writelines("file_created=" + datetime.now().isoformat() + "\n")
		for key in list(meta.keys()):
			value = meta.get(key,'')
			if isinstance(value,list) or isinstance(value,dict):
				continue 
			metafile.writelines(key + "=" + str(value) + "\n")

	print('wrote ' + name + ' with ' + str(len(rows) - 1) + ' rows')