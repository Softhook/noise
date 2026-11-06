#!/bin/sh
# Before the logger starts: make sure the log folder exists, is on the SSD rather than an SD card,
# and belongs to the logger. Run as root by adsb-logger.service; installed by install.sh.
#
# The Pi boots from the SSD, and the logs are a folder on it. If an SD card is left in, the Pi
# boots from that instead, and the logger would fill it, so it refuses to start.
set -u
DIR=/var/lib/adsb-logger
mkdir -p "$DIR"
source=$(findmnt -n -o SOURCE --target "$DIR" 2>/dev/null || true)
case "$source" in
    /dev/mmcblk*)
        echo "$DIR is on an SD card ($source), so the Pi didn't boot from the SSD. Remove the SD card and reboot."
        exit 1 ;;
esac
chown adsb-logger: "$DIR"
