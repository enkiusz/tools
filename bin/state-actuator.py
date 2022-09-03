#!/usr/bin/env python3

#
# Copyright 2022 Maciej Grela <enki@fsck.pl>
# SPDX-License-Identifier: WTFPL
#

## Category: Making the Internet of Things work for you
## Shortdesc: Manage charging/discharging cycles with a the CBUS outputs of a FTDI dongle.

import logging
import sys
import re
import argparse
from types import SimpleNamespace
import json
from urllib.parse import urlparse
import time
from pyftdi.ftdi import Ftdi
from enum import Enum, IntFlag


CBUS3 = 0b1000
CBUS2 = 0b0100

CHRG_REQ = CBUS3
DISCH_REQ = CBUS2

log = logging.getLogger(__name__)

config = SimpleNamespace(
    loglevel="INFO",

    # FTDI device URL
    url='ftdi://ftdi/1',

    # MQTT broker hostname
    mqtt_broker=None,

    # MQTT topic
    mqtt_topic="battery/state",

    # Initial charging state
    initial_state=dict(chrg=0, disch=0),
)



def get_state(ftdi):
    v = ftdi._cbus_out
    return dict(chrg=1 if v & CHRG_REQ > 0 else 0, disch=1 if v & DISCH_REQ > 0 else 0)


def set_state(ftdi, state):
    v = 0
    v |= CHRG_REQ if state['chrg'] == 1 else 0
    v |= DISCH_REQ if state['disch'] == 1 else 0
    ftdi.set_cbus_gpio(v)


def feedback_loop(config, **kwargs):
    log.info("Reading CBUS state from '{}'".format(args.url))

    while True:
        state = get_state(kwargs['ftdi'])

        log.debug("state '{}'".format(state))

        log.debug("Sending to MQTT topic '{}': {}'".format(config.mqtt_topic, json.dumps(state)))
        kwargs['mqtt'].publish(config.mqtt_topic, qos=1, payload=json.dumps(state))

        time.sleep(1)

    return 1


def on_message(client, userdata, message):
    ftdi = userdata
    log.info("message received for topic='{}' {}".format(message.topic, message.payload))

    try:
        set_state(ftdi, json.loads(message.payload))
    except Exception as e:
        log.error(e)
        log.error("error while setting new state '{}'".format(message.payload))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage charging/discharging cycles with a the CBUS outputs of a FTDI dongle.")
    parser.add_argument("--loglevel", default=config.loglevel, help="Log level")
    parser.add_argument("-u", "--url", metavar="URL", default=config.url, help="The FTDI device URL")
    parser.add_argument("--mqtt-broker", metavar="NAME", help="Send data to specified MQTT broker URL")
    parser.add_argument("--mqtt-topic", metavar="TOPIC", default=config.mqtt_topic, help="Set MQTT topic")
    parser.add_argument("--mqtt-reconnect-delay", metavar="MIN MAX", nargs=2, type=int, help="Set MQTT client reconnect behaviour")

    args = parser.parse_args()
    config.__dict__.update(vars(args))

    logging.basicConfig(level=getattr(logging, config.loglevel))

    ftdi = Ftdi()
    ftdi.open_from_url(url=config.url)

    # Set bitbang mode
    ftdi.set_bitmode(0, Ftdi.BitMode.CBUS)

    # Set output mode on both chrg and disch pins
    ftdi.set_cbus_direction(CHRG_REQ|DISCH_REQ, CHRG_REQ|DISCH_REQ)

    # Set initial state
    set_cbus_out(ftdi, config.initial_state)

    broker_url = urlparse(config.mqtt_broker)
    log.debug("MQTT URL {}".format(broker_url))

    import paho.mqtt.client as mqtt
    import ssl

    mqtt_client = mqtt.Client(userdata=ftdi)
    mqtt_client.enable_logger(logger=log)

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
        mqtt_client.loop_start()

        mqtt_client.subscribe(config.mqtt_topic + '/set', qos=1)
    except:
        # Connection to broker failed
        log.error("Cannot connect to MQTT broker", exc_info=True)
        sys.exit(1)

    log.debug("Configuration dump: {}".format(config))

    try:
        feedback_loop(config, mqtt=mqtt_client, ftdi=ftdi)
    except Exception as e:
        print(e)
    finally:
        # Restore initial state
        set_cbus_out(ftdi, config.initial_state)
        ftdi.close()
