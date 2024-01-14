#!/bin/sh
ffmpeg -i "${1}" -vn -ar 44100 -ac 2 -b:a 192k "${2}"
