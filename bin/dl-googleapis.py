#!/usr/bin/env python3

import requests, string, re
from bs4 import BeautifulSoup

r = requests.get('https://developers.google.com/speed/libraries/devguide')

if r.status_code != 200:
    print("Error downloading library list page, status_code='%d'" % (r.status_code))

soup = BeautifulSoup(r.text)
for lib_div in soup.find('h1', id='Libraries').find_next_siblings('div'):
    lib_id = lib_div['id']

    versions = list()
    for version_span in lib_div.find_all('span', class_='versions'):
        versions.extend( [ tag.strip(string.whitespace) for tag in version_span.get_text().split(',') ] )

    # Search for one of the versions in the snippet to determine paths we need to download
    refs = list()
    for snippet in lib_div.find_all('code', class_='snippet'):
        
        for ref in re.findall(r'(?:href|src)=[\'"]([^"\']+?)[\'"]', snippet.get_text(strip=True), re.IGNORECASE):

            # Inside each reference URL look for one of the available version tags.
            # Replace this version tag with a version placeholder ('%s')
            for v in versions:
                if re.search("/%s/" % (v), ref) is not None:
                    refs.append( re.sub("/%s/" % (v), '/%s/', ref) )

    for ref in refs:
        for version in versions:
            print('https:%s' % ( ref % ( version ) ))
