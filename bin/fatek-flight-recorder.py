#!/usr/bin/env python3

#
# Copyright 2022,2023 Maciej Grela <enki@fsck.pl>
# SPDX-License-Identifier: WTFPL
#

## Category: Making the Internet of Things work for you
## Shortdesc: Monitor and control Fatek FBs PLC on Port 0 via MQTT

# Reference: https://github.com/elshaka/fatek-serial
# Reference: https://github.com/mh-mansouri/FatekPLC_for_LabView/blob/main/FATEK%20Communication%20Protocol.pdf
# Reference: https://github.com/Za-Ra/Fatek_FBs

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
import threading

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

    while True:

        input_count = 12
        input_names = [ f'X{i}' for i in range(0, input_count) ]

        with config._ser.lock:
            # Read 0x0C inputs starting from X0000
            response = transaction(config._ser, command='44', config=config, data='0CX0000')

        if response:
            inputs = dict(unpack_states(input_names, response['data']))
            log.debug('input states', inputs=inputs)
        else:
            log.error('error reading inputs', response=response)

        output_count = 8
        output_names = [ f'Y{i}' for i in range(0, input_count) ]

        with config._ser.lock:
            # Read 0x08 outputs starting from Y0000
            response = transaction(config._ser, command='44', config=config, data='08Y0000')

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

def on_message(client, userdata, message):
    config = userdata
    log.info('mqtt message', topic=message.topic, payload=message.payload)

    input_name = message.topic.removeprefix(f"{config.mqtt_topic}/").removesuffix("/set")
    _type = input_name[0]
    _number = int(input_name[1:])

    if message.payload == b'1':
        value_code = '3'  # Set
    elif message.payload == b'0':
        value_code = '4'  # Reset
    else:
        log.error('invalid payload', payload=message.payload)
        return

    if config._ser:
        try:
            with config._ser.lock:
                log.info("set state", topic=message.topic, value=message.payload, value_code=value_code)
                transaction(config._ser, command='42', config=config, data=f'{value_code}{_type}{_number:04d}')
        except Exception as e:
            log.error(e)
            log.error("error while setting new state '{}'".format(message.payload))
    else:
        log.warn('Serial port not open, skipping update')

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Query a Fatek FBs PLC on Port 0 and publish input (X) as well as output (Y) state via MQTT")
    parser.add_argument("--loglevel", default=config.loglevel, help="Log level")
    parser.add_argument("-p", "--port", metavar="URL", help="The serial port URL")
    parser.add_argument("--settable-input", metavar="INPUT", dest='settable_inputs', action='append', help="Specify inputs that will be accessible via MQTT")
    parser.add_argument("--mqtt-broker", metavar="NAME", help="Send data to specified MQTT broker URL")
    parser.add_argument("--mqtt-topic", metavar="TOPIC", default=config.mqtt_topic, help="Set MQTT topic")
    parser.add_argument("--mqtt-reconnect-delay", metavar="MIN MAX", nargs=2, type=int, help="Set MQTT client reconnect behaviour")

    args = parser.parse_args()
    config.__dict__.update(vars(args))

    # Restrict log message to be above selected level
    structlog.configure( wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, args.loglevel)) )

    log.info('using serial port', port=config.port)

    ser = serial.serial_for_url(config.port)
    ser.baudrate = 9600
    ser.bytesize = serial.SEVENBITS
    ser.parity = serial.PARITY_EVEN
    ser.stopbits = 1
    ser.timeout = config.timeout
    ser.lock = threading.Lock()
    config.__dict__.update(dict(_ser=ser))

    if config.mqtt_broker:
        broker_url = urlparse(config.mqtt_broker)
        log.debug("MQTT URL {}".format(broker_url))

        import paho.mqtt.client as mqtt
        import ssl

        mqtt_client = mqtt.Client(userdata=config)

        # TODO: How to attach structlog to paho?
        # mqtt_client.enable_logger(logger=log)

        mqtt_client.on_message = on_message

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

            if config.settable_inputs:
                for input_name in config.settable_inputs:
                    _type = input_name[0]
                    _number = int(input_name[1:])

                    with config._ser.lock:
                        # We need to disable the inputs first to disconnect from the external input pins
                        if transaction(ser, command='42', config=config, data=f'1{_type}{_number:04d}'):
                            topic = f"{config.mqtt_topic}/{input_name}/set"
                            log.debug('mqtt subscribe', topic=topic)
                            mqtt_client.subscribe(topic, qos=1)
                        else:
                            log.error('cannot disable input', input_name=input_name)

            mqtt_client.loop_start()
        except:
            # Connection to broker failed
            log.error("Cannot connect to MQTT broker", exc_info=True)
            sys.exit(1)

    else:
        mqtt_client = None

    log.debug('configuration dump', config=config)

    main_loop(config)
