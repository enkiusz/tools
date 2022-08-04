#!/usr/bin/env python3

#
# Copyright 2018 Maciej Grela <enki@fsck.pl>
# SPDX-License-Identifier: WTFPL
#

## Category: Making the Internet of Things work for you
## Shortdesc: Host script for reading pulses from SObasic Arduino interface and forwarding them to an MQTT broker.

import logging
import sys
import re
import argparse
import serial
import datetime as dt
import serial.tools.list_ports
from types import SimpleNamespace
import json
from urllib.parse import urlparse
import time
import random
import threading
import pint

ureg = pint.UnitRegistry()
log = logging.getLogger(__name__)

config = SimpleNamespace(
    loglevel="INFO",

    # The bitrate of the serial port
    bitrate=115200,

    # The amount of measured resource (energy/water/gas) consumed for each pulse. 
    # The amount of pulses will be multipled by this value before sending to the MQTT server.
    quantum=1.0,

    # Units for the measured resource (optional). If not defined electrical energy is assumed.
    # Note, that the RRD database doesn't store unit information, this is used only when the
    # data is sent to an MQTT server.
    resource_unit="Wh", # The unit for the actual resource (kWh, m^3, etc.)
    rate_unit="W", # The unit for the resource consumption rate (W, liters/s, etc.)

    # MQTT broker hostname
    mqtt_broker=None,

    # MQTT topic
    mqtt_topic="energy",

    # The fake pulse interval.
    # Fake pulses are generated in random intervals between [0, fake_pulse_interval] seconds.
    fake_pulse_interval=5
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

def fake_pulse_source(config):
    i = 0
    prev_ts = None

    while True:
        ts = dt.datetime.now(dt.timezone.utc)

        if prev_ts:
            rate = ureg.parse_expression("({} {}) / ({} s)".format(
                config.quantum, config.resource_unit, (ts - prev_ts).total_seconds())
            )

            yield dict(i=i, u=config.rate_unit, v=rate.m_as(config.rate_unit), info='fake pulse')

        prev_ts = ts
        i += 1

        time.sleep(config.fake_pulse_interval * random.random())

def serial_pulse_source(config):

    if config.port is None:
        config.port=find_serial_port(config.serialport_query)

    log.info("Reading pulses from serial port '{}'".format(config.port))

    # Set the timeout so that it corresponds to the period
    with serial.Serial(config.port, config.bitrate, timeout=1) as ser:

        while True:
            line = ser.readline().decode('ascii').rstrip()
            if len(line) == 0:
                continue

            log.debug("Serial read line: {}".format(repr(line)))
            yield dict(info=line)


def measurement_loop(config, source):

    log.info("Reading pulses from '{}', quantum '{}'".format(args.port, args.quantum))

    prev_ts = None
    while True:
        pulse = next(source)

        log.debug("from source '{}'".format(repr(pulse)))

        if mqtt_client:
            log.debug("Sending to MQTT topic '{}': {}'".format(config.mqtt_topic, json.dumps(pulse)))
            mqtt_client.publish(config.mqtt_topic, qos=1, payload=json.dumps(pulse))

    return 1

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Process SO pulses and report resource usage to an MQTT broker as RFC8428 SenML Records")
    parser.add_argument("--loglevel", default=config.loglevel, help="Log level")
    parser.add_argument("-p", "--port", metavar="DEV", help="The serial port that connects to the SObasic module")
    parser.add_argument("--find-serialport", metavar="QUERY", dest="serialport_query", default='^Arduino', help="Find a serial port using serial.tools.list_ports.grep(QUERY)")
    parser.add_argument("-b", "--bitrate", metavar="BPS", default=config.bitrate, type=int, help="The bitrate of the serial port")
    parser.add_argument("-q", "--quantum", metavar="QUANTUM", type=float, default=config.quantum, help="The amount of measured resource (energy/water/gas) consumed for each pulse.")
    parser.add_argument("--resource-unit", metavar="UNIT", default=config.resource_unit, help="The unit of the measured resource (J, Wh, kWh, m^3, etc.)")
    parser.add_argument("--rate-unit", metavar="UNIT", default=config.rate_unit, help="The unit of the reported resource consumption rate (W, liters/s, etc.)")
    parser.add_argument("--mqtt-broker", metavar="NAME", help="Send data to specified MQTT broker URL")
    parser.add_argument("--mqtt-topic", metavar="TOPIC", default=config.mqtt_topic, help="Set MQTT topic")
    parser.add_argument("--mqtt-reconnect-delay", metavar="MIN MAX", nargs=2, type=int, help="Set MQTT client reconnect behaviour")
    parser.add_argument("--fake-pulses", action='store_true', default=False, help="Generate fake pulses instead of reading them from the serial port")

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
            log.debug("Initializing MQTT TLS")
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

    if config.fake_pulses:
        source = fake_pulse_source(config)
    else:
        source = serial_pulse_source(config)

    sys.exit(measurement_loop(config, source))
