#!/usr/bin/env python3

## Category: Making the Internet of Things work for you
## Shortdesc: Scrape and print the status of a Cisco EPC3008 cable modem

import requests, re, sys, argparse
from bs4 import BeautifulSoup

from urllib.parse import urljoin

parser = argparse.ArgumentParser(description="Cisco EPC3008 status checkur")
parser.add_argument('--base_url', default='http://192.168.100.1', help="Override the default modem status base URL")
args = parser.parse_args(sys.argv[1:])

status_page = requests.get(urljoin(args.base_url,'Docsis_system.asp'));
soup = BeautifulSoup(status_page.content)

epc3008_tokens = {
    r'dw\(vs_channel\);': 'CH',
    r'dw\(vcolon\);': '', # Remove colon from channel IDs
    r'dw\(vdbmv\);': 'dBmV',
    r'dw\(vdb\);': 'dB',
    r'dw\(vmodel\);': 'model',
    r'dw\(vvendor\);': 'vendor',
    r'dw\(vhwrev\);': 'hwrev',
    r'dw\(vmac1\);': 'mac',
    r'dw\(vbootloader\);': 'bootrev',
    r'dw\(vcurswrev\);': 'swrev',
    r'dw\(vfwname\);': 'fwname', 
    r'dw\(vfwbldtime\);': 'fw_buildtime',
    r'dw\(vcmstatus\);': 'status',
    r'dw\(vcm_operational\);': 'operational',
    r'dw\(vcm_state_ds\);': 'downstream_scan', #  DOCSIS Downstream Scanning:  
    r'dw\(vcm_state_us\);': 'upstream_ranging', # DOCSIS Ranging: 
    r'dw\(vcm_state_dhcp\);': 'dhcp', #  DOCSIS DHCP: 
    r'dw\(vcm_state_tftp\);': 'tftp', #  DOCSIS TFTP: 
    r'dw\(vcm_state_reg\);': 'registration', #  DOCSIS Data Reg Complete: 
    r'dw\(vcm_state_privacy\);': 'privacy', #  DOCSIS Privacy: 
    r'dw\(msg_st_completed\);': 'completed',
    r'dw\(venabled\);': 'enabled',
    r'dw\(vdisabled\);': 'disabled',
    }

def untokenize(s, tokens=epc3008_tokens):
    for k,v in tokens.items():
        s = re.sub(k, v, s)
    return s
    
about_table = soup.find('script', text='dw(vt_docsystem);').find_parent('table')
for row in about_table.find('table').find_all(lambda tag: tag.name == 'tr' and len(tag.find_all('td')) == 2):
    cols = row.find_all('td')
    name = untokenize( cols[0].get_text() ).strip()
    value = untokenize( cols[1].get_text() ).strip()
    
    if name == "fw_buildtime": # Parse the build time to be ISO-8601
        # Reference: '2013+6+27+0+11+6+20'
        # Meaning of '0' is unknown
        value = '{0:04d}-{1:02d}-{2:02d}T{4:02d}:{5:02d}:{6:02d}'.format( *map(int, value.split('+')) )
    
    print("ABOUT: name='%s' value='%s'" % (name, value))

modem_state_table = soup.find('script', text='dw(vcm_state);').find_parent('table')
for row in modem_state_table.find('table').find_all(lambda tag: tag.name == 'tr' and len(tag.find_all('td')) == 2):
    cols = row.find_all('td')
    name = untokenize( cols[0].get_text() ).strip()
    value = untokenize( cols[1].get_text() ).strip()
    
    print("MODEM: name='%s' value='%s'" % (name, value))

# print(modem_state_table)

ds_ch_table = soup.find('script', text='dw(vdsch);').find_parent('table')
for row in ds_ch_table.find('table').find_all(lambda tag: tag.name == 'tr' and len(tag.find_all('td')) == 3):
    cols = row.find_all('td')
    
    ch = untokenize( cols[0].get_text() ).strip()
    if len(ch) == 0: # Skip if no channel is defined for row
        continue
    
    txpower = untokenize( cols[1].get_text() ).strip()
    snr = untokenize( cols[2].get_text() ).strip()
    print("DS CH: ch='%s' txpower='%s' SNR='%s'" % (ch, txpower, snr))


us_ch_table = soup.find('script', text='dw(vusch);').find_parent('table')
for row in us_ch_table.find('table').find_all(lambda tag: tag.name == 'tr' and len(tag.find_all('td')) == 2):
    cols = row.find_all('td')
    
    ch = untokenize( cols[0].get_text() ).strip()
    if len(ch) == 0: # Skip if no channel is defined for row
        continue
    
    txpower = untokenize( cols[1].get_text() ).strip()
    print("US CH: ch='%s' txpower='%s'" % (ch, txpower))
    
