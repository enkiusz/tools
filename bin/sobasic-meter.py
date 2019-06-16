#!/usr/bin/env python3

#
# Copyright 2018 Maciej Grela <enki@fsck.pl>
# SPDX-License-Identifier: WTFPL
#
# Host script for reading pulses from SObasic Arduino interface and storing them into an RRD database.
# All should be obvious after running SObasic-meter.py --help
#

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
    # The amount of pulses will be multipled by this value before storing in RRD
    quantum=1.0,

    # Both min and max values are not limited (-Inf .. +Inf) to allow for bidirectional flow (like in net energy metering).
    min="U",
    max="U",

    rra_defs={
        # Prediction RRA
        #
        # This RRA stores LAST readout in one step intervals for 30 days. This is basically the raw data gathered by the meter.
        #
        # It's possible use is load prediction and general graphing of short-term data.
        #
        "prediction": {
            "cdf": "AVERAGE",
            "xff": 0.5,
            "interval": dt.timedelta(seconds=30),
            "duration": dt.timedelta(days=30)
        },

        # System dimensioning RRA
        #
        # The system dimensioning RRA stores MAX readout in one hour intervals for 365 days.
        # This data is useful for dimensioning of backup power or solar inverters max kW ratings
        "dimensioning": {
            "cdf": "MAX",
            "xff": 0.5,
            "interval": dt.timedelta(hours=1),
            "duration": dt.timedelta(days=365)
        }
    }
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

    rrdtool_run( "rrdtool create '{}' -s '{}' '{}' {}".format(args.rrdfile, config.step.seconds, ds_defstring, ' '.join(rra_defstrings)) )

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


def measurement_loop(config):

    if config.port is None:
        config.port=find_arduino_serial()

    try:
        step_line = next( filter(lambda line: line.startswith("step = "), subprocess.getoutput("rrdtool info '{}'".format(config.rrdfile)).split("\n")) )
        period = dt.timedelta(seconds=int(re.match("step\s*=\s*(\d+)", step_line).group(1)))
    except:
        # Use the period value from the configuration
        period = config.interval

    log.info("Reading pulses from '{}' with integration period '{}', quantum '{}' and storing to RRD database '{}'".format(args.port, period, args.quantum, args.rrdfile))

    # Set the timeout so that it corresponds to the period
    with serial.Serial(args.port, args.bitrate, timeout=period.seconds // 2) as ser:

        while True:
            period_start = dt.datetime.now()
            log.debug("Period start '{}'".format(period_start))
            pulse_count = 0

            while dt.datetime.now() - period_start < period:
                line = ser.readline().decode('ascii').rstrip()
                log.debug("READ: '{}'".format(line))
                if line == "SO pulse":
                    pulse_count += 1

            period_end = dt.datetime.now()
            log.debug("PERIOD '{}' -> '{}' (duration {}) had '{}' pulses".format(period_start, period_end, period_end - period_start, pulse_count))

            rrdtool_run("rrdtool update '{}' 'N@{}'".format(config.rrdfile, pulse_count * config.quantum))
    return 0

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
    parser_m.add_argument("-i", "--interval", metavar="SEC", type=float, default=config.interval, help="The interval is the time during all pulses are counted as a single energy usage value.")

    parser_c = subparsers.add_parser("create", help="Create the SObasic RRD database")
    parser_c.add_argument("-r", "--rrdfile", metavar="RRDFILE", required=True, help="The RRD database file")

    args = parser.parse_args()
    config.__dict__.update(vars(args))

    logging.basicConfig(level=getattr(logging, config.loglevel))

    log.debug("Configuration dump: {}".format(config))

    if args.command == "create":
        sys.exit(rrd_create(config))
    elif args.command == "measure":
        sys.exit(measurement_loop(config))
    else:
        log.fatal("Unknown command '{}'".format(args.command))
        sys.exit(1)

    sys.exit(0)
