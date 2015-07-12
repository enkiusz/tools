#!/usr/bin/env python3

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

from decimal import Decimal
from money import Money
Money.set_default_currency('PLN')

from optparse import OptionParser
from urllib.parse import urljoin

#
# Default configuration
#
base_url = 'https://secure.ideabank.pl/'
login = None

#
# Parse command line options
#

parser = OptionParser()
parser.add_option('-l', '--login', dest='login', action="append", help='Use LOGIN as the login name', metavar='LOGIN')
parser.add_option('-d', '--keepass-db', dest='keepass_db_file', help='Use KEEPASS_DB Keepass database file as a source for credentials', metavar='KEEPASS_DB')

(options, args) = parser.parse_args()
login = options.login

if len(login) == 0:
    print('At least one login is required')
    sys.exit(1)

def amount_prepare(s):
    return s.strip().translate({ord(' '): None}).replace(',', '.')

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
            # Skip entries in the "Backup" group
            if entry.group.title == "Backup":
                continue

            if login == entry.username:
                password = entry.password
    else:
        password = getpass.getpass("Enter password for login '%s' used to access URL '%s': " % (login, base_url))
        
    return password

for login in options.login:

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

    login_req = session.post(base_url, data={ 'log2': login , 'password': get_secret(login), 'banking': csrf_token } )

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
            balance = Money.Money(amount=amount_prepare(cols[2].get_text()), currency=currency_code)
            avail_funds = Money.Money(amount=amount_prepare(cols[3].get_text()), currency=currency_code)
            balance_pln = Money.Money(amount=amount_prepare(cols[4].get_text()), currency='PLN')

            print("Found account '%s' with currency '%s' with balance '%s' ('%s') and available funds '%s'" % (account_id, currency_code, balance, balance_pln, avail_funds))
            accounts[account_id] = {
                'balance': balance,
                'avail_funds': avail_funds,
                'balance_pln': balance_pln,
            }


    print("Accounts:", accounts)

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
            amount = Money.Money(amount=amount_prepare(cols[4].get_text()), currency='PLN')

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
    else:
        print(active_deposits)
    
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


keepass_db.close()
del keepass_db

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
#         amount = Money.Money(amount=amount_prepare(cols[4].get_text()), currency='PLN')
#         print("Pending deposit '%s' @ '%s'  for '%s' elapses @ '%s' requested '%s'" % ( deposit_name, apr, time, ends, amount))

