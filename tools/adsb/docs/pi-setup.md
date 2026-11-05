# Setting up the Pi

These steps come from the project documentation and haven't yet been run on our Pi. Steps 1–3 come from the readsb project. Read the install script before running it, because it runs as root and removes any other ADS-B decoder.

1. Install 64-bit Raspberry Pi OS Lite, then connect the stick, antenna, GPS receiver and SSD.
2. Install readsb and tar1090:

   ```bash
   sudo bash -c "$(wget -O - https://github.com/wiedehopf/adsb-scripts/raw/master/readsb-install.sh)"
   sudo reboot
   ```

3. Set the receiver location and automatic gain:

   ```bash
   sudo readsb-set-location <latitude> <longitude>
   sudo readsb-gain auto
   ```

4. Download a dated aircraft database from the [`csv` branch of tar1090-db](https://github.com/wiedehopf/tar1090-db/tree/csv). Keep that copy for the whole stage.
5. Edit `/etc/default/readsb`. Add the first option to `NET_OPTIONS` and the second to `DECODER_OPTIONS`. Keep what's already there:

   ```text
   --net-json-port 30154
   --db-file /path/to/aircraft-YYYY-MM-DD.csv.gz
   ```

   readsb only adds the type (`t`) and registration (`r`) when `--db-file` is set. We chose port 30154; any free port will do.

6. Restart readsb and check the stream:

   ```bash
   sudo systemctl restart readsb
   nc localhost 30154 | head
   ```

7. Open `http://<pi-address>/tar1090` to see the live map.

## GPS clock

A Pi 4 has no battery-backed clock, so after a power cut it can't know the time until the GPS has a fix. This setup is a starting point that we still need to test.

```bash
sudo apt install gpsd chrony
```

In `/etc/default/gpsd`, check the device name with `ls /dev/ttyACM* /dev/ttyUSB*`:

```text
DEVICES="/dev/ttyACM0"
GPSD_OPTIONS="-n"
```

Create `/etc/chrony/conf.d/gps.conf`:

```text
refclock SHM 0 refid GPS precision 1e-1 offset 0.0 delay 0.2
makestep 1 -1
```

`makestep 1 -1` lets chrony jump the clock at any time, so it corrects a wrong boot time straight away.

USB GPS receivers commonly lag by a few hundred milliseconds. That's within our 1 s target, so `offset 0.0` will do. For directivity or Doppler work, which needs 0.25 s, measure the lag: run the Pi with internet access for a few hours, compare the GPS source with internet time using `chronyc sourcestats`, and set `offset` to the difference. The GPS antenna needs a view of the sky.

Check the clock with `chronyc tracking`. The logger records this in its health log every 5 minutes.


## Logger

The SSD should be mounted at `/var/lib/adsb-logger`. The service won't start without it, rather than filling the SD card.

From `tools/adsb` in a copy of this repository on the Pi:

```bash
sudo useradd --system --no-create-home adsb-logger
sudo usermod -aG video adsb-logger              # so it can read throttling flags
sudo mkdir -p /opt/adsb-logger /etc/adsb-logger
sudo chown adsb-logger /var/lib/adsb-logger
sudo rm -rf /opt/adsb-logger/adsb && sudo cp -r adsb /opt/adsb-logger/
sudo install -m 755 deploy/adsb /usr/local/bin/adsb
sudo cp site.example.json /etc/adsb-logger/site.json
sudo nano /etc/adsb-logger/site.json            # the garden's real location and ground height
sudo cp deploy/adsb-logger.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now adsb-logger
journalctl -u adsb-logger -f
```

The whole `adsb` package is copied, but the logger only loads its Pi-side modules (`logger`, `status`, `health`, `geometry`). To update the code, repeat the `cp -r` line and run `sudo systemctl restart adsb-logger`.

## On each site visit

```bash
adsb status
```

This shows when the logger last wrote, the clock's state, free disk space, temperature, power problems and how much data was kept in the last 24 hours. It warns if:

- the logger has stopped
- the clock isn't synchronised
- the disk is filling
- the Pi is overheating or short of power
- readsb keeps disconnecting
- nothing is being kept, which usually means the site location in the config is wrong

It exits with code 1 when there are warnings.
