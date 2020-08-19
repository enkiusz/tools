#!/usr/bin/env python3

#
# Copyright 2018 Maciej Grela <enki@fsck.pl>
# SPDX-License-Identifier: WTFPL
#

## Category: Making the Internet of Things work for you
## Shortdesc: Host script for reading pulses from SObasic Arduino interface and storing them into an RRD database.

import logging
import sys
import os
import re
import subprocess
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
    pretend=False,

    # Connection configuration

    # The bitrate of the serial port
    bitrate=115200,

    #
    # DB configuration
    #

    # Data source name
    ds_name="energy",

    # The interval is the time during all pulses are counted as a single energy usage value.
    interval=dt.timedelta(seconds=30),

    # The amount of measured resource (energy/water/gas) consumed for each pulse. 
    # The amount of pulses will be multipled by this value before storing in RRD or sending to the MQTT server.
    quantum=1.0,

    #
    # Units for the measured resource (optional). If not defined electrical energy is assumed.
    # Note, that the RRD database doesn't store unit information, this is used only when the
    # data is sent to an MQTT server.
    resource_unit="Wh", # The unit for the actual resource (kWh, m^3, etc.)
    rate_unit="W", # The unit for the resource consumption rate (W, liters/s, etc.)

    # Both min and max values are not limited (-Inf .. +Inf) to allow for bidirectional flow (like in net energy metering).
    min="U",
    max="U",

    rra_defs={
        # Prediction RRA
        #
        # This RRA stores AVERAGE readout in one step intervals for 90 days. This is basically the raw data gathered by the meter.
        # It's possible use is load prediction and general graphing of short-term data.
        #
        "prediction": {
            "cdf": "AVERAGE",
            "xff": 0.5,
            "interval": dt.timedelta(seconds=30),
            "duration": dt.timedelta(days=90)
        },

	    # Energy storage RRA
	    #
	    # The daily storage RRA stores the AVERAGE readouts in 24h intervals for 10 years.
	    # The average amount of energy used during each day is useful for capacity dimensioning of powerwalls and other home energy storage
	    # devices which should provide energy during the night (for example with PV panels).
        #
	    "diurnal-cycle": {
	        "cdf": "AVERAGE",
	        "xff": 0.5,
	        "interval": dt.timedelta(hours=24),
	        "duration": dt.timedelta(days=10 * 365)
	    },

        # Power dimensioning RRA
        #
        # The power dimensioning RRA stores MAX readout in one hour intervals for 365 days.
        # This data is useful for dimensioning of inverter power ratings required.
        #
        "power-dimensioning": {
            "cdf": "MAX",
            "xff": 0.5,
            "interval": dt.timedelta(hours=1),
            "duration": dt.timedelta(days=365)
        }
    },

    #
    # MQTT configuration
    #

    #
    # MQTT broker hostname
    #
    mqtt_broker=None,

    #
    # MQTT topic
    #
    mqtt_topic="energy/kWh",

    #
    # The fake pulse interval.
    # Fake pulses are generated in random intervals between [0, fake_pulse_interval] seconds.
    #
    fake_pulse_interval=5
)

def rrdtool_run(cmd):
    log.debug("Running rrdtool command '{}'".format(cmd))

    if not config.pretend:
        return os.system(cmd)
    else:
        return 0

def rrd_create(config):

    heartbeat = 2 * config.interval

    log.debug("RRD for source '{}' will use step is '{}' and heartbeat '{}'".format(config.ds_name, config.interval, heartbeat))

    # Data source
    ds_defstring = "DS:{}:ABSOLUTE:{}:{}:{}".format(config.ds_name, heartbeat.seconds, config.min, config.max)

    rra_defstrings = []
    for (rra_name, rra_def) in config.rra_defs.items():
        cdf = rra_def['cdf']
        interval = rra_def['interval']
        duration = rra_def['duration']
        xff = rra_def['xff']

        log.debug("RRA '{}' stores data in intervals of '{}' for '{}' (xff {})".format(rra_name, interval, duration, xff))

        rra_defstrings.append("RRA:{}:{}:{}:{}".format(cdf, xff, interval // config.interval, duration // config.interval))

    rrdtool_run( "rrdtool create {} '{}' -s '{}' '{}' {}".format("--start '{}'".format(config.start) if config.start else '' , args.rrdfile, config.interval.seconds, ds_defstring, ' '.join(rra_defstrings)) )

#
# Try to find the first Arduino serial port
#
def find_arduino_serial():
    try:
        (port, desc, hwid) = next(serial.tools.list_ports.grep("^Arduino"))
    except StopIteration:
        log.error("Could not detect an Arduino connected, please supply the serial port device manually")
        return None

    log.debug("Using first available port with an Arduion: {} (description '{}' hwid '{}')".format(port, desc, hwid))
    return port

def fake_pulse_source(config):
    i = 0

    while True:
        yield dict(ts=dt.datetime.now(dt.timezone.utc), i=i, info='SO pulse', usage=1)
        time.sleep(config.fake_pulse_interval * random.random())

        i += 1

def serial_pulse_source(config):

    if config.port is None:
        config.port=find_arduino_serial()

    log.info("Reading pulses from serial port '{}'".format(config.port))

    # Set the timeout so that it corresponds to the period
    with serial.Serial(config.port, config.bitrate, timeout=config.period.seconds // 2) as ser:

        while True:
            line = ser.readline().decode('ascii').rstrip()
            if len(line) == 0:
                continue

            log.debug("Serial read line: '{}'".format(line))
            yield dict(ts=dt.datetime.now(dt.timezone.utc), info=line, usage=1)


def measurement_loop(config, source):

    try:
        step_line = next( filter(lambda line: line.startswith("step = "), subprocess.getoutput("rrdtool info '{}'".format(config.rrdfile)).split("\n")) )
        period = dt.timedelta(seconds=int(re.match("step\s*=\s*(\d+)", step_line).group(1)))
    except:
        # Use the period value from the configuration
        period = config.interval

    config.period = period

    log.info("Reading pulses from '{}' with integration period '{}', quantum '{}' and storing to RRD database '{}'".format(args.port, period, args.quantum, args.rrdfile))

    while True:
        period_start = dt.datetime.now(dt.timezone.utc)
        log.debug("Period start '{}'".format(period_start.isoformat()))
        pulse_count = 0

        period = config.interval
        prev_ts = None
        while dt.datetime.now(dt.timezone.utc) - period_start < period:
            pulse = next(source)

            log.debug("from source '{}'".format(pulse))
            if pulse['info'] == "SO pulse":
                pulse_count += 1

                ts = pulse['ts']

                pulse['usage'] = dict(value=pulse['usage'] * config.quantum, unit=config.resource_unit)
                if prev_ts:
                    rate = ureg.parse_expression("({} {}) / ({} s)".format(
                        config.quantum, config.resource_unit, (ts - prev_ts).total_seconds())
                    )
                    pulse['rate'] = dict(value=round(rate.m_as(config.rate_unit), 3), unit=config.rate_unit)

                if mqtt_client:
                    pulse['ts'] = pulse['ts'].isoformat() # TypeError: Object of type datetime is not JSON serializable
                    log.debug("Sending to MQTT topic '{}': {}'".format(config.mqtt_topic, json.dumps(pulse)))
                    mqtt_client.publish(os.path.join(config.mqtt_topic,'pulse'), qos=1, payload=json.dumps(pulse))

                prev_ts = ts

        period_end = dt.datetime.now(dt.timezone.utc)
        log.debug("PERIOD '{}' -> '{}' (duration {}) had '{}' pulses".format(period_start.isoformat(), period_end.isoformat(), period_end - period_start, pulse_count))

        rrdtool_run("rrdtool update '{}' 'N@{}'".format(config.rrdfile, pulse_count * config.quantum))

        if mqtt_client:
            mqtt_client.publish(os.path.join(config.mqtt_topic,'summary'), qos=1, payload=json.dumps(
                dict(period_begin=period_start.isoformat(), period_end=period_end.isoformat(),
                    usage={ 'value': pulse_count * config.quantum, 'unit': config.resource_unit})
            ))

    return 1

def mqtt_loop(config):
    mqtt_client.loop_forever(retry_first_connection=True)

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Process SO pulses and store readings in an rrd database")
    parser.add_argument("--loglevel", default=config.loglevel, help="Log level")
    parser.add_argument("--pretend", action="store_true", default=config.pretend, help="Pretend to update information in RRD")

    subparsers = parser.add_subparsers(dest="command", help="sub-commands help")

    parser_m = subparsers.add_parser("measure", help="Measure pulses and store in RRD")
    parser_m.add_argument("-p", "--port", metavar="DEV", help="The serial port that connects to the SObasic module")
    parser_m.add_argument("-b", "--bitrate", metavar="BPS", default=config.bitrate, type=int, help="The bitrate of the serial port")
    parser_m.add_argument("-r", "--rrdfile", metavar="RRDFILE", required=True, help="The RRD database file")
    parser_m.add_argument("-q", "--quantum", metavar="QUANTUM", type=float, default=config.quantum, help="The amount of measured resource (energy/water/gas) consumed for each pulse. The amount of pulses will be multipled by this value before storing in RRD")
    parser_m.add_argument("--resource-unit", metavar="UNIT", default=config.resource_unit, help="The unit of the measured resource (Wh, kWh, m^3, etc.)")
    parser_m.add_argument("--rate-unit", metavar="UNIT", default=config.rate_unit, help="The unit of the reported resource consumption rate (W, liters/s, etc.)")
    parser_m.add_argument("-i", "--interval", metavar="SEC", type=float, default=config.interval, help="The interval is the time during all pulses are counted as a single energy usage value.")
    parser_m.add_argument("--mqtt-broker", metavar="NAME", help="Send data to specified MQTT broker URL")
    parser_m.add_argument("--mqtt-topic", metavar="TOPIC", default=config.mqtt_topic, help="Set MQTT topic")
    parser_m.add_argument("--fake-pulses", action='store_true', default=False, help="Generate fake pulses instead of reading them from the serial port")

    parser_c = subparsers.add_parser("create", help="Create the SObasic RRD database")
    parser_c.add_argument("-r", "--rrdfile", metavar="RRDFILE", required=True, help="The RRD database file")
    parser_c.add_argument("--start", metavar="UNIX_TIMESTAMP", help="The start timestamp for the RRD database")

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

    if args.command == "create":
        sys.exit(rrd_create(config))
    elif args.command == "measure":
        sys.exit(measurement_loop(config, source))
    else:
        log.fatal("Unknown command '{}'".format(args.command))
        sys.exit(1)

    sys.exit(0)
