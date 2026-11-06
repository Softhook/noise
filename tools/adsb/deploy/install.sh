#!/bin/sh
# Install or update the ADS-B logger on the Pi. Safe to run again: it never overwrites the
# site config and never touches the logs.
#
#   sudo sh deploy/install.sh                    # the logger, status page and watchdog
#   sudo sh deploy/install.sh --watchdog         # also install the watchdog daemon, which checks the SSD
#   sudo sh deploy/install.sh --gps              # also set up gpsd and chrony for the GPS clock
#   sudo sh deploy/install.sh --hotspot          # also make the Pi's own Wi-Fi, and a cable fallback
#   sudo sh deploy/install.sh --graphs           # also install graphs1090, for tuning the gain in the trial
#
# Usually run from the laptop with `make pi-deploy` (ARGS="--watchdog --gps --hotspot"), which
# copies this folder to the Pi first. Those and --graphs need internet, so run them at home.
# readsb is installed separately first; see docs/pi-setup.md.
set -eu

APP_DIR=/opt/adsb-logger
CONF=/etc/adsb-logger/site.json
LOG_DIR=/var/lib/adsb-logger
SERVICE_USER=adsb-logger

say() { echo "==> $*"; }
warn() { echo "WARNING: $*" >&2; WARNED=1; }
WARNED=0

cd "$(dirname "$0")/.."
[ -f adsb/__main__.py ] || { echo "Can't find the adsb package next to deploy/" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo: sudo sh deploy/install.sh" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' \
    || { echo "Needs Python 3.9 or later" >&2; exit 1; }

setup_gps() {
    say "GPS clock"
    apt-get install -y gpsd chrony

    # A stable name for the receiver, so it survives other USB devices being plugged in.
    # Prefer one that names itself as a GPS, in case another serial device is plugged in.
    device=$(ls /dev/serial/by-id/* 2>/dev/null | grep -i -E 'gps|gnss|u-blox|ublox' | head -n 1 || true)
    [ -n "$device" ] || device=$(ls /dev/serial/by-id/* 2>/dev/null | head -n 1 || true)
    [ -n "$device" ] || device=$(ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -n 1 || true)
    if [ "$(ls /dev/serial/by-id/ 2>/dev/null | wc -l)" -gt 1 ]; then
        warn "Several serial devices; using $device. Check it's the GPS: ls /dev/serial/by-id/"
    fi
    if [ -n "$device" ]; then
        say "GPS receiver: $device"
        touch /etc/default/gpsd
        sed -i '/^DEVICES=/d; /^GPSD_OPTIONS=/d' /etc/default/gpsd
        printf 'DEVICES="%s"\nGPSD_OPTIONS="-n"\n' "$device" >> /etc/default/gpsd
    else
        warn "No GPS receiver found. Plug it in and run this again with --gps."
    fi

    mkdir -p /etc/chrony/conf.d
    cat > /etc/chrony/conf.d/gps.conf <<'EOF'
# Written by tools/adsb/deploy/install.sh
refclock SHM 0 refid GPS precision 1e-1 offset 0.0 delay 0.2
# Step the clock whenever it's wrong, not just at boot: the Pi has no battery-backed clock
makestep 1 -1
EOF
    # Debian's chrony.conf sets "makestep 1 3" after reading conf.d, which would override ours
    sed -i 's/^makestep/# makestep (see conf.d\/gps.conf)/' /etc/chrony/chrony.conf
    grep -q '^confdir /etc/chrony/conf.d' /etc/chrony/chrony.conf \
        || echo 'confdir /etc/chrony/conf.d' >> /etc/chrony/chrony.conf

    systemctl enable gpsd
    systemctl restart gpsd chrony
}

setup_cable() {
    # The fallback when the hotspot fails: a laptop on a cable straight to the Pi. The usual wired
    # connection asks for an address by DHCP, and with no DHCP server it gives up without one. This
    # ranks below it, so it's only tried then, and gives the Pi a 169.254 address, as the laptop
    # gives itself. It never hands out addresses, so it's harmless on any network.
    say "Cable fallback"
    if nmcli -t -f NAME connection show | grep -qx adsb-cable; then
        say "Already set up, so unchanged."
        return
    fi
    nmcli connection add type ethernet ifname eth0 con-name adsb-cable \
        autoconnect yes connection.autoconnect-priority -10 \
        ipv4.method link-local ipv6.method link-local >/dev/null
}

setup_hotspot() {
    # The Pi's own Wi-Fi, for site visits: the garden has no network. It ranks below any Wi-Fi the
    # Pi already knows, so at home the Pi joins the home network, and elsewhere starts this.
    command -v nmcli >/dev/null || { warn "No NetworkManager (nmcli), so no hotspot."; return; }
    setup_cable
    say "Wi-Fi hotspot"
    if nmcli -t -f NAME connection show | grep -qx adsb-hotspot; then
        say "Already set up, so unchanged."
        return
    fi
    apt-get install -y dnsmasq-base  # Hands out addresses to phones and laptops that join
    password=$(python3 -c 'import secrets; print(secrets.token_urlsafe(9))')
    # WPA2 with CCMP only, and pmf 1 (off): some phones won't join the Pi's Wi-Fi otherwise
    nmcli connection add type wifi ifname wlan0 con-name adsb-hotspot ssid "$(hostname)" \
        autoconnect yes connection.autoconnect-priority -10 \
        802-11-wireless.mode ap 802-11-wireless.band bg \
        ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method ignore \
        wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp \
        wifi-sec.pmf 1 wifi-sec.psk "$password" >/dev/null
    case "$(iw reg get 2>/dev/null | sed -n 's/^country \([A-Z][A-Z]\).*/\1/p' | head -n 1)" in
        ""|00) warn "No Wi-Fi country is set, so the hotspot won't start: sudo raspi-config nonint do_wifi_country GB" ;;
    esac
}

setup_graphs() {
    # graphs1090, by readsb's author: graphs of signal, gain and message rates, at /graphs1090/.
    # Keeps its data in memory and writes it to disk once a day. For the trial; remove
    # it afterwards with: sudo bash /usr/share/graphs1090/uninstall.sh
    say "graphs1090"
    if [ -d /usr/share/graphs1090 ]; then
        say "Already installed, so unchanged."
        return
    fi
    script=$(mktemp)
    curl -fsSL -o "$script" https://github.com/wiedehopf/graphs1090/raw/master/install.sh \
        || { warn "Couldn't download the graphs1090 installer."; rm -f "$script"; return; }
    bash "$script" || warn "The graphs1090 installer failed; see above."
    rm -f "$script"
}

setup_watchdog() {
    # The Pi's hardware watchdog reboots it if nothing tells it the system is alive for 15 s.
    # The Pi boots from the SSD, so if the SSD resets or goes read-only, the whole system is stuck
    # and only a reboot can bring the disk back. The watchdog daemon (from --watchdog) checks the
    # disk with deploy/disk-check.sh, and reboots if it fails for 3 minutes or hangs for 1. It runs
    # locked in memory, so it keeps working when the disk doesn't. Without the daemon, systemd
    # feeds the watchdog itself, which only catches a hung kernel or systemd.
    say "Watchdog"
    if [ ! -e /dev/watchdog ]; then
        warn "No /dev/watchdog, so a hung Pi won't reboot by itself. Add dtparam=watchdog=on to /boot/firmware/config.txt"
        return
    fi
    dropin=/etc/systemd/system.conf.d/adsb-watchdog.conf
    if [ "$DO_WATCHDOG" -eq 1 ] && ! command -v watchdog >/dev/null; then
        apt-get install -y watchdog
    fi
    if command -v watchdog >/dev/null; then
        # Only one program can feed /dev/watchdog, so systemd stops doing it first
        if [ -f "$dropin" ]; then
            rm -f "$dropin"
            systemctl daemon-reexec
        fi
        cat > /etc/watchdog.conf <<'CONF'
# Written by tools/adsb/deploy/install.sh; see docs/pi-setup.md
watchdog-device = /dev/watchdog
watchdog-timeout = 15
interval = 5
# Locked in memory and at high priority, so it keeps running when the disk has failed
realtime = yes
priority = 1
# Writes and syncs a small file on the SSD once a minute. Reboot if that fails for 180 s, or hangs for 60 s.
test-binary = /opt/adsb-logger/disk-check.sh
test-timeout = 60
retry-timeout = 180
CONF
        systemctl enable watchdog >/dev/null 2>&1
        systemctl restart watchdog
        say "Watchdog daemon checking the SSD"
    else
        mkdir -p /etc/systemd/system.conf.d
        new=$(mktemp)
        printf '# Written by tools/adsb/deploy/install.sh\n[Manager]\nRuntimeWatchdogSec=14s\nRebootWatchdogSec=2min\n' > "$new"
        if cmp -s "$new" "$dropin"; then
            rm -f "$new"
        else
            mv "$new" "$dropin"
            chmod 644 "$dropin"
            systemctl daemon-reexec
        fi
        warn "A failed SSD won't reboot the Pi, only a hung kernel. Run make pi-deploy ARGS=--watchdog at home."
    fi
}

limit_journal() {
    # The journal shares the SSD with the logs. Keep it, so a crash or watchdog reboot can be
    # looked into afterwards, but capped.
    say "System journal capped at 200 MB"
    mkdir -p /etc/systemd/journald.conf.d
    printf '# Written by tools/adsb/deploy/install.sh\n[Journal]\nSystemMaxUse=200M\n' \
        > /etc/systemd/journald.conf.d/adsb.conf
    systemctl restart systemd-journald
}

DO_WATCHDOG=0
DO_GPS=0
DO_HOTSPOT=0
DO_GRAPHS=0
for arg in "$@"; do
    case "$arg" in
        --watchdog) DO_WATCHDOG=1 ;;
        --gps) DO_GPS=1 ;;
        --hotspot) DO_HOTSPOT=1 ;;
        --graphs) DO_GRAPHS=1 ;;
        *) echo "usage: sudo sh deploy/install.sh [--watchdog] [--gps] [--hotspot] [--graphs]" >&2; exit 2 ;;
    esac
done
[ "$DO_WATCHDOG$DO_GPS$DO_HOTSPOT" = 000 ] || apt-get update
[ "$DO_GPS" -eq 0 ] || setup_gps
[ "$DO_HOTSPOT" -eq 0 ] || setup_hotspot
[ "$DO_GRAPHS" -eq 0 ] || setup_graphs

say "Service user $SERVICE_USER"
id -u "$SERVICE_USER" >/dev/null 2>&1 \
    || useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
# The video group can read the throttling flags with vcgencmd
getent group video >/dev/null && usermod -aG video "$SERVICE_USER"

say "Code in $APP_DIR"
mkdir -p "$APP_DIR"
rm -rf "$APP_DIR/adsb.new"
cp -r adsb "$APP_DIR/adsb.new"
find "$APP_DIR/adsb.new" -name __pycache__ -prune -exec rm -rf {} +
rm -rf "$APP_DIR/adsb"
mv "$APP_DIR/adsb.new" "$APP_DIR/adsb"
python3 -m compileall -q "$APP_DIR/adsb"
install -m 755 deploy/check-log-disk.sh deploy/disk-check.sh "$APP_DIR/"
install -m 755 deploy/adsb /usr/local/bin/adsb

NEW_CONFIG=0
if [ ! -f "$CONF" ]; then
    say "New config $CONF"
    mkdir -p "$(dirname "$CONF")"
    install -m 644 site.example.json "$CONF"
    NEW_CONFIG=1
fi
python3 - "$CONF" <<'EOF' || WARNED=1
import json, sys
try:
    with open(sys.argv[1]) as f:
        site = json.load(f)["site"]
    lat, lon = float(site["lat"]), float(site["lon"])
except (OSError, ValueError, KeyError, TypeError) as error:
    sys.exit(f"WARNING: {sys.argv[1]} is unreadable or has no site lat/lon: {error}")
if (lat, lon) == (51.5, 0.1):
    sys.exit(f"WARNING: {sys.argv[1]} still has the placeholder location. Set the garden's real one.")
EOF

say "Log folder $LOG_DIR"
# A folder on the SSD the Pi boots from. The logger's service gives it to $SERVICE_USER each time
# it starts, and refuses to start if it's on an SD card.
mkdir -p "$LOG_DIR"
source=$(findmnt -n -o SOURCE --target "$LOG_DIR" 2>/dev/null || true)
case "$source" in
    /dev/mmcblk*) warn "The Pi booted from an SD card ($source), not the SSD, so the logger won't run. Remove the SD card and reboot (see docs/pi-setup.md)." ;;
esac

if [ -f /etc/default/readsb ]; then
    readsb_options=$(grep -v '^[[:space:]]*#' /etc/default/readsb)
    echo "$readsb_options" | grep -q -- '--net-json-port' \
        || warn "readsb has no --net-json-port in /etc/default/readsb, so the logger has nothing to read."
    if ! echo "$readsb_options" | grep -q -- '--db-file' \
        || echo "$readsb_options" | grep -q -E -- '--db-file[= ]+none'; then
        warn "readsb has no --db-file, so aircraft types and registrations won't be logged."
    fi
    # readsb's default, 2, gives tar1090 (and anyone on the network) the garden's exact location.
    # 1 rounds it to about 1 km. 0 and 4 round readsb's own copy to whole degrees, too coarse for decoding.
    accuracy=$(echo "$readsb_options" | grep -o -E -- '--json-location-accuracy[= ]+[0-9]+' \
        | tail -n 1 | grep -o -E '[0-9]+$' || true)
    case "$accuracy" in
        1 | 3) ;;
        *) warn "readsb publishes the garden's exact location to tar1090. Set --json-location-accuracy 1 in /etc/default/readsb (see docs/pi-setup.md)." ;;
    esac
else
    warn "readsb isn't installed (no /etc/default/readsb)."
fi

setup_watchdog
limit_journal

say "Logger service and status page"
install -m 644 deploy/adsb-logger.service deploy/adsb-status.service deploy/adsb-status.timer \
    /etc/systemd/system/
systemctl daemon-reload
# A new config still has the placeholder location, so the logger is turned on by make pi-config
[ "$NEW_CONFIG" -eq 1 ] || systemctl enable adsb-logger
systemctl enable --now adsb-status.timer
if [ -d /etc/lighttpd/conf-enabled ]; then
    install -m 644 deploy/lighttpd-adsb-status.conf /etc/lighttpd/conf-available/89-adsb-status.conf
    ln -sf ../conf-available/89-adsb-status.conf /etc/lighttpd/conf-enabled/89-adsb-status.conf
    if lighttpd -tt -f /etc/lighttpd/lighttpd.conf >/dev/null; then
        systemctl restart lighttpd
        say "Status page: http://$(hostname).local/adsb-status/"
    else
        rm -f /etc/lighttpd/conf-enabled/89-adsb-status.conf
        warn "lighttpd didn't accept the status page config, so it's turned off. The map is unaffected."
    fi
else
    warn "No lighttpd (it comes with tar1090), so there's no status page. 'adsb status' still works."
fi

echo
if [ "$NEW_CONFIG" -eq 1 ]; then
    echo "Next: set the garden's location with 'make pi-config' on the laptop, which starts the logger."
else
    systemctl restart adsb-logger
    echo "Logger (re)started. Follow it with 'make pi-journal' on the laptop."
fi
if [ "$DO_HOTSPOT" -eq 1 ]; then
    echo "Hotspot: Wi-Fi network $(hostname), password" \
        "$(nmcli -s -g 802-11-wireless-security.psk connection show adsb-hotspot)," \
        "status page http://10.42.0.1/adsb-status/"
fi
[ "$WARNED" -eq 0 ] || echo "Finished, with warnings above."
