#!/usr/bin/env bash

## Category: Googlefoo
## Shortdesc: Make a local mirror of all the libraries hosted on https://developers.google.com/speed/libraries/devguide for improved privacy

# Reference: http://robertmuth.blogspot.com/2012/08/better-bash-scripting-in-15-minutes.html
set -o nounset

# Configuration
readonly MIRROR_ROOT=${MIRROR_ROOT:="/var/www/ajax.googleapis.com/htdocs"}

# Resolve the source hostname independent of /etc/hosts
resolve() {
    local hostname="$1"; shift
    host "$hostname" | awk '/has address/ { print $4; }'
}

# FIXME: Calculate this from each URL on list
ajax_proto="https"
ajax_host="ajax.googleapis.com"
ajax_port="443"
ajax_ip=$(resolve "$ajax_host")


for url in $(googlehostedlibs-list.py); do
    local_path=${url##$ajax_proto://$ajax_host/}
    echo "-: --create-dirs -z '$MIRROR_ROOT/$local_path' -o '$MIRROR_ROOT/$local_path' --url '$url'"

# Need to manually set the IP to which ajax.googleapis.com should resolve to as we're changing it
# in /etc/hosts for the browser.

done | xargs curl --silent  --show-error --remote-time --resolve "$ajax_host:$ajax_port:$ajax_ip"

# Make the files readable by the world
find "$MIRROR_ROOT" -type f | xargs chmod a+r
find "$MIRROR_ROOT" -type d | xargs chmod a+rx
