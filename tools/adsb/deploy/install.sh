#!/bin/sh
# Install or update the ADS-B logger on the Pi. Safe to run again: it never overwrites the
# site config and never touches the logs.
#
#   sudo sh deploy/install.sh                    # the logger and status page
#   sudo sh deploy/install.sh --gps              # also set up gpsd and chrony for the GPS clock
#   sudo sh deploy/install.sh --hotspot          # also make the Pi's own Wi-Fi for site visits
#
# Usually run from the laptop with `make pi-deploy` (ARGS="--gps --hotspot"), which copies this
# folder to the Pi first. --gps and --hotspot need internet, so run them at home.
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

setup_hotspot() {
    # The Pi's own Wi-Fi, for site visits: the garden has no network. It ranks below any Wi-Fi the
    # Pi already knows, so at home the Pi joins the home network, and elsewhere starts this.
    say "Wi-Fi hotspot"
    command -v nmcli >/dev/null || { warn "No NetworkManager (nmcli), so no hotspot."; return; }
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

DO_GPS=0
DO_HOTSPOT=0
for arg in "$@"; do
    case "$arg" in
        --gps) DO_GPS=1 ;;
        --hotspot) DO_HOTSPOT=1 ;;
        *) echo "usage: sudo sh deploy/install.sh [--gps] [--hotspot]" >&2; exit 2 ;;
    esac
done
[ "$DO_GPS$DO_HOTSPOT" = 00 ] || apt-get update
[ "$DO_GPS" -eq 0 ] || setup_gps
[ "$DO_HOTSPOT" -eq 0 ] || setup_hotspot

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
# The logger's service mounts the SSD and gives it to $SERVICE_USER each time it starts
mkdir -p "$LOG_DIR"
mountpoint -q "$LOG_DIR" \
    || warn "$LOG_DIR is not a mounted disk. The logger will wait until the SSD is mounted there (see docs/pi-setup.md)."
options=$(findmnt --fstab -n -o OPTIONS "$LOG_DIR" 2>/dev/null || true)
case ",$options," in
    ,,) ;;
    *,nofail,*) ;;
    *) warn "The /etc/fstab entry for $LOG_DIR has no 'nofail', so the Pi won't boot without the SSD." ;;
esac

if [ -f /etc/default/readsb ]; then
    readsb_options=$(grep -v '^[[:space:]]*#' /etc/default/readsb)
    echo "$readsb_options" | grep -q -- '--net-json-port' \
        || warn "readsb has no --net-json-port in /etc/default/readsb, so the logger has nothing to read."
    if ! echo "$readsb_options" | grep -q -- '--db-file' \
        || echo "$readsb_options" | grep -q -E -- '--db-file[= ]+none'; then
        warn "readsb has no --db-file, so aircraft types and registrations won't be logged."
    fi
else
    warn "readsb isn't installed (no /etc/default/readsb)."
fi

say "Logger service and status page"
install -m 644 deploy/adsb-logger.service deploy/adsb-status.service deploy/adsb-status.timer \
    /etc/systemd/system/
systemctl daemon-reload
systemctl enable adsb-logger
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
