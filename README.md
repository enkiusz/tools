# tools

Here is a bunch of scripts that I use more or less often:

## Daily/maintenance:

* bin/daily - A Gentoo maintenance script run daily on my machine
* bin/dwmstatus - The status command I used when I had dwm

## Various
* bin/envunpack - Unpacks /proc/${PID}/environ files. Try 'cat /proc/self/environ | envunpack'
* bin/hdd-surv - A HDD survey script for internet auctions
* bin/unwrap - Recursively unpack containers. That is, if there are other container files inside they will also be unpacked.
* bin/debian-snowflake - Find all the files that were potentially edited by you when you were customizing that Xubuntu distribution. Attempts to remove most of the false positives.
* bin/clone-user-repos - Clone all repositories of a particular user from github.com

## Googlefoo
* bin/googlehostedlibs-fetch.sh - Make a local mirror of all the libraries hosted on https://developers.google.com/speed/libraries/devguide for improved privacy
* bin/googlehostedlibs-list.py - list URLs of libraries hosted on https://developers.google.com/speed/libraries/devguide

* bin/youtube-get-playlists.py - Get a list of playlists for a particular Youtube account
* bin/youtube-playlist-sync - Make a local mirror of all playlists for a particular Youtube account. Personal YT backup solution.

## Internet banking

* bin/ideabank.py - Fetch the account balances from your http://www.ideabank.pl/ internet banking account
* bin/ideabank-pingpong.py - Create a PING-PONG one day deposit on your http://www.ideabank.pl/ internet banking account
* bin/banksmart.rb - Fetch the account balances from your http://www.banksmart.pl/ internet banking account

## Making the Internet of Things work for you
* bin/epc3008-status.py - Scrape and print the status of a Cisco EPC3008 cable modem
* bin/printerstasi.rb - Summarize info about jobs printed on a RICOH Aficio MP 6001 printer, may work for other Ricoh printers. Uses a reverse-engineered Ricoh MIB (share/mibs/vendor/RICOH-MIB.txt)

