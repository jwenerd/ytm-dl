
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

			song_mapping =  'history' in self.file or '_songs' in self.file
			if song_mapping:
				self.columns = ['title', 'artists', 'album'] + self.columns + ['duration', 'duration_seconds', 'videoId']

	def get_rows(self):
		rows = []
		for item in self.records:
			row = []
			for c in self.columns:
				value = item.get(c, '')
				if isinstance(value, dict) and 'name' in value.keys():
					value = value['name'] # for song albuem
				if c == 'artists' and isinstance(value,list):
					value = join_list_value(value)
				row.append(value)

			rows.append(row)
		return rows
