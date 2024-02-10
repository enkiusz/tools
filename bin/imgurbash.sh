#!/usr/bin/env bash

## Category: Various
## Shortdesc: Upload scripts to imgur (from Bart Nagel <bart@tremby.net>)

# imgur script by Bart Nagel <bart@tremby.net>
# version 4
# I release this into the public domain. Do with it what you will.

# Changes by Maciej Grela <enki@fsck.pl>
# The changes are also in the public domain.
# - Remove image metadata before uploading

# Required: curl
#
# Optional: xsel or xclip for automatically putting the URLs on the X selection
# for easy pasting
#
# Instructions:
# Put it somewhere in your path and maybe rename it:
# 	mv ~/Downloads/imgurbash.sh ~/bin/imgur
# Make it executable:
# 	chmod +x ~/bin/imgur
# Optional, since Alan kindly provided an API key for this script: stick your
# API key in the top:
# 	vim ~/bin/imgur
# Upload an image:
# 	imgur images/hilarious/manfallingover.jpg
# Upload multiple images:
# 	imgur images/delicious/cake.png images/exciting/bungeejump.jpg
# The URLs will be displayed (and the delete page's URLs will be displayed on
# stderr). If you have xsel or xclip the URLs will also be put on the X
# selection, which you can usually paste with a middle click.

# From: https://github.com/Ceryn/img/blob/master/img.sh
clientid=3e7a4deb7ac67da

# function to output usage instructions
function usage {
	echo "Usage: $(basename $0) <filename> [<filename> [...]]" >&2
	echo "Upload images to imgur and output their new URLs to stdout. Each one's" >&2
	echo "delete page is output to stderr between the view URLs." >&2
	echo "If xsel or xclip is available, the URLs are put on the X selection for" >&2
	echo "easy pasting." >&2
	echo "Note: If the exiv2 tool is available in $PATH, all image metadata is removed before uploading" >&2
}

# check API key has been entered
if [ "$apikey" = "Your API key" ]; then
	echo "You first need to edit the script and put your API key in the variable near the top." >&2
	exit 15
fi

# check arguments
if [ "$1" = "-h" -o "$1" = "--help" ]; then
	usage
	exit 0
elif [ $# == 0 ]; then
	echo "No file specified" >&2
	usage
	exit 16
fi

# check if curl is available
type curl >/dev/null 2>/dev/null || {
	echo "Couln't find curl, which is required." >&2
	exit 17
}

# check if jq is available
type jq >/dev/null 2>/dev/null || {
	  echo "Couln't find jq, which is required." >&2
	  exit 17
}

type exiv2 >/dev/null 2>/dev/null && {
    echo "Found exiv2, metadata will be stripped before upload" >&2
    strip_metadata=true
}

upload() {
    local file="$1"
    curl -sH "Authorization: Client-ID $clientid" -F "image=@$file" "https://api.imgur.com/3/upload"
}

while [ "$1" ]; do
    filename="$1"; shift
    echo "Uploading '$filename'" >&2

    if [ "$strip_metadata" == "true" ]; then
        # Copy image and strip metadata

        tempfile=$(mktemp)
        cp $filename $tempfile
        echo "Stripping metadata from file '$filename'" >&2
        exiv2 --delete a $tempfile

        response=$(upload "$tempfile")
        rm "$tempfile"
    else

        response=$(upload "$tempfile")
    fi

    if [ "$(jq .success <<<$response )" != "true" ]; then
        echo "Could not upload '$filename', result:" >&2
        echo "$response"
        continue
    fi

    echo "$filename" $(jq -r .data.link <<<"$response" ) https://imgur.com/delete/$(jq -r .data.deletehash <<<"$response" )

done

