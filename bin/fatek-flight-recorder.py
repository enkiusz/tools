#!/usr/bin/env python3

#
# Copyright 2022 Maciej Grela <enki@fsck.pl>
# SPDX-License-Identifier: WTFPL
#

## Category: Making the Internet of Things work for you
## Shortdesc: Query a Fatek FBs PLC on Port 0 and publish input (X) as well as output (Y) state via MQTT

# Reference: https://github.com/elshaka/fatek-serial
# Reference: https://github.com/mh-mansouri/FatekPLC_for_LabView/blob/main/FATEK%20Communication%20Protocol.pdf

import structlog
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
import socket

# Reference: https://stackoverflow.com/a/49724281
LOG_LEVEL_NAMES = [logging.getLevelName(v) for v in
                   sorted(getattr(logging, '_levelToName', None) or logging._levelNames) if getattr(v, "real", 0)]

log = structlog.get_logger()

config = SimpleNamespace(
    loglevel="INFO",

    # Serial port device
    port=None,

    # Serial protocol retransmit parameters
    timeout=5,
    retransmit_count=5,

    # Station number (address)
    station_no='01',

    # Query period
    query_period=5,  # Time between queries

    # MQTT broker hostname
    mqtt_broker=None,

    # MQTT topic
    mqtt_topic="fatek",

)


# The Fatek FBs Port 0 protocol uses an LRC like the Modbus ASCII protocol
def _lrc(string):
    lrc = 0
    for char in string:
        lrc += ord(char)
    return hex(lrc & 0xff)[2:].upper()


def transaction(ser, command, **kwargs):
    data = kwargs.get('data', '')
    config = kwargs['config']

    data = data.replace(' ','')
    string = '\x02' + config.station_no + command + data

    n = config.retransmit_count
    while n > 0:
        try:
            command = string + _lrc(string) + '\x03'
            log.debug('sent to port0', command=command)
            ser.write(command.encode('ascii'))

            response = ser.read_until('\x03').decode('ascii')[1:-3]
            log.debug('received from port0', response=response)
            if len(response) > 0:
                # TODO: Verify LRC and station number on received packets
                d = dict(
                    station = response[0:2],
                    command = response[2:4],
                    error = response[4:5],
                    data = response[5:]
                )

                if d['error'] != '0':
                    log.error('error response', command=command, response=response)
                    return None

                log.debug('parsed response', parsed=d)
                return d
            else:
                n -= 1
                log.warn('empty response', command=command, attempts_left=n)

        except serial.SerialTimeoutException as e:
            n -= 1
            log.warn('timeout', pkt=string, attempts_left=n)

    return None


def unpack_states(names, data):
    return zip(names, list(data))


def main_loop(config):
    
    log.info('using serial port', port=config.port)

    ser = serial.serial_for_url(config.port)
    ser.baudrate = 9600
    ser.bytesize = serial.SEVENBITS
    ser.parity = serial.PARITY_EVEN
    ser.stopbits = 1
    ser.timeout = config.timeout

    while True:

        input_count = 12
        input_names = [ f'X{i}' for i in range(0, input_count) ]

        # Read 0x0C inputs starting from X0000
        response = transaction(ser, command='44', config=config, data='0CX0000')
        if response:
            inputs = dict(unpack_states(input_names, response['data']))
            log.debug('input states', inputs=inputs)
        else:
            log.error('error reading inputs', response=response)

        output_count = 8
        output_names = [ f'Y{i}' for i in range(0, input_count) ]

        # Read 0x08 outputs starting from Y0000
        response = transaction(ser, command='44', config=config, data='08Y0000')
        if response:
            outputs = dict(unpack_states(output_names, response['data']))
            log.debug('output states', outputs=outputs)
        else:
            log.error('error reading outputs', response=response)

        payload = dict(inputs=dict(inputs), outputs=dict(outputs))
        if mqtt_client:
            for (name,v) in inputs.items():
                topic = f"{config.mqtt_topic}/inputs/{name}"
                log.debug('mqtt publish', topic=topic, payload=v)
                mqtt_client.publish(topic, qos=1, payload=str(v))
            for (name,v) in outputs.items():
                topic = f"{config.mqtt_topic}/outputs/{name}"
                log.debug('mqtt publish', topic=topic, payload=v)
                mqtt_client.publish(topic, qos=1, payload=str(v))


        time.sleep(config.query_period)

    return 1

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Query a Fatek FBs PLC on Port 0 and publish input (X) as well as output (Y) state via MQTT")
    parser.add_argument("--loglevel", default=config.loglevel, help="Log level")
    parser.add_argument("-p", "--port", metavar="URL", help="The serial port URL")
    parser.add_argument("--mqtt-broker", metavar="NAME", help="Send data to specified MQTT broker URL")
    parser.add_argument("--mqtt-topic", metavar="TOPIC", default=config.mqtt_topic, help="Set MQTT topic")
    parser.add_argument("--mqtt-reconnect-delay", metavar="MIN MAX", nargs=2, type=int, help="Set MQTT client reconnect behaviour")

    args = parser.parse_args()
    config.__dict__.update(vars(args))

    # Restrict log message to be above selected level
    structlog.configure( wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, args.loglevel)) )

    if config.mqtt_broker:
        broker_url = urlparse(config.mqtt_broker)
        log.debug("MQTT URL {}".format(broker_url))

        import paho.mqtt.client as mqtt
        import ssl

        mqtt_client = mqtt.Client()

        # TODO: How to attach structlog to paho?
        # mqtt_client.enable_logger(logger=log)

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

    log.debug('configuration dump', config=config)

    main_loop(config)
