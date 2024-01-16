import os
import hashlib

def file_hash(file):
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

  with open(file, 'w') as f:
    f.write(output)
