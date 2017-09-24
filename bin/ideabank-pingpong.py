#!/usr/bin/env python3

## Category: Internet banking
## Shortdesc: Create a PING-PONG one day deposit on your http://www.ideabank.pl/ internet banking account

# ideabank - Scripted creation of Idea Bank "Ping-pong" deposit
# Copyright (C) 2014 Maciej Grela <enki@fsck.pl>

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
import requests, re, sys, getpass, datetime, dateutil.parser

# Use money namespace from https://pypi.python.org/pypi/money/
# *NOT* from https://pypi.python.org/pypi/python-money/
from decimal import Decimal
from money import Money

from optparse import OptionParser
from urllib.parse import urljoin

#
# Default configuration
#
base_url = 'https://secure.ideabank.pl/'

#
# Parse command line options
#

parser = OptionParser()
parser.add_option('-d', '--keepass-db', dest='kdb_filename', help='Use Keepass file KDB_FILENAME as a source for credentials', metavar='KDB_FILENAME')

(options, args) = parser.parse_args()

def amount_prepare(s):
    return s.strip().translate({ord(' '): None}).replace(',', '.')

kdb = None
if options.kdb_filename is not None:
    try:
        from kppy.database import KPDBv1
        from kppy.groups import v1Group
        from kppy.exceptions import KPError

        keepass_password = getpass.getpass("Enter password to unlock Keepass database '%s': " % (options.kdb_filename))
        kdb = KPDBv1(options.kdb_filename, keepass_password, read_only=True)
        kdb.load()
        print("Loaded Keepass database with '%d' entries" % ( len(kdb.entries) ))


    except ImportError as err:
        print("Cannot load Keepass support, do you have the 'kppy' module installed?")

    except KPError as err:
        print("Keepass module encountered an error: ", err)


for login in args:

    print("Using identity '%s'" % (login))
    
    password = None
    if kdb is not None:
        for entry in kdb.entries:
            # Skip entries in the "Backup" group
            if entry.group.title == "Backup":
                continue

            if login == entry.username:
                password = entry.password

    if password is None:
        password = getpass.getpass("Enter password for login '%s' used to access URL '%s': " % (login, base_url))

    #
    # Establish session
    #

    session = requests.Session()

    # Get the CSRF token
    loginpage = session.get(base_url)
    soup = BeautifulSoup(loginpage.text)
    loginform = soup.find('form', id='form_login')
    loginpath = loginform['action']
    csrf_token = loginform.find(attrs={'name': 'banking'})['value']

    login_req = session.post(base_url, data={ 'log2': login , 'password': password, 'banking': csrf_token } )

    # print(login_req.text)
    soup = BeautifulSoup(login_req.text)
    # print("Page after login: ", login_req.text)


    #
    # Fetch the checking accounts list
    #

    accounts_req = session.get(urljoin(base_url, '/accounts/index'))
    soup = BeautifulSoup(accounts_req.text)
    # print(accounts_req.text)

    accounts = {}

    for account_table in soup.find('div', id='accounts_accounts').find_all('table', id='data'):
        # print("Account table: ", account_table)

        for row in account_table.find('tbody').find_all(lambda tag: tag.name == 'tr' and len(tag.find_all('td')) == 5):
            cols = row.find_all('td')

            account_id = cols[0].get_text(strip=True).replace(' ','')

            if account_id == '-': # This account entry is empty
                continue

            currency_code = cols[1].get_text(strip=True)
            balance = Money(amount=amount_prepare(cols[2].get_text()), currency=currency_code)
            avail_funds = Money(amount=amount_prepare(cols[3].get_text()), currency=currency_code)
            balance_pln = Money(amount=amount_prepare(cols[4].get_text()), currency='PLN')

            print("Found account '%s' with currency '%s' with balance '%s' ('%s') and available funds '%s'" % (account_id, currency_code, balance, balance_pln, avail_funds))
            accounts[account_id] = {
                'balance': balance,
                'avail_funds': avail_funds,
                'balance_pln': balance_pln,
            }


    # print("Accounts:", accounts)

    #
    # Fetch the active deposits list
    #

    active_deposits = {}

    # Fetch the deposits list
    deposits_req = session.get('https://secure.ideabank.pl/deposits/index')
    soup = BeautifulSoup(deposits_req.text)

    deposits_span = soup.find('span', text='Lista Twoich Lokat')
    if deposits_span is not None:
        for row in deposits_span.find_parent('div', class_='content').find_all('div', class_='data'):
            # print("Active deposit: ", row)

            deposit_id = re.search("'/deposits/details/(.+?)'", row.find('button', class_='szczegoly1')['onclick']).group(1)

            cols = row.find_all_next('div', class_="inner", limit=5)
            # print("Columns: ", cols)

            name = cols[0].get_text(strip=True)
            time = cols[1].get_text(strip=True)
            ends = dateutil.parser.parse(cols[2].get_text(strip=True))
            apr = cols[3].get_text(strip=True)
            amount = Money(amount=amount_prepare(cols[4].get_text()), currency='PLN')

            print("Active deposit '%s' name '%s' @ '%s' for '%s' elapses @ '%s' amount '%s'" % ( deposit_id, name, apr, time, ends, amount))

            active_deposits[str(deposit_id)] = {
                'name': name,
                'time': time,
                'ends': ends,
                'apr': apr,
                'amount': amount
                }

    if len(active_deposits.keys()) == 0:
        print("No active deposits")

    #
    # Check whether we have any available funds
    #
    for account_id, account in accounts.items():

        #
        # Fetch the list of available deposits
        #
        avail_deposits_req = session.get(urljoin(base_url, '/deposits/newDeposit'))
        soup = BeautifulSoup(avail_deposits_req.text)

        avail_deposits = {}

        for row in soup.find('div', id='actions').find('table', id='selectStructure').find_all('tr'):
            # print("Available deposit: ", row)

            deposit_button = row.find("input")
            deposit_id = re.search("'/deposits/newDeposit/(.+?)'", deposit_button['onclick']).group(1)

            deposit_img = row.find('img')
            if deposit_img is not None:
                name = deposit_img['title']
            else:
                name = row.find("td").get_text(strip=True)

            amount_min_info = row.find(text=re.compile('^Kwota min'))
            amount_min = Money(amount=re.match('Kwota min.:(\d+)', amount_min_info).group(1), currency='PLN' )

            amount_max_info = row.find(text=re.compile('^Kwota max'))
            amount_max = Money(amount=re.match('Kwota max.:(\d+)', amount_max_info).group(1), currency='PLN' )

            print("Available deposit '%s' name '%s' (min amount '%s' max amount '%s'" % (deposit_id, name, amount_min, amount_max))

            avail_deposits[name] = {
                'id': deposit_id,
                'name': name,
                'amount_min': amount_min,
                'amount_max': amount_max
            }

        # print("Account table: ", account_table)

        try:
            pingpong_deposit = avail_deposits['Lokata PING PONG']
        except KeyError:
            print("No pingpong deposit available, skipping account")
            continue

        if pingpong_deposit['amount_min'] > account['avail_funds']:
            print("Amount '%s' not enough to create a PING-PONG deposit, required at least '%s'" % ( account['avail_funds'], pingpong_deposit['amount_min'] ))
            continue

        deposit_url = urljoin(base_url, '/deposits/newDeposit/%s' % (pingpong_deposit['id']))

        deposit_create_req = session.post(deposit_url)
        # print("Deposit create html: ", deposit_create_req.text)
        soup = BeautifulSoup(deposit_create_req.text)

        # print('Inputs', soup.find_all('input'))

        deposit_data = {}
        for input in soup.find_all('input'):
            try:
                deposit_data[input['name']] = input['value']
            except KeyError:
                continue

        # Other useful params
        deposit_data['amount'] = min( account['avail_funds'], pingpong_deposit['amount_max'] ).amount
        deposit_data['nrb_out'] = account_id

        # Other crap params
        deposit_data['send'] = 'send' # No shit Sherlock
        deposit_data['ajaxSend'] = 'true' # It's ajax, riiiight?
        deposit_data['undefined'] = '' # WTF is that?

        print("Creating deposit: ", deposit_data)

        deposit_create_req = session.post(deposit_url, data=deposit_data)
        # print("Deposit create req: ", deposit_create_req.text)
        soup = BeautifulSoup(deposit_create_req.text)

        deposit_confirm_data = {}

        for input in soup.find('form', attrs={ 'name': 'btnszaloz1'}).find_all('input'):
            # print("Input: ", input)

            try:
                deposit_confirm_data[input['name']] = input['value']
            except KeyError:
                continue

        # Other crap params 
        deposit_confirm_data['ajaxSend'] = 'true'
        deposit_confirm_data['send'] = 'send'

        # CSRF token
        csrf_script = soup.find('script', text=re.compile("changeBanking\('[A-Fa-f0-9]+'\);")).get_text(strip=True)
        csrf_token = re.search("'([A-Fa-f0-9]+)'", csrf_script).group(1)

        deposit_confirm_data['banking'] = csrf_token

        print("Deposit confirm request: ", deposit_confirm_data)

        deposit_confirm_req = session.post(deposit_url, data=deposit_confirm_data)
        soup = BeautifulSoup(deposit_confirm_req.text)
        # print("Deposit confirmed: ", deposit_confirm_req.text)

        deposit_create_status = soup.find(text=re.compile('Wniosek o lokatę złożony pomyślnie.'))
        if deposit_create_status is None:
            print("Error confirming deposit creation, webpage returned: ", deposit_confirm_req.text)


    #
    # Logout
    #

    logout_req = session.get(urljoin(base_url, '/main/logout'))
    soup = BeautifulSoup(logout_req.text)
    logout_text = soup.find(text=re.compile('Zostałeś wylogowany'))
    if logout_text is not None:
        print("Logout was successful")
    else:
        print("Logout was unsuccessful, HTTP response content: ", logout_req.text)

    #
    # Unused code, just for documentation purposes
    #

    # pending_deposits = soup.find('span', text='Lista Lokat Nieopłaconych oraz w trakcie realizacji')

    # if pending_deposits is not None:

    #     for row in pending_deposits.find_parent('div', class_='content').find_all('div', class_='data'):
    #         # print("Pending deposit: ", row)

    #         cols = row.find_all_next('div', class_="inner", limit=5)
    #         # print("Columns: ", cols)
    #         deposit_name = cols[0].get_text(strip=True)
    #         time = cols[1].get_text(strip=True)
    #         ends = cols[2].get_text(strip=True)
    #         apr = cols[3].get_text(strip=True)
    #         amount = Money(amount=amount_prepare(cols[4].get_text()), currency='PLN')
    #         print("Pending deposit '%s' @ '%s'  for '%s' elapses @ '%s' requested '%s'" % ( deposit_name, apr, time, ends, amount))

try:
    kdb.close()
    del kdb
except:
    pass
