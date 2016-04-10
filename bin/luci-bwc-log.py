#!/usr/bin/env python2.7

# luci-bwc-log - Store the output of OpenWRS's luci-bwc network iface traffic stats into sqlite
# Copyright (C) 2015 Maciej Grela <enki@fsck.pl>

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

import sqlite3, sys, argparse, os, re

# Default config
database_filename = '/opt/netmonitor/bw.sqlite'

parser = argparse.ArgumentParser()
parser.add_argument("router", help="Specify the router name")
parser.add_argument("iface", help="Specify the interface name")
args = parser.parse_args(os.environ['SSH_ORIGINAL_COMMAND'].split()[1:]) # Get the original commandline from the ssh client

print("Inserting data for router '%s' interface '%s' into database file '%s'" % (args.router, args.iface, database_filename))

try:
    con = sqlite3.connect(database_filename)

    # Create schema if not yet present
    con.executescript("""
create table if not exists routers (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
create table if not exists interfaces (id INTEGER PRIMARY KEY, router_id INTEGER, name TEXT,
    UNIQUE (router_id, name), FOREIGN KEY(router_id) REFERENCES routers(id));
create table if not exists interface_counters(iface_id INTEGER NOT NULL,
    timestamp INTEGER NOT NULL, rxb INTEGER, rxp INTEGER, txb INTEGER, txp INTEGER,
    UNIQUE (iface_id,timestamp), FOREIGN KEY(iface_id) REFERENCES interfaces(id));
""")
    con.commit()

    # Insert entries for specified router and interface
    con.execute('insert or ignore into routers (name) values (?)', (args.router,))
    con.execute('insert or ignore into interfaces (router_id, name) values ((select id from routers where routers.name = ?), ?)', (args.router, args.iface))
    con.commit()

    linerex = re.compile('^\[\s*(?P<time>\d+),\s*(?P<rxb>\d+),\s*(?P<rxp>\d+),\s*(?P<txb>\d+),\s*(?P<txp>\d+)\s*\]')
    rows = tuple( ( (args.router, args.iface) + linerex.match(line).groups() ) for line in sys.stdin )

    con.executemany('insert or ignore into interface_counters(iface_id, timestamp, rxb, rxp, txb, txp) values((select interfaces.id from interfaces left join routers on interfaces.router_id = routers.id where routers.name = ? and interfaces.name = ?), ?, ?, ?, ?, ?)', rows)
    con.commit()

except sqlite3.Error, e:

    print ("Sqlite error '%s'" % (e.args[0]))
    sys.exit(1)

finally:

    if con:
        con.close()
