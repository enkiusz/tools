#!/usr/bin/env python3

## Category: Information security
## Shortdesc: Convert basic information from a Nessus XML scan report to a nmap XML report

# Before running this script you need to install the vulnscan-parser python module.
# You can do that using pip:
# python3 -m pip install git+https://github.com/happyc0ding/vulnscan-parser.git

#
# Information included:
# - detected hosts
# - open ports
#

import argparse
import logging
import structlog
import sys
from collections import defaultdict

from vulnscan_parser.parser.nessus.xml import NessusParserXML
from xml.etree.ElementTree import ElementTree, Element, SubElement, Comment, tostring

# Reference: https://stackoverflow.com/a/49724281
LOG_LEVEL_NAMES = [logging.getLevelName(v) for v in
                   sorted(getattr(logging, '_levelToName', None) or logging._levelNames) if getattr(v, "real", 0)]

log = structlog.get_logger()


def main(config):
    nessus_parser = NessusParserXML()
    nessus_parser.parse(config.nessus_filename)

    log.info('nessus report parsed', filename=config.nessus_filename, hosts_count=len(nessus_parser.hosts), services_count=len(nessus_parser.services))
    
    nmaprun = Element('nmaprun')
    tree = ElementTree(element=nmaprun)
    nmaprun.set('scanner', 'nessus')

    hosts = defaultdict(default_factory=lambda k: dict(ports={}))

    for host_id, nessus_host in nessus_parser.hosts.items():

        host = SubElement(nmaprun, 'host')
        addr = SubElement(host, 'address')
        addr.set('addrtype', 'ipv4')
        addr.set('addr', nessus_host.ip)

        hostnames = SubElement(host, 'hostnames')
        for nessus_hostname in nessus_host.hostnames:
            hostname = SubElement(hostnames, 'hostname')
            hostname.set('type', nessus_hostname['type'])
            hostname.set('name', nessus_hostname['name'])

        ports = SubElement(host, 'ports')
        for nessus_service in nessus_host.services:
            # Ignore invalid port numbers
            if nessus_service.port == 0:
                continue

            #print(nessus_service.to_dict())
            port = SubElement(ports, 'port')
            port.set('protocol', nessus_service.protocol)
            port.set('portid', str(nessus_service.port))

            service = SubElement(port, 'service')
            service.set('name', nessus_service.name)

    tree.write(config.nmap_filename, xml_declaration=True, encoding='UTF-8')
    log.info('nmap report generated', filename=config.nmap_filename)

if __name__ == "__main__":
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr)
    )

    parser = argparse.ArgumentParser(description='Convert a Nessus XML report into a nmap XML report')
    parser.add_argument('--loglevel', choices=LOG_LEVEL_NAMES, default='INFO', help='Change log level')
    parser.add_argument('nessus_filename', help='Nessus scanner output file')
    parser.add_argument('nmap_filename', help='The filename of the resulting nmap XML file')
    args = parser.parse_args()

    # Restrict log message to be above selected level
    structlog.configure( wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, args.loglevel)) )

    log.debug('config', args=args)

    main(config=args)