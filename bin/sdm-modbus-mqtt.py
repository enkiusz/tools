#!/usr/bin/env python3

#
# Copyright 2021 Maciej Grela <enki@fsck.pl>
# SPDX-License-Identifier: WTFPL
#

## Category: Making the Internet of Things work for you
## Shortdesc: Query power import/export measurements from an Eastron SDM72D-M Modbus 3-phase bidirectional energy meter and publish them as SenML records to MQTT

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
import random
import threading

# $ python3 -m pip install sdm_modbus
import sdm_modbus

# Reference: https://stackoverflow.com/a/49724281
LOG_LEVEL_NAMES = [logging.getLevelName(v) for v in
                   sorted(getattr(logging, '_levelToName', None) or logging._levelNames) if getattr(v, "real", 0)]

log = structlog.get_logger()

config = SimpleNamespace(
    loglevel="INFO",

    # See:
    # $ python3 -m serial.tools.list_ports -v
    serialport_query = "",

    # Default serial port settings
    port=None,
    baud=9600,
    stopbits=1,
    parity='N',
    timeout=1,

    # Modbus protocol settings
    address=1,
    query_period=5,  # Time between Modbus queries
    
    # MQTT broker hostname
    mqtt_broker=None,

    # MQTT topic
    topic_base="sdm",

    # The fake pulse interval.
    # Fake pulses are generated in random intervals between [0, fake_pulse_interval] seconds.
    fake_pulse_interval=5,

    # Generate fake measurements instead of querying Modbus
    fake_measurements = False,
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


def fake_source(config):

    while True:
          yield({
            'total_import_active_power': dict(u='W', v=500 - 1000*random.random()),
            'total_export_active_power': dict(u='W', v=500 - 1000*random.random()),
          })
          time.sleep(config.fake_pulse_interval * random.random())


def modbus_source(config):

    if config.port is None:
        config.port=find_serial_port(config.serialport_query)

    log.info('using serial port', port=config.port)

    # TODO: Support other Eastron meter models
    meter = sdm_modbus.SDM72(
          device=config.port,
          baud=config.baud,
          stopbits=config.stopbits,
          parity=config.parity,
          timeout=config.timeout,
          unit=config.address
    )

    while True:

          yield({
            # Take absolute values on both measurements, the import/export names already indicate the direction where energy flows.
            # Negatie energy flow values are confusing.
            'total_import_active_power': dict(u='W', v=abs(meter.read('import_total_power_active'))),
            'total_export_active_power': dict(u='W', v=abs(meter.read('export_total_power_active'))),
          })
          time.sleep(config.query_period)


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


def mqtt_loop(config):
    mqtt_client.loop_forever(retry_first_connection=True)

if __name__ == "__main__":
    # Restrict log message to be above selected level
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr)
    )

    parser = argparse.ArgumentParser(description="Measure wind speed based on sensor pulse frequency, send to MQTT broker as RFC8428 SenML Records")
    parser.add_argument('--loglevel', choices=LOG_LEVEL_NAMES, default='INFO', help='Change log level')

    # TODO: Add additional parameters, most notably Modbus address
    parser.add_argument("-p", "--port", metavar="DEV", help="The serial port that connects to the Modbus RTU master interface")
    parser.add_argument("--find-serialport", metavar="QUERY", dest="serialport_query", help="Find a serial port using serial.tools.list_ports.grep(QUERY)")
    parser.add_argument("-b", "--baud", metavar="BPS", type=int, help="The bitrate of the Modbus RTU serial port")
    parser.add_argument("--mqtt-broker", metavar="NAME", help="Send data to specified MQTT broker URL")
    parser.add_argument("--topic-base", metavar="TOPIC", help="Set MQTT topic base")
    parser.add_argument("--fake-measurements", action='store_true', help="Generate fake measurements instead of querying Modbus")

    args = parser.parse_args()

    # Restrict log message to be above selected level
    structlog.configure( wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, args.loglevel)) )

    config.__dict__.update({ (k,v) for (k,v) in vars(args).items() if v is not None})
    log.debug('config', config=config)

    if config.mqtt_broker:
        broker_url = urlparse(config.mqtt_broker)

        import paho.mqtt.client as mqtt
        import ssl

        mqtt_client = mqtt.Client()
        #mqtt_client.enable_logger(logger=log)  # FIXME: How to configure paho-mqtt to use structlog?

        if broker_url.scheme == 'mqtts':
            log.debug("Initializing MQTT TLS")
            mqtt_client.tls_set(cert_reqs=ssl.CERT_NONE)
            mqtt_port = 8883
        else:
            mqtt_port = 1883

        try:
            mqtt_thread = threading.Thread(target=mqtt_loop, args=(config,))
            mqtt_thread.start()

            log.info("Connecting to MQTT broker URL '{}'".format(config.mqtt_broker))
            mqtt_client.connect(broker_url.netloc, port=mqtt_port)
        except:
            # Connection to broker failed, disable MQTT
            log.error("Cannot connect to MQTT broker, MQTT will be disabled", exc_info=True)
    else:
        mqtt_client = None

    if config.fake_measurements:
        source = fake_source(config)
    else:
        source = modbus_source(config)

    measurement_loop(config, source)
