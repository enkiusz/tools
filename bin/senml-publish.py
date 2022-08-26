#!/usr/bin/env python3

#
# Copyright 2022 Maciej Grela <enki@fsck.pl>
# SPDX-License-Identifier: WTFPL
#

## Category: Making the Internet of Things work for you
## Shortdesc: Publish RFC8428 SenML Records read from a specified serial port to an MQTT broker.

import logging
import sys
import re
import argparse
import serial
import serial.tools.list_ports
from types import SimpleNamespace
import json
from urllib.parse import urlparse

log = logging.getLogger(__name__)

config = SimpleNamespace(
    loglevel="INFO",

    # The bitrate of the serial port
    bitrate=115200,

    # MQTT broker hostname
    mqtt_broker=None,

    # MQTT topic
    mqtt_topic=None,
)


#
# Try to find the first port matching a given query
#
def find_serial_port(query):
    try:
        (port, desc, hwid) = next(serial.tools.list_ports.grep(query))
    except StopIteration:
        log.error("Could not find port using query '{}', please supply the serial port device manually".format(query))
        return None

    log.debug("Found port: {} (query '{}', description '{}' hwid '{}')".format(port, query, desc, hwid))
    return port

def serial_source(config):

    if config.port is None:
        config.port=find_serial_port(config.serialport_query)

    log.info("Reading SenML records from serial port '{}'".format(config.port))

    with serial.Serial(config.port, config.bitrate, timeout=1) as ser:

        while True:
            line = ser.readline().decode('utf8').rstrip()
            if len(line) == 0:
                continue

            log.debug("Serial read line: {}".format(repr(line)))

            try:
                j = json.loads(line)
                yield dict(senml=j)
            except Exception as e:
                log.error("Cannot parse line from serial port: '{}'".format(repr(line)))


def main_loop(config, source):

    log.info("Reading SenML records '{}'".format(args.port))
    while True:
        pkt = next(source)
        log.debug("from source '{}'".format(repr(pkt)))

        senml = pkt['senml']
        if mqtt_client:
            for record in senml:
                mqtt_topic = config.mqtt_topic + record['n']
                log.debug("Sending to MQTT topic '{}': {}'".format(mqtt_topic, json.dumps(record)))
                mqtt_client.publish(mqtt_topic, qos=1, payload=json.dumps(record))

    return 1

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Publish RFC8428 SenML Records read from a specified serial port to an MQTT broker")
    parser.add_argument("--loglevel", default=config.loglevel, help="Log level")
    parser.add_argument("-p", "--port", metavar="DEV", help="The serial port to read SenML Record Packs, read from stdin if not specified")
    parser.add_argument("--find-serialport", metavar="QUERY", dest="serialport_query", default='^Arduino', help="Find a serial port using serial.tools.list_ports.grep(QUERY)")
    parser.add_argument("-b", "--bitrate", metavar="BPS", default=config.bitrate, type=int, help="The bitrate of the serial port")
    parser.add_argument("--mqtt-broker", metavar="name", help="send data to specified MQTT broker URL")
    parser.add_argument("--mqtt-topic", metavar="TOPIC", default=config.mqtt_topic, help="Set MQTT topic, the SenML record name will be appended to it")
    parser.add_argument("--mqtt-reconnect-delay", metavar="MIN MAX", nargs=2, type=int, help="Set MQTT client reconnect behaviour")

    args = parser.parse_args()
    config.__dict__.update(vars(args))

    logging.basicConfig(level=getattr(logging, config.loglevel))
    if config.mqtt_broker:
        broker_url = urlparse(config.mqtt_broker)
        log.debug("MQTT URL {}".format(broker_url))

        import paho.mqtt.client as mqtt
        import ssl

        mqtt_client = mqtt.Client()
        mqtt_client.enable_logger(logger=log)

        if broker_url.scheme == 'mqtts':
            Log.Debug("Initializing MQTT TLS")
            mqtt_client.tls_set(cert_reqs=ssl.CERT_NONE)
            mqtt_port = 8883
        else:
            mqtt_port = 1883

        if config.mqtt_reconnect_delay is not None:
            (_min_delay, _max_delay) = config.mqtt_reconnect_delay
            mqtt_client.reconnect_delay_set(min_delay=_min_delay, max_delay=_max_delay)

        try:
            log.info("Connecting to MQTT broker URL '{}'".format(config.mqtt_broker))
            mqtt_client.connect(broker_url.netloc, port=mqtt_port)
            mqtt_client.loop_start()
        except:
            # Connection to broker failed
            log.error("Cannot connect to MQTT broker", exc_info=True)
            sys.exit(1)

    else:
        mqtt_client = None

    log.debug("Configuration dump: {}".format(config))

    source = serial_source(config)

    sys.exit(main_loop(config, source))
