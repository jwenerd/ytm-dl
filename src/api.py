from ytmusicapi import YTMusic

def get_api_client():
	ytmusic = YTMusic("oauth.json")
	return ytmusic
