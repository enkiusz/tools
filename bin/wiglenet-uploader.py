#!/usr/bin/env python3

# wigleuploader - Upload script for wigle.net
# Copyright (C) 2016 Maciej Grela <enki@fsck.pl>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from bs4 import BeautifulSoup
import requests, sys, os, getpass, time, json, logging, asciitable


# You will see the REQUEST, including HEADERS and DATA, and RESPONSE with HEADERS but without DATA.
# The only thing missing will be the response.body which is not logged.

# *Uncomment this and set the log level in basicConfig to DEBUG in order to enable debugging of HTTP requests/responses*
# try:
#     import http.client as http_client
# except ImportError:
#     # Python 2
#     import httplib as http_client
# http_client.HTTPConnection.debuglevel = 1

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# *Uncomment this and set the log level in basicConfig to DEBUG in order to enable debugging of HTTP requests/responses*
# requests_log = logging.getLogger("requests.packages.urllib3")
# requests_log.setLevel(logging.DEBUG)
# requests_log.propagate = True

from optparse import OptionParser
from urllib.parse import urljoin

#
# Default configuration
#
base_url = 'https://wigle.net/'
login = None

#
# Parse command line options
#

parser = OptionParser()
parser.add_option('-l', '--login', dest='login', help='Use LOGIN as the login name', metavar='LOGIN')
parser.add_option('-d', '--keepass-db', dest='keepass_db_file', help='Use KEEPASS_DB Keepass database file as a source for credentials', metavar='KEEPASS_DB')
parser.add_option('--delete-imported', dest='delete_after_successful_import', action="store_true", help='Delete files that were successfuly imported', default=False)
parser.add_option('-n', '--number', dest='upload_batch_size', help='Number of files uploaded in a batch', default=10, metavar='NUMBER')

(options, args) = parser.parse_args()

login = options.login
if login is None:
    print('A wigle.net login is required')
    sys.exit(1)

keepass_db = None
if options.keepass_db_file is not None:
    try:
        from kppy.database import KPDBv1
        from kppy.groups import v1Group
        from kppy.exceptions import KPError

        keepass_password = getpass.getpass("Enter password to unlock Keepass database '%s': " % (options.keepass_db_file))
        keepass_db = KPDBv1(options.keepass_db_file, keepass_password, read_only=True)
        keepass_db.load()
        print("Loaded Keepass database with '%d' entries" % ( len(keepass_db.entries) ))

    except ImportError as err:
        print("Cannot load Keepass support, do you have the 'kppy' module installed?")

    except KPError as err:
        print("Keepass module encountered an error: ", err)
        keepass_db = None

def get_secret(login):
    password = None
    if keepass_db is not None:
        for entry in keepass_db.entries:
            logging.debug(entry)
            # Skip entries in the "Backup" group
            if entry.group.title == "Backup":
                continue

            if login == entry.username:
                password = entry.password
    else:
        password = getpass.getpass("Enter password for login '%s' used to access URL '%s': " % (login, base_url))

    return password


session = requests.Session()
login_resp = session.post(urljoin(base_url,'/api/v1/jsonLogin'), data={ 'credential_0': login , 'credential_1': get_secret(login)} )
login_state = json.loads(login_resp.text)

if not login_state['success']:
    logging.critical("Could not login to '%s' as identity '%s' with message '%s' returned by server" % (base_url, login, login_state['message']))
    sys.exit(1)


session_id = int(login_state['session'])
logging.info("Successfuly authenticated to '%s' as identity '%s', got session id '%d'" % (base_url, login, session_id) )

def popn(l,n):
    rv = []
    while n > 0 and len(l) > 0:
        rv.append(l.pop(0))
        n = n - 1
    return rv

def handle_completed_upload(summary, src_filename):
    s = summary[src_filename]

    # Return if files from source file have not completed processing
    if s['waiting'] != 0:
        return

    if s['failed'] == s['total']: # Mark as failed only if all files have failed to import
        os.rename(src_filename, src_filename + '.failed-import')
    elif options.delete_after_successful_import: # Import was successful, no failed files
        logging.info("Deleting source file '%s' with '%d' files successfuly imported ('%d' failures)" % (src_filename, s['completed'], s['failed']))
        os.unlink(src_filename)

count_success = 0
count_failure = 0

# Treat all arguments as source filenames
while len(args) > 0:

    # Process source files in batches
    src_filenames = popn(args, options.upload_batch_size)
    logging.info("Uploading a batch of '%d' source files" % (len(src_filenames)))

    src_summary = {}
    trans_waiting = {}
    for src_filename in src_filenames:

        # Track the number of completed and failed files inside a source to check when we can remove/rename the source file
        src_summary[src_filename] = {
            'waiting': 0,
            'completed': 0,
            'failed': 0,
            'total' : 0,
        }

        logging.info("Uploading source file '%s' (%d bytes)" % (src_filename, os.stat(src_filename).st_size))
        upload_resp = session.post(urljoin(base_url, '/upload'), files=[( 'stumblefile', (os.path.basename(src_filename), open(src_filename, 'rb'), 'text/plain') )], data={'observer': login} )
        soup = BeautifulSoup(upload_resp.text)

        # Check if we don't have an error
        if soup.find(class_='loginError') is not None:
            error_message = soup.find(class_='loginError').get_text(strip=True)
            logging.error("Could not upload '%s', server returned error: '%s'" % (src_filename, error_message))
            os.rename(src_filename, src_filename + '.failed-upload')
            continue

        for row in soup.find('div', class_="statsSection").find('table').find_all('tr'):
            cols = row.find_all('td')
            if len(cols) == 2:
                transid = cols[1].get_text(strip=True)
                uploaded_filename = cols[0].get_text(strip=True)

                logging.info("Filename '%s' from source '%s' has transid '%s'" % (uploaded_filename, src_filename, transid))
                trans_waiting[transid] = { 'source': src_filename, 'uploaded_filename': uploaded_filename }
                src_summary[src_filename]['waiting']+=1

        src_summary[src_filename]['total'] = src_summary[src_filename]['waiting']

    # Watch for transaction status to check if filenames 
    while len(trans_waiting) > 0:

        # Get a list of transactions
        trans_list_result = json.loads(session.get(urljoin(base_url, '/api/v1/jsonTrans'), params={ 'pagestart': 0, 'pageend': 100}).text)

        logging.debug("Current upload processing state:")
        logging.debug(trans_list_result)

        if not trans_list_result['success']:
            logging.error("Could not fetch the list of uploads, message '%s' returned by server" % (trans_list_result['message']))
            sys.exit(1)

        transids = []
        filenames = []
        statuses = []
        percentages = []
        times = []
        filesizes = []
        new_wlan_aps = []
        all_wlan_aps = []

        for trans in trans_list_result['results']:
            transid = trans['transid']

            # Check if we want to monitor this transaction
            if transid in trans_waiting:
                status = trans['status']
                filename = trans['filename']
                src_filename = trans_waiting[transid]['source']

                transids.append(transid)
                filenames.append(filename)
                statuses.append(status)
                percentages.append(trans['percentdone'])
                times.append(trans['timeparsing'])
                filesizes.append(trans['filesize'])
                new_wlan_aps.append(trans['discgps'])
                all_wlan_aps.append(trans['totalgps'])

                if status == "Completed Successfully":
                    logging.info("Processing of '%s' has been successful, %d new WiFi APs w/ GPS (%d total WiFi APs w/ GPS)" %
                                 (src_filename, trans['discgps'], trans['totalgps']))

                    src_summary[src_filename]['waiting']-=1
                    src_summary[src_filename]['completed']+=1
                    count_success = count_success + 1
                    handle_completed_upload(src_summary, src_filename)

                    del trans_waiting[transid]

                elif status == "Failed":
                    logging.error("Processing of '%s' has failed" % (filename))

                    src_summary[src_filename]['waiting']-=1
                    src_summary[src_filename]['failed']+=1
                    count_failure = count_failure + 1
                    handle_completed_upload(src_summary, src_filename)

                    del trans_waiting[transid]

        logging.info("%d transactions from current batch still pending, total %d transactions completed successfuly, total %d transactions failed" % (len(trans_waiting), count_success, count_failure))

        if log.isEnabledFor(logging.INFO):
            asciitable.write({
                'Transid': transids,
                'Task status': statuses,
                'Filename': filenames,
                'File size': filesizes,
                'Task %': percentages,
                'Task time': times,
                'New WiFi w/ GPS': new_wlan_aps,
                'WiFi in File w/ GPS': all_wlan_aps,
            }, names = ['Transid', 'Task status', 'Filename', 'File size', 'Task %', 'Task time', 'New WiFi w/ GPS', 'WiFi in File w/ GPS'], Writer=asciitable.FixedWidth)


        time.sleep(10)
