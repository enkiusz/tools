#!/usr/bin/env python3

#
# Copyright 2022 Maciej Grela <enki@fsck.pl>
# SPDX-License-Identifier: WTFPL
#

## Category: Making the Internet of Things work for you
## Shortdesc: Query power measurement from dual PZEM016 modbus meters and publish them to an MQTT broker

import sys
import structlog
import logging
import argparse
import serial.tools.list_ports
from types import SimpleNamespace
import json
from urllib.parse import urlparse
from pathlib import Path
import time

from pzem import PZEM_016
import minimalmodbus


# Reference: https://stackoverflow.com/a/49724281
LOG_LEVEL_NAMES = [logging.getLevelName(v) for v in
                   sorted(getattr(logging, '_levelToName', None) or logging._levelNames) if getattr(v, 'real', 0)]

log = structlog.get_logger()

config = SimpleNamespace(
    loglevel='INFO',

    # See:
    # $ python3 -m serial.tools.list_ports -v
    serialport_query = '',

    # Default serial port settings
    port=None,
    baud=9600,
    stopbits=1,
    parity='N',
    timeout=1,

    # Modbus protocol settings
    query_period=10,  # Time between Modbus queries

    # MQTT broker hostname
    mqtt_broker=None,

    # MQTT topic
    topic_base='pzem016',

    # MQTT reconnect parameters
    mqtt_reconnect_delay=(1, 5),
)


#
# Try to find the first port matching a given query
#
def find_serial_port(query):
    try:
        (port, desc, hwid) = next(serial.tools.list_ports.grep(query))
    except StopIteration:
        log.error('no port found', query=query)
        return None

    log.debug('found port', port=port, desc=desc, hwid=hwid)
    return port

def cleanup_pzem_reading(reading):
    # drop stuff we don't need
    del reading['timestamp']
    del reading['energy']
    del reading['alarm_status']
    del reading['alarm_threshold']

def modbus_source(config):

    if config.port is None:
        config.port=find_serial_port(config.serialport_query)

    log.info('using serial port', port=config.port)

    pzem_left = PZEM_016(config.port, slave_addr=16)
    pzem_right = PZEM_016(config.port, slave_addr=17)

    while True:
        measurement=dict()

        try:
            reading_left = pzem_left.read()
            log.debug('left', pkt=reading_left)
            cleanup_pzem_reading(reading_left)

            measurement['left'] = reading_left
        except minimalmodbus.ModbusException as e:
            log.error('modbus error', pzem=pzem_left, _exc_info=e)

        time.sleep(config.query_period / 2)

        try:
            reading_right = pzem_right.read()
            log.debug('right', pkt=reading_right)
            cleanup_pzem_reading(reading_right)

            measurement['right'] = reading_right
        except minimalmodbus.ModbusException as e:
            log.error('modbus error', pzem=pzem_right, _exc_info=e)

        time.sleep(config.query_period / 2)

        if len(measurement) > 0:
            yield measurement


def measurement_loop(config, source):

    while True:
        measurement = next(source)
        log.debug('measurement', measurement=measurement)

        if mqtt_client:

           for (k,v) in measurement.items():
               payload = json.dumps(v)
               topic = str(Path(config.topic_base).joinpath(k))
               log.debug('publishing to mqtt', topic=topic, payload=payload)
               mqtt_client.publish(topic, qos=1, payload=payload)


if __name__ == '__main__':
    # Restrict log message to be above selected level
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr)
    )

    parser = argparse.ArgumentParser(description='Measure wind speed based on sensor pulse frequency, send to MQTT broker as RFC8428 SenML Records')
    parser.add_argument('--loglevel', choices=LOG_LEVEL_NAMES, default='INFO', help='Change log level')
    parser.add_argument('-p', '--port', metavar='DEV', help='The serial port that connects to the Modbus RTU master interface')
    parser.add_argument('--find-serialport', metavar='QUERY', dest='serialport_query', help='Find a serial port using serial.tools.list_ports.grep(QUERY)')
    parser.add_argument('-b', '--baud', metavar='BPS', type=int, help='The bitrate of the Modbus RTU serial port')
    parser.add_argument('--mqtt-broker', metavar='NAME', help='Send data to specified MQTT broker URL')
    parser.add_argument('--topic-base', metavar='TOPIC', help='Set MQTT topic base')
    parser.add_argument('--mqtt-reconnect-delay', metavar='MIN MAX', nargs=2, type=int, help='Set MQTT client reconnect behaviour')


    args = parser.parse_args()

    # Restrict log message to be above selected level
    structlog.configure( wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, args.loglevel)) )
    logging.basicConfig(level=getattr(logging, args.loglevel))
    paho_logger = logging.getLogger('paho-mqtt')

    config.__dict__.update({ (k,v) for (k,v) in vars(args).items() if v is not None})
    log.debug('config', config=config)

    if config.mqtt_broker:
        broker_url = urlparse(config.mqtt_broker)

        import paho.mqtt.client
        import paho.mqtt.enums
        import ssl

        mqtt_client = paho.mqtt.client.Client(callback_api_version=paho.mqtt.enums.CallbackAPIVersion.VERSION2)
        mqtt_client.enable_logger(logger=paho_logger)

        if broker_url.scheme == 'mqtts':
            log.debug('Initializing MQTT TLS')
            mqtt_client.tls_set(cert_reqs=ssl.CERT_NONE)
            mqtt_port = 8883
        else:
            mqtt_port = 1883

        if config.mqtt_reconnect_delay is not None:
            (_min_delay, _max_delay) = config.mqtt_reconnect_delay
            mqtt_client.reconnect_delay_set(min_delay=_min_delay, max_delay=_max_delay)

        try:
            log.info('Connecting to MQTT broker', url=config.mqtt_broker)
            mqtt_client.connect(broker_url.netloc, port=mqtt_port)
            mqtt_client.loop_start()
        except:
            # Connection to broker failed
            log.error('Cannot connect to MQTT broker', exc_info=True)
            sys.exit(1)
    else:
        mqtt_client = None

    source = modbus_source(config)
    measurement_loop(config, source)
