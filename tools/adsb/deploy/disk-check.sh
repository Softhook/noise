#!/bin/sh
# Run by the watchdog daemon every few seconds (see install.sh --watchdog). Once a minute it writes
# and syncs a small file on the SSD. If that fails for 3 minutes, or hangs for 1, the watchdog
# reboots the Pi: with the system on the SSD, a USB reset or a read-only disk can't be fixed
# any other way, and a reboot usually brings the disk back. Exit 0 means the disk is fine.
STAMP=/run/adsb-disk-check  # In memory
PROBE=/var/lib/adsb-logger/.disk-check
now=$(date +%s)
last=$(cat "$STAMP" 2>/dev/null || echo 0)
[ $((now - last)) -lt 60 ] && exit 0
printf '%s\n' "$now" > "$PROBE.tmp" && sync "$PROBE.tmp" && mv "$PROBE.tmp" "$PROBE" || exit 1
echo "$now" > "$STAMP"
