
def join_list_value(values, key='name'):
	plucked = list(map(lambda t: t[key], values))
	plucked.sort()
	return ", ".join(plucked)

class Mapping:
	def __init__(self, file, records):
			self.file = file
			self.records = records
			self.cols = {
				'history': [
					'inLibrary', 'likeStatus', 'played'
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
			}.get(self.file, [])

	def get_rows(self):
		songs = 'history' in self.file or '_songs' in self.file
		if songs:
			return self.map_songs()
		else:
			return self.map_generic()

	def map_generic(self, columns=None):
		if columns is None:
			columns = self.cols
		
		rows = [columns] # header
		for item in self.records:
			row = []
			for c in columns:
				value = item.get(c, '')
				
				if isinstance(value, dict) and 'name' in value.keys():
					value = value['name'] # for song albuem
				if c == 'artists' and isinstance(value,list):
					value = join_list_value(value)
				
				row.append(value)
			
			rows.append(row)
		return rows

	def map_songs(self):
		otherCols = []
		if self.file == 'history':
			otherCols = ['inLibrary', 'likeStatus', 'played']

		columns = ['title', 'artists', 'album'] + otherCols + ['duration', 'duration_seconds', 'videoId']
		return self.map_generic(columns)
		