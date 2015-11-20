#!/usr/bin/env python2

#
# Taken from Google example code.
#
# Reference: https://developers.google.com/youtube/v3/code_samples/python#retrieve_my_uploads
# Reference: https://developers.google.com/api-client-library/python/start/get_started

import httplib2
import os
import sys

import codecs
sys.stdout = codecs.getwriter('utf8')(sys.stdout)

from apiclient.discovery import build
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import run_flow


# The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
# the OAuth 2.0 information for this application, including its client_id and
# client_secret. You can acquire an OAuth 2.0 client ID and client secret from
# the Google Developers Console at
# https://console.developers.google.com/.
# Please ensure that you have enabled the YouTube Data API for your project.
# For more information about using OAuth2 to access the YouTube Data API, see:
#   https://developers.google.com/youtube/v3/guides/authentication
# For more information about the client_secrets.json file format, see:
#   https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
CLIENT_SECRETS_FILE = os.getenv('CLIENT_SECRETS_FILE', os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                                                    'client-secrets.json')))

# This variable defines a message to display if the CLIENT_SECRETS_FILE is
# missing.
MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0


To make this sample run you will need to populate the client_secrets.json file
found at:

   %s

*OR* set an environment variable CLIENT_SECRETS_FILE containing the location 
of the above file.

with information from the Developers Console
https://console.developers.google.com/

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
""" % (CLIENT_SECRETS_FILE)

# This OAuth 2.0 access scope allows for read-only access to the authenticated
# user's account, but not other types of account access.
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
  message=MISSING_CLIENT_SECRETS_MESSAGE,
  scope=YOUTUBE_READONLY_SCOPE)

storage = Storage( os.path.join(os.getenv('OAUTH2_TOKEN_DIR', '.'), "%s-oauth2.json" % os.path.basename(sys.argv[0])) )
credentials = storage.get()

if credentials is None or credentials.invalid:
  credentials = run_flow(flow, storage)


youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
  http=credentials.authorize(httplib2.Http()))

playlists_response = youtube.playlists().list(
  mine=True,
  maxResults=50,
  part="id,snippet",
).execute()

for playlist_item in playlists_response['items']:
  if playlist_item['kind'] != 'youtube#playlist': 
    continue
  print("%s %s" % (playlist_item['id'], playlist_item['snippet']['title']))
