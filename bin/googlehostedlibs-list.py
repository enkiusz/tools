#!/usr/bin/env python3

## Category: Googlefoo
## Shortdesc: List URLs of libraries hosted on https://developers.google.com/speed/libraries/devguide

import requests, string, re
from bs4 import BeautifulSoup

r = requests.get('https://developers.google.com/speed/libraries/devguide')

if r.status_code != 200:
    print("Error downloading library list page, status_code='%d'" % (r.status_code))

static_versions = {
    'angularjs': [
        '1.1.5' # Reference: http://mailinator.com/inbox.jsp?to=test
        ],
    }
soup = BeautifulSoup(r.text)
for lib_div in soup.find('h2', text='Libraries').find_next_siblings('h3'):
    lib_id = lib_div.get_text().lower()
    lib_dl = lib_div.find_next_sibling('dl')

    # print("Dumping links for lib '%s'" % (lib_id))

    versions = set()
    try:
        versions = set(static_versions[lib_id])
    except KeyError:
        pass
    for version_dd in lib_dl.find_all('dd', class_='versions'):
        for tag in version_dd.get_text().split(','):
            versions.add(tag.strip(string.whitespace))

    # Search for one of the versions in the snippet to determine paths we need to download
    refs = list()
    for snippet in lib_dl.find_all('code', class_='snippet'):
        
        for ref in re.findall(r'(?:href|src)=[\'"]([^"\']+?)[\'"]', snippet.get_text(strip=True), re.IGNORECASE):

            # Inside each reference URL look for one of the available version tags.
            # Replace this version tag with a version placeholder ('%s')
            for v in versions:
                if re.search("/%s/" % (v), ref) is not None:
                    refs.append( re.sub("/%s/" % (v), '/%s/', ref) )

    for ref in refs:
        for version in versions:
            print('%s' % ( ref % ( version ) ))
