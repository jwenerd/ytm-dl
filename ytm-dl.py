import sys
from src.api import get_api_client, map_playlist_songs, map_generic
from src.file import write_files
import concurrent.futures
import threading

thread_local = threading.local()

def ytmusic():
	if not hasattr(thread_local, "ytmusic"):
			thread_local.ytmusic = get_api_client()
	return thread_local.ytmusic

def write_liked():
	print('start liked')
	liked_songs = ytmusic().get_liked_songs(limit=2500)
	rows = map_playlist_songs(liked_songs['tracks'])
	write_files('liked', rows, liked_songs)
	return 'liked'

def write_recent_songs():
	print('start recent')
	recent_songs = ytmusic().get_library_songs(limit=2500, order='recently_added')
	rows = map_playlist_songs(recent_songs)
	write_files('recent_songs', rows)
	return 'recent_songs'

def write_history():
	print('start history')
	history = ytmusic().get_history()
	rows = map_playlist_songs(history, ['inLibrary', 'likeStatus', 'played'])
	write_files('history', rows)
	return 'history'

def write_subscribed_artists():
	print('start sub artist')
	artists = ytmusic().get_library_subscriptions(limit=2500, order='recently_added')
	rows = map_generic(artists, ['artist', 'browseId'])
	write_files('subscribed_artists', rows)
	return 'subscribed_artists'

def write_library_artists():
	print('start lib artists')
	artists = ytmusic().get_library_artists(limit=2500, order='recently_added')
	rows = map_generic(artists, ['artist', 'browseId'])
	write_files('library_artists', rows)
	return 'library_artists'

def write_library_albums():
	print('start lib albums')
	albums = ytmusic().get_library_albums(limit=2500, order='recently_added')
	rows = map_generic(albums, ['artists', 'title', 'type', 'year', 'browseId'])
	write_files('library_albums', rows)
	return 'library_albums'


def main(option):
	if not option in ['all', 'frequent']:
		print('Option must be all or frequent')
		print('  given: ' + str(option))
		sys.exit(1)

	fns = [write_liked, write_recent_songs, write_history]
	if option == 'all':
		fns = fns +  [write_subscribed_artists, write_library_artists, write_library_albums]

	with concurrent.futures.ThreadPoolExecutor() as executor:
		results = list(executor.map(lambda x: x(), fns))
	print(results)

option = ''
if len(sys.argv) >= 2:
	option =sys. argv[1]

main(option)
