# Setting up the Pi

The Pi runs headless: no screen or keyboard, ever. You set it up at home over Wi-Fi, where it has internet, and run everything from a laptop with `make pi-*` commands in `tools/adsb`. The garden has no network, so there the Pi makes its own Wi-Fi hotspot. A phone can join it to see the status page, and a laptop can join it to copy the logs.

These steps come from the project documentation and haven't yet been run on our Pi.

| | At home (internet) | At the garden (no network) |
|---|---|---|
| Pi's address | `adsb-pi.local` | `10.42.0.1`, on the Pi's own Wi-Fi |
| Status page | `http://adsb-pi.local/adsb-status/` | `http://10.42.0.1/adsb-status/` |
| Laptop commands | `make pi-status` | `make pi-status PI=10.42.0.1` |

If your user name on the Pi differs from the laptop's, add it: `PI=pi@10.42.0.1`, or put a `Host` entry in `~/.ssh/config`. `10.42.0.1` is every NetworkManager hotspot's default address, so tell ssh it's the same Pi under both names. Otherwise it refuses to connect when another device has used that address:

```text
Host adsb-pi.local 10.42.0.1
    HostKeyAlias adsb-pi
```

## 1. First boot, without a screen

The Pi boots from the USB SSD, with no SD card. Pi 4s made since 2020 try USB after the SD card slot. An older one needs its bootloader updated once: in Raspberry Pi Imager, write *Misc utility images > Bootloader > USB Boot* to a spare SD card, boot the Pi from it until the green light flashes steadily, then remove the card.

Connect the SSD to the laptop. In [Raspberry Pi Imager](https://www.raspberrypi.com/software/), choose 64-bit Raspberry Pi OS Lite and the SSD as the storage, and open the OS customisation settings (Ctrl-Shift-X) before writing it:

- hostname `adsb-pi`
- a user name and password
- your home Wi-Fi, with the Wi-Fi country set to GB (the hotspot won't start without a country)
- SSH on, with **public-key authentication only**, pasting your laptop's `~/.ssh/id_ed25519.pub`

Connect the SSD (to a blue USB 3 port), the stick, antenna and GPS receiver, with no SD card in, and power it up. After a minute or two, `make pi-ssh` should log you in.

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

4. Edit `/etc/default/readsb`. Add the first option to `NET_OPTIONS` and the second to `DECODER_OPTIONS`. In `JSON_OPTIONS`, change `--json-location-accuracy 2` to `1`. Keep everything else that's there:

   ```text
   NET_OPTIONS="... --net-json-port 30154"
   DECODER_OPTIONS="... --db-file /path/to/aircraft-YYYY-MM-DD.csv.gz"
   JSON_OPTIONS="--json-location-accuracy 1 ..."
   ```

   readsb only adds the type (`t`) and registration (`r`) when `--db-file` is set. We chose port 30154; any free port will do.

   With the default accuracy, `2`, readsb gives tar1090 the garden's exact location, and tar1090 serves it to anyone on the same network. `1` rounds it to 2 decimal places, about 1 km. readsb also uses the rounded location itself, which is fine for decoding. Don't use `0` or `4`: they round it to whole degrees, which is too coarse. Our logger works out distances from the exact location in `site.json`, so it isn't affected.

5. Restart readsb and check the stream:

   ```bash
   sudo systemctl restart readsb
   nc localhost 30154 | head
   ```

6. Open `http://adsb-pi.local/tar1090` to see the live map.

## 3. The SSD (at home)

The Pi boots from the SSD, and there's no SD card. The logs are a folder on it, `/var/lib/adsb-logger`, so there's nothing to format or mount. Check the Pi really booted from the SSD:

```bash
findmnt -n -o SOURCE /          # /dev/sda2, not /dev/mmcblk0p2
```

If an SD card is left in, the Pi boots from that instead. The logger then refuses to start, so it can't fill the card, and the status page says why.

The system and the logs share the disk. The logger stops writing with 2 GB left (`min_free_gb`), and ext4 keeps another 5% for the system that the logger can't use, so a full log never stops the Pi. `adsb status` warns below 10 GB.

**If the SSD fails, the whole Pi stops,** because the system is on it too. USB SSDs usually fail by resetting, after a dip in the supply voltage. The disk then fails every write or goes read-only, and only a reboot brings it back. `--watchdog` (step 4) sets up the watchdog daemon. Once a minute it writes and syncs a small file on the SSD with `deploy/disk-check.sh`, and reboots the Pi if that fails for 3 minutes or hangs for 1. It runs locked in memory, so it keeps working when the disk doesn't. A disk that's really broken can't be fixed on site, so the Pi will keep rebooting until the next visit.

To make resets rare:

- Use the official 5 V 3 A supply. The Pi 4's USB ports share 1.2 A: the stick draws 300 mA and the GPS about 50 mA, which leaves enough for a SATA SSD, but not for many NVMe enclosures. If the status page reports power problems, use a powered USB hub or a lower-power SSD.
- Plug the SSD into a blue USB 3 port.
- Some USB-to-SATA adapters reset often on a Pi 4. In the trial, check `sudo dmesg | grep -i -E 'uas|reset'` after a few days. If the adapter keeps resetting, turn off UAS for it: add `usb-storage.quirks=VID:PID:u` to the start of `/boot/firmware/cmdline.txt`, keeping it all on one line, with the IDs from `lsusb`.

## 4. The logger, GPS clock and hotspot (at home)

From `tools/adsb` on the laptop:

```bash
make pi-deploy ARGS="--watchdog --gps --hotspot"
make pi-config       # set the garden's real location and ground height; restarts the logger
make pi-status
```

`pi-deploy` copies the code to `~/adsb-deploy` on the Pi and runs `deploy/install.sh` there with sudo. It never copies `site.json` or any logs. With `--hotspot`, it ends by printing the hotspot's name and password; note them down.

The install script is safe to run again. It never overwrites `site.json` and never touches the logs. It warns about anything it can't fix itself: the placeholder location, a Pi that booted from an SD card, no watchdog daemon, or readsb missing `--net-json-port` or `--db-file`. To update the code later, anywhere, run plain `make pi-deploy`, which restarts the logger. `--watchdog`, `--gps`, `--hotspot` and `--graphs` need internet (they install packages), but only need running once.

It does the following:

- creates the `adsb-logger` system user, in the `video` group so it can read the throttling flags
- copies the `adsb` package to `/opt/adsb-logger`, and installs the `adsb` command
- copies `site.example.json` to `/etc/adsb-logger/site.json` if there's no config yet
- installs `adsb-logger.service`, which restarts the logger whenever it stops. A new install leaves it off until `make pi-config` has set the location.
- installs `adsb-status.timer`, which writes the status page every minute, and adds it to the web server that came with tar1090
- sets up the Pi's hardware watchdog, which reboots it if the system hangs. With `--watchdog` it installs the watchdog daemon, which also reboots it if the SSD fails (see [step 3](#3-the-ssd-at-home)). Without it, systemd feeds the watchdog, which only catches a hung kernel.
- caps the system journal at 200 MB. It stays on the SSD, so a crash or watchdog reboot can be looked into afterwards.

The whole `adsb` package is copied, but the logger only loads its Pi-side modules (`logger`, `status`, `health`, `geometry`).

### What `--hotspot` sets up

A NetworkManager connection, `adsb-hotspot`, that broadcasts a Wi-Fi network named after the Pi (`adsb-pi`), with WPA2 and a random password. The Pi is `10.42.0.1` on it, and hands out addresses to whatever joins. Nothing on it reaches the internet. Running `--hotspot` again leaves it as it is and prints the password again. To choose your own password, run `sudo nmcli connection modify adsb-hotspot wifi-sec.psk 'NEW PASSWORD'` on the Pi.

The hotspot has a lower priority than any Wi-Fi the Pi already knows. At home the Pi joins your home network as usual. At the garden, where no known network is in range, it starts the hotspot by itself at boot. To try the hotspot at home, run `sudo nmcli connection up adsb-hotspot` on the Pi. If you're connected over Wi-Fi, this drops your SSH session. Join the hotspot to check it, then power-cycle the Pi to put it back on your home network.

If the hotspot doesn't appear, a cable still works: connect the laptop straight to the Pi's Ethernet port and use `PI=adsb-pi.local`. `--hotspot` also adds a wired connection, `adsb-cable`, ranked below the usual one. With no DHCP server on the cable, the Pi falls back to it after about 45 seconds and gives itself a `169.254` address, as the laptop does. It never hands out addresses, so it's harmless on the home network. This hasn't been tried yet: test it at home before relying on it.

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

### What `--graphs` sets up (trial only)

[graphs1090](https://github.com/wiedehopf/graphs1090), by readsb's author: graphs of signal, noise, gain, message rate and range, at `http://adsb-pi.local/graphs1090/`. It helps with tuning the gain in the trial, alongside the strong-signal share in `adsb status`. It keeps its data in memory and writes it to disk once a day, so it can lose up to a day of graphs in a power cut. That's fine, as our health log holds the figures that matter. Install it at home with `make pi-deploy ARGS="--graphs"`, which downloads and runs its installer. Remove it before the survey with `sudo bash /usr/share/graphs1090/uninstall.sh`, so that the Pi runs only what the survey needs.

## Status page

Open `http://10.42.0.1/adsb-status/` on the hotspot, or `http://adsb-pi.local/adsb-status/` at home. It shows the same report as `adsb status`, with any warnings at the top, and reloads every minute. It links to the live map at `/tar1090/`.

The page is written to `/run/adsb-status`, which is in memory, so it costs no disk writes. Anyone on the same network can read it. It shows the logger's state, not the garden's location or the logs. If it's stale or missing, check the timer with `systemctl list-timers adsb-status` and `journalctl -u adsb-status`.

## On each site visit

1. Join the Pi's Wi-Fi (`adsb-pi`) with a phone, and open `http://10.42.0.1/adsb-status/`. For a quick check, that's all you need.
2. To collect data, join it with the laptop and, from `tools/adsb`:

   ```bash
   make pi-status PI=10.42.0.1
   make pi-collect PI=10.42.0.1
   ```

`adsb status`, and the status page, show when the logger last wrote, the clock's state, free disk space, temperature, power problems and how much data was kept in the last 24 hours. They warn if:

- the Pi booted from an SD card, not the SSD
- the logger or readsb has stopped (checked directly on the Pi, not just from the log)
- the logger isn't connected to readsb, or nothing has come from it for 15 minutes, which means the stick, antenna or readsb has failed
- the clock isn't synchronised (checked directly with `chronyc`)
- the disk is filling
- the Pi is overheating or short of power
- readsb keeps disconnecting
- more than 10% of messages are very strong, or readsb is dropping samples (see below)
- nothing is being kept, which usually means the site location in the config is wrong
- a whole day had far fewer close passes than usual (see below)

They also count the **close passes** each UTC day: aircraft that came within 2 km of the garden below 3,000 ft, which are mostly LCY arrivals and departures. The count changes a lot with wind direction, and LCY's weekend closure halves it. So the warning only fires for a whole day with less than a fifth of the usual count, which points to a failed antenna, stick or cable rather than a quiet day. The last line gives the time of the last close pass.

They also show the receiver's gain, signal and noise levels, and the share of strong signals (stronger than -3 dBFS) over the last 24 hours, from readsb's `/run/readsb/stats.json`. That share shows whether the gain is right. [About 5% is the usual aim](https://github.com/wiedehopf/adsb-wiki/wiki/Optimizing-gain), and near an airport up to 10% is fine. Much more means the gain is too high, so the closest aircraft, the ones we need, may be missed. If so, set a fixed gain a step lower (`sudo readsb-gain 40`, say), wait a few hours and check again.

After a power cut the Pi's clock starts from the time it last saved, which is behind. So `adsb status` on the Pi finds the newest health record by this boot's uptime, not by its time. The status page also compares the Pi's time with the phone's, and says so if they're minutes apart: either the page has stopped updating, or the Pi's clock is wrong.

`adsb status` exits with code 1 when there are warnings. `make pi-status` also shows the logger's last journal lines; `make pi-journal` follows them live.

### Collecting the logs

`make pi-collect` copies the logs to `data/collected/` on the laptop (git ignores it; choose another folder with `COLLECT_DIR=...`). It does the following:

- checksums the files on the Pi
- copies only the new ones
- checks every copy against the Pi's SHA-256 checksum
- adds the checksums to `data/collected/SHA256SUMS`, which then lists every file collected so far

It prints `OK` or `FAILED`.

Files the logger is still writing to are left for the next visit, so every collected file is final. The logger lists them in `/run/adsb-logger/open-files`; they aren't worked out from the time, which can be wrong after a power cut. A file collected earlier is never overwritten. If the Pi's copy has changed, that's reported as a failure. Nothing is deleted from the Pi. Keep a second copy off site.

At the end of the survey, stop the logger first so its last files are closed, then collect everything:

```bash
make pi-ssh PI=10.42.0.1          # then: sudo systemctl stop adsb-logger
sh deploy/collect.sh --all 10.42.0.1
```
