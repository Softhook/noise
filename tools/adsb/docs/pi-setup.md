# Setting up the Pi

The Pi runs headless: no screen or keyboard, ever. You set it up at home over Wi-Fi, where it has internet, and run everything from a laptop with `make pi-*` commands in `tools/adsb`. The garden has no network, so there the Pi makes its own Wi-Fi hotspot. A phone can join it to see the status page, and a laptop can join it to copy the logs.

These steps come from the project documentation and haven't yet been run on our Pi.

| | At home (internet) | At the garden (no network) |
|---|---|---|
| Pi's address | `adsb-pi.local` | `10.42.0.1`, on the Pi's own Wi-Fi |
| Status page | `http://adsb-pi.local/adsb-status/` | `http://10.42.0.1/adsb-status/` |
| Laptop commands | `make pi-status` | `make pi-status PI=10.42.0.1` |

If your user name on the Pi differs from the laptop's, add it: `PI=pi@10.42.0.1`, or put a `Host` entry in `~/.ssh/config`.

## 1. First boot, without a screen

In [Raspberry Pi Imager](https://www.raspberrypi.com/software/), choose 64-bit Raspberry Pi OS Lite and open the OS customisation settings (Ctrl-Shift-X) before writing the card:

- hostname `adsb-pi`
- a user name and password
- your home Wi-Fi, with the Wi-Fi country set to GB (the hotspot won't start without a country)
- SSH on, with **public-key authentication only**, pasting your laptop's `~/.ssh/id_ed25519.pub`

Connect the stick, antenna, GPS receiver and SSD, and power it up. After a minute or two, `make pi-ssh` should log you in.

## 2. readsb and tar1090 (at home)

On the Pi (`make pi-ssh`). Steps 1 to 3 come from the readsb project. Read its install script before running it, because it runs as root and removes any other ADS-B decoder.

1. Install rsync (for `make pi-deploy` and `make pi-collect`), readsb and tar1090, then reboot:

   ```bash
   sudo apt-get install -y rsync
   sudo bash -c "$(wget -O - https://github.com/wiedehopf/adsb-scripts/raw/master/readsb-install.sh)"
   sudo reboot
   ```

2. Set the receiver location and automatic gain:

   ```bash
   sudo readsb-set-location <latitude> <longitude>
   sudo readsb-gain auto
   ```

3. Download a dated aircraft database from the [`csv` branch of tar1090-db](https://github.com/wiedehopf/tar1090-db/tree/csv). Keep that copy for the whole stage.

4. Edit `/etc/default/readsb`. Add the first option to `NET_OPTIONS` and the second to `DECODER_OPTIONS`. Keep what's already there:

   ```text
   --net-json-port 30154
   --db-file /path/to/aircraft-YYYY-MM-DD.csv.gz
   ```

   readsb only adds the type (`t`) and registration (`r`) when `--db-file` is set. We chose port 30154; any free port will do.

5. Restart readsb and check the stream:

   ```bash
   sudo systemctl restart readsb
   nc localhost 30154 | head
   ```

6. Open `http://adsb-pi.local/tar1090` to see the live map.

## 3. The SSD (at home)

The logs go on the SSD, mounted at `/var/lib/adsb-logger`. The logger won't start until it's mounted there, so it can't fill the SD card. Format the SSD once (this erases it; check the device name with `lsblk`):

```bash
sudo mkfs.ext4 -L adsb-logs /dev/sda1
sudo mkdir -p /var/lib/adsb-logger
echo 'LABEL=adsb-logs /var/lib/adsb-logger ext4 defaults,noatime,nofail 0 2' | sudo tee -a /etc/fstab
sudo systemctl daemon-reload && sudo mount /var/lib/adsb-logger
```

`nofail` matters: without it, a Pi with a missing or broken SSD stops at boot and can't be reached on site. If the SSD is missing or slow at boot, the logger keeps trying to mount it every 10 seconds, so plugging it back in is enough. It also gives a new or replaced SSD to the `adsb-logger` user itself.

## 4. The logger, GPS clock and hotspot (at home)

From `tools/adsb` on the laptop:

```bash
make pi-deploy ARGS="--gps --hotspot"
make pi-config       # set the garden's real location and ground height; restarts the logger
make pi-status
```

`pi-deploy` copies the code to `~/adsb-deploy` on the Pi and runs `deploy/install.sh` there with sudo. It never copies `site.json` or any logs. With `--hotspot`, it ends by printing the hotspot's name and password; note them down.

The install script is safe to run again. It never overwrites `site.json` and never touches the logs. It warns about anything it can't fix itself: the placeholder location, an unmounted SSD, an fstab entry without `nofail`, or readsb missing `--net-json-port` or `--db-file`. To update the code later, anywhere, run plain `make pi-deploy`, which restarts the logger. `--gps` and `--hotspot` need internet (they install packages), but only need running once.

It does the following:

- creates the `adsb-logger` system user, in the `video` group so it can read the throttling flags
- copies the `adsb` package to `/opt/adsb-logger`, and installs the `adsb` command
- copies `site.example.json` to `/etc/adsb-logger/site.json` if there's no config yet
- installs and enables `adsb-logger.service`, which restarts the logger whenever it stops
- installs `adsb-status.timer`, which writes the status page every minute, and adds it to the web server that came with tar1090

The whole `adsb` package is copied, but the logger only loads its Pi-side modules (`logger`, `status`, `health`, `geometry`).

### What `--hotspot` sets up

A NetworkManager connection, `adsb-hotspot`, that broadcasts a Wi-Fi network named after the Pi (`adsb-pi`), with WPA2 and a random password. The Pi is `10.42.0.1` on it, and hands out addresses to whatever joins. Nothing on it reaches the internet. Running `--hotspot` again leaves it as it is and prints the password again. To choose your own password, run `sudo nmcli connection modify adsb-hotspot wifi-sec.psk 'NEW PASSWORD'` on the Pi.

The hotspot has a lower priority than any Wi-Fi the Pi already knows. At home the Pi joins your home network as usual. At the garden, where no known network is in range, it starts the hotspot by itself at boot. To try the hotspot at home, run `sudo nmcli connection up adsb-hotspot` on the Pi. If you're connected over Wi-Fi, this drops your SSH session. Join the hotspot to check it, then power-cycle the Pi to put it back on your home network.

If the hotspot doesn't appear, a cable still works: connect the laptop straight to the Pi's Ethernet port and use `PI=adsb-pi.local`. This usually works over the link-local address that both ends give themselves.

### What `--gps` sets up

A Pi 4 has no battery-backed clock, so after a power cut it can't know the time until the GPS has a fix. This setup is a starting point that we still need to test. `--gps`:

- installs `gpsd` and `chrony`
- points gpsd at the receiver (by its `/dev/serial/by-id/` name, so it isn't confused by other USB devices, preferring one that names itself as a GPS) with `GPSD_OPTIONS="-n"`, so it reads the GPS even when no program is connected, and enables it at boot
- writes `/etc/chrony/conf.d/gps.conf`:

  ```text
  refclock SHM 0 refid GPS precision 1e-1 offset 0.0 delay 0.2
  makestep 1 -1
  ```

- comments out the `makestep 1 3` line in Debian's `/etc/chrony/chrony.conf`, which would otherwise override ours

`makestep 1 -1` lets chrony jump the clock at any time, so it corrects a wrong boot time straight away.

USB GPS receivers commonly lag by a few hundred milliseconds. That's within our 1 s target, so `offset 0.0` will do. For directivity or Doppler work, which needs 0.25 s, measure the lag: run the Pi with internet access for a few hours, compare the GPS source with internet time using `chronyc sourcestats`, and set `offset` to the difference. The GPS antenna needs a view of the sky.

Check the clock with `chronyc tracking` and `chronyc sources` (the GPS line should start `#*` once it's in use). The logger records the clock's state in its health log every 5 minutes.

## Status page

Open `http://10.42.0.1/adsb-status/` on the hotspot, or `http://adsb-pi.local/adsb-status/` at home. It shows the same report as `adsb status`, with any warnings at the top, and reloads every minute. It links to the live map at `/tar1090/`.

The page is written to `/run/adsb-status`, which is in memory, so it costs no disk writes and still works when the SSD is missing. Anyone on the same network can read it. It shows the logger's state, not the garden's location or the logs. If it's stale or missing, check the timer with `systemctl list-timers adsb-status` and `journalctl -u adsb-status`.

## On each site visit

1. Join the Pi's Wi-Fi (`adsb-pi`) with a phone, and open `http://10.42.0.1/adsb-status/`. For a quick check, that's all you need.
2. To collect data, join it with the laptop and, from `tools/adsb`:

   ```bash
   make pi-status PI=10.42.0.1
   make pi-collect PI=10.42.0.1
   ```

`adsb status`, and the status page, show when the logger last wrote, the clock's state, free disk space, temperature, power problems and how much data was kept in the last 24 hours. They warn if:

- the SSD isn't mounted
- the logger has stopped
- the clock isn't synchronised
- the disk is filling
- the Pi is overheating or short of power
- readsb keeps disconnecting
- nothing is being kept, which usually means the site location in the config is wrong

`adsb status` exits with code 1 when there are warnings. `make pi-status` also shows the logger's last journal lines; `make pi-journal` follows them live.

### Collecting the logs

`make pi-collect` copies the logs to `data/collected/` on the laptop (git ignores it; choose another folder with `COLLECT_DIR=...`). It does the following:

- checksums the files on the Pi
- copies only the new ones
- checks every copy against the Pi's SHA-256 checksum
- adds the checksums to `data/collected/SHA256SUMS`, which then lists every file collected so far

It prints `OK` or `FAILED`.

Files that may still be written to (the newest data file and today's health log) are left for the next visit, so every collected file is final. A file collected earlier is never overwritten. If the Pi's copy has changed, that's reported as a failure. Nothing is deleted from the Pi. Keep a second copy off site.

At the end of the survey, stop the logger first so its last files are closed, then collect everything:

```bash
make pi-ssh PI=10.42.0.1          # then: sudo systemctl stop adsb-logger
sh deploy/collect.sh --all 10.42.0.1
```
