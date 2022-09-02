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

# Reference: https://gist.github.com/ptmcg/23ba6e42d51711da44ba1216c53af4ea
class ArgTypeMixin(Enum):

    @classmethod
    def argtype(cls, s: str) -> Enum:
        try:
            return cls[s]
        except KeyError:
            raise argparse.ArgumentTypeError(
                f"{s!r} is not a valid {cls.__name__}")

    def __str__(self):
        return self.name

CBUS3 = 0b1000
CBUS2 = 0b0100

CHRG_REQ = CBUS3
DISCH_REQ = CBUS2

class BatteryStates(ArgTypeMixin, IntFlag):
    idle = 0
    chrg = CHRG_REQ
    disch = DISCH_REQ
    chrg_disch = CHRG_REQ|DISCH_REQ

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
    initial_state=BatteryStates.idle,
)



def get_cbus_out(ftdi) -> BatteryStates:
    return BatteryStates(ftdi._cbus_out)


def set_cbus_out(ftdi, state: BatteryStates):
    ftdi.set_cbus_gpio(state.value)


def feedback_loop(config, **kwargs):
    log.info("Reading CBUS state from '{}'".format(args.url))

    while True:
        state = dict(state=get_cbus_out(kwargs['ftdi']).name, ts=time.time())

        log.debug("state '{}'".format(state))

        log.debug("Sending to MQTT topic '{}': {}'".format(config.mqtt_topic, json.dumps(state)))
        kwargs['mqtt'].publish(config.mqtt_topic, qos=1, payload=json.dumps(state))

        time.sleep(1)

    return 1


def on_message(client, userdata, message):
    ftdi = userdata
    log.info("message received for topic='{}' {}".format(message.topic, message.payload))

    try:
        j = json.loads(message.payload)
        set_cbus_out(ftdi, BatteryStates[j['state']])
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
    parser.add_argument("--initial-state", metavar="STATE", type=BatteryStates.argtype, default=config.initial_state, choices=BatteryStates, help="Initial state")

    args = parser.parse_args()
    config.__dict__.update(vars(args))

    logging.basicConfig(level=getattr(logging, config.loglevel))

    ftdi = Ftdi()
    ftdi.open_from_url(url=config.url)

    # Set bitbang mode
    ftdi.set_bitmode(0, Ftdi.BitMode.CBUS)

    # Set output mode on both chrg and disch pins
    ftdi.set_cbus_direction(BatteryStates.chrg_disch, BatteryStates.chrg_disch)

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
