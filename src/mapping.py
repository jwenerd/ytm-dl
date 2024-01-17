
def join_list_value(values, key='name'):
	plucked = list(map(lambda t: t[key], values))
	plucked.sort()
	return ", ".join(plucked)

class Mapping:
	FILE_COLUMNS = {
		'history': [
			'inLibrary', 'likeStatus'
		],
		'library_subscriptions': [
			'artist', 'browseId'
		],
		'library_artists': [
			'artist', 'browseId'
		],
		'library_albums': [
			'artists', 'title', 'type', 'year', 'browseId'
		]
	}

	def __init__(self, file, records):
			self.file = file
			self.records = records
			self.columns = Mapping.FILE_COLUMNS.get(self.file, [])

			song_records =  'history' in self.file or '_songs' in self.file
			if song_records:
				self.columns = ['title', 'artists', 'album'] + self.columns + ['duration', 'duration_seconds', 'videoId']

	def get_rows(self):
		return [ fullrow(record, self.columns) for record in self.records ]

def fullrow(record,columns):
	return [ colval(record, col) for col in columns ]

def colval(record, col):
	value = record.get(col, '')
	if isinstance(value, dict) and 'name' in value.keys():
		value = value['name'] # for song albuem
	if col == 'artists' and isinstance(value,list):
		value = join_list_value(value)
	if isinstance(value, str):
		value = value.strip()
	return value
