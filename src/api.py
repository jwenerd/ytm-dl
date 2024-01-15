from ytmusicapi import YTMusic
ytmusic = YTMusic("oauth.json")

def get_artists_value(artists_lists):
	artists = list(map(lambda t: t['name'], artists_lists))
	artists.sort()
	return ", ".join(artists)

def map_playlist_songs(songs, otherCols = []):
	headers = ['title', 'artist', 'album'] + otherCols + ['duration', 'duration_seconds', 'link']
	rows = [headers]
	for song in songs:
		title = song['title']
		artist = get_artists_value(song['artists'])
		album = song['album']
		album = album['name'] if (album != None) else ""

		otherVals = [song.get(col, '') for col in otherCols]

		duration = song['duration']
		duration_s = str(song['duration_seconds'])
		link = 'https://music.youtube.com/watch?v=' + song['videoId']


		row =  []
		row += [title,artist,album]
		row += otherVals
		row += [duration, duration_s,link]
		rows.append(row)

	return rows

def map_generic(items, cols):
	if 'browseId' in cols:
		cols.append('link')
	rows = [cols]
	for item in items:
		row = []
		for c in cols:
			value = item.get(c, '')
			if c == 'artists' and isinstance(value,list):
				value = get_artists_value(value)
			if c == 'link':
				value = 'https://music.youtube.com/browse/' + item['browseId']
			row.append(value)

		rows.append(row)
	return rows
