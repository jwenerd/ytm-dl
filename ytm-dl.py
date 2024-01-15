from sys import argv
from src.api import ytmusic, map_playlist_songs, map_generic
from src.file import write_files

def write_liked():
	liked_songs = ytmusic.get_liked_songs(limit=2500)
	rows = map_playlist_songs(liked_songs['tracks'])
	write_files('liked', rows, liked_songs)

def write_recent_songs():
	recent_songs = ytmusic.get_library_songs(limit=2500, order='recently_added')
	rows = map_playlist_songs(recent_songs)
	write_files('recent_songs', rows)

def write_history():
	history = ytmusic.get_history()
	rows = map_playlist_songs(history, ['inLibrary', 'likeStatus', 'played'])
	write_files('history', rows)

def write_subscribed_artists():
	artists = ytmusic.get_library_subscriptions(limit=2500, order='recently_added')
	rows = map_generic(artists, ['artist', 'subscribers', 'browseId'])
	write_files('subscribed_artists', rows)

def write_library_artists():
	artists = ytmusic.get_library_artists(limit=2500, order='recently_added')
	rows = map_generic(artists, ['artist', 'subscribers', 'browseId'])
	write_files('library_artists', rows)

def write_library_albums():
	albums = ytmusic.get_library_albums(limit=2500, order='recently_added')
	rows = map_generic(albums, ['artists', 'title', 'type', 'year', 'browseId'])
	write_files('library_albums', rows)


def main(option):
	if option in ['all', 'frequent']:
		write_liked()
		write_recent_songs()
		write_history()
	if option in ['all']:
		write_subscribed_artists()
		write_library_artists()
		write_library_albums()
	if not option in ['all', 'frequent']:
		print('Option must be all or frequent')
		print('  given: ' + str(option))

option = ''
if len(argv) >= 2:
	option = argv[1]

main(option)
