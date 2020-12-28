#!/usr/bin/env python3

#
# Copyright 2020 Maciej Grela <enki@fsck.pl>
# SPDX-License-Identifier: WTFPL
#

## Category: Making the Internet of Things work for you
## Shortdesc: Measure wind speed based on a pulse sensor and send the measurements to an MQTT broker as SenML Records

import logging
import sys
import os
import re
import argparse
import serial
import serial.tools.list_ports
from types import SimpleNamespace
import json
from urllib.parse import urlparse
import time
import random
import threading

log = logging.getLogger(__name__)

config = SimpleNamespace(
    loglevel="INFO",

    # The bitrate of the serial port
    bitrate=115200,

    # The minimal wind speed that gets reported to MQTT
    min_reported_speed = 0.0,

    # The wind speed unit reported
    unit="m/s",

    # MQTT broker hostname
    mqtt_broker=None,

    # MQTT topic
    mqtt_topic="windspeed",

    # The fake pulse interval.
    # Fake pulses are generated in random intervals between [0, fake_pulse_interval] seconds.
    fake_pulse_interval=5
)

#
# Try to find the first Arduino serial port
#
def find_arduino_serial():
    try:
        (port, desc, hwid) = next(serial.tools.list_ports.grep("^Arduino"))
    except StopIteration:
        log.error("Could not detect an Arduino connected, please supply the serial port device manually")
        return None

    log.debug("Using first available serial port with an Arduino connected: {} (description '{}' hwid '{}')".format(port, desc, hwid))
    return port

def fake_pulse_source(config):
    i = 0

    while True:
        yield dict(i=i, info='{} Hz'.format(5*random.randpom()))
        time.sleep(config.fake_pulse_interval * random.random())
        i += 1

def serial_pulse_source(config):

    if config.port is None:
        config.port=find_arduino_serial()

    log.info("Reading pulse frequency data from serial port '{}'".format(config.port))

    with serial.Serial(config.port, config.bitrate, timeout=1) as ser:

        while True:
            line = ser.readline().decode('ascii').rstrip()
            if len(line) == 0:
                continue

            log.debug("Serial read line: {}".format(repr(line)))
            yield dict(info=line)


def measurement_loop(config, source):

    while True:
        pulse = next(source)
        log.debug("Data received from source: '{}'".format(pulse))

        if mqtt_client:
            m = re.match("([0-9.]+) Hz", pulse['info'])
            if m is None:
                log.warning("Cannot parse string {} from source, '<number> Hz' is expected".format(repr(pulse['info'])))
                continue

            windspeed = config.conversion_factor * float(m.group(1))
            if windspeed >= config.min_reported_speed:
                sensml = dict(u="m/s", v=windspeed)

                log.debug("Sending to MQTT topic '{}': '{}'".format(config.mqtt_topic, json.dumps(sensml)))
                mqtt_client.publish(config.mqtt_topic, qos=1, payload=json.dumps(sensml))
            else:
                log.debug("Wind speed {} is below minimum ('{}'), not reporting".format(windspeed, config.min_reported_speed))

    return 0

def mqtt_loop(config):
    mqtt_client.loop_forever(retry_first_connection=True)

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Measure wind speed based on sensor pulse frequency, send to MQTT broker as RFC8428 SenML Records")
    parser.add_argument("--loglevel", default=config.loglevel, help="Log level")
    parser.add_argument("-p", "--port", metavar="DEV", help="The serial port that connects to the pulsefreq-basic module")
    parser.add_argument("-b", "--bitrate", metavar="BPS", default=config.bitrate, type=int, help="The bitrate of the serial port")
    parser.add_argument("-f", "--conversion_factor", required=True, metavar="FACTOR", type=float, help="The conversion factor from frequency to wind speed")
    parser.add_argument("--min-speed", type=float, metavar="SPEED", default=config.min_reported_speed, help="Minimum wind speed reported to MQTT")
    parser.add_argument("--unit", default=config.unit, metavar="UNIT", help="The unit of windspeed")
    parser.add_argument("--mqtt-broker", metavar="NAME", help="Send data to specified MQTT broker URL")
    parser.add_argument("--mqtt-topic", metavar="TOPIC", default=config.mqtt_topic, help="Set MQTT topic")
    parser.add_argument("--fake-pulses", action='store_true', default=False, help="Generate fake pulses instead of reading them from the serial port")

    args = parser.parse_args()
    config.__dict__.update(vars(args))

    logging.basicConfig(level=getattr(logging, config.loglevel))
    if config.mqtt_broker:
        broker_url = urlparse(config.mqtt_broker)

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

    log.debug("Configuration dump: {}".format(config))

    if config.fake_pulses:
        source = fake_pulse_source(config)
    else:
        source = serial_pulse_source(config)

    sys.exit(measurement_loop(config, source))
