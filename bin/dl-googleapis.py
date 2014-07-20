#!/usr/bin/env python3

import requests, string, os, re
from bs4 import BeautifulSoup

local_root = "/home/enki/mirror/googleapis/ajax/libs"
remote_root = '//ajax.googleapis.com/ajax/libs'

# Load library list
r = requests.get('https://developers.google.com/speed/libraries/devguide')

if r.status_code != 200:
    print("Error downloading library list, status_code='%d'" % (r.status_code))

soup = BeautifulSoup(r.text)

# print(soup)

for lib_div in soup.find('h1', id='Libraries').find_next_siblings('div'):
    lib_id = lib_div['id']

    versions = list()
    for version_span in lib_div.find_all('span', class_='versions'):
        versions.extend( [ tag.strip(string.whitespace) for tag in version_span.get_text().split(',') ] )

    # Search for one of the versions in the snippet to determine paths we need to download
    refs = list()
    for snippet in lib_div.find_all('code', class_='snippet'):
        
        # Add the refs found to the list of refs for this library while removing the common remote root prefix
        # And converting them to string templates to replace version
        
        for ref in re.findall(r'(?:href|src)=[\'"]([^"\']+?)[\'"]', snippet.get_text(strip=True), re.IGNORECASE):
            ref = re.sub("^%s/" % (remote_root), '', ref);
            sp = ref.split('/', 2); ref = '/'.join([sp[0], '%s', sp[2]])

            refs.append(ref)

    for ref in refs:
        for version in versions:
            # print("Downloading library '%s' ref '%s' version tag '%s'" % ( lib_id, ref, version ))

            src_uri = 'https:%s/%s' % ( remote_root, ref % ( version ) )
            dest_file = '%s/%s' % ( local_root, ref % ( version ) )

            # Get the directory part of the file
            dest_dir = '/'.join( dest_file.split('/')[:-1] )

            try:
                os.makedirs(dest_dir)
            except FileExistsError:
                pass

            # Download the file
            r = requests.get(src_uri)
            print("Downloading '%s' -> '%s'" % (src_uri, dest_file))
            with open(dest_file, 'wb') as fd:
                for chunk in r.iter_content(64*1024):
                    fd.write(chunk)
                fd.close()

            
