# The simulated day

Make one, analyse it and open the viewer, from the top of the repository:

```bash
make demo        # or: noise adsb simulate demo --out data/derived/adsb/demo
open data/derived/adsb/demo/results/viewer.html
```

The simulated day isn't real data, though it includes the main kinds of error real data has. Its fleet of E190s, E190-E2s, E195-E2s, A220-100s and A320neos flies straight paths with no wind, turbulence or speed changes. Arrivals use 5.5°, or 4.49° for the A320neo, and the garden is 500 m north of the RWY 27 centreline, 4 km from the threshold. RWY 27 is in use until 13:15, then RWY 09. It includes overflights, two helicopter passes and some deliberate problems:

- about 8 m of noise on every position, as in good real ADS-B
- a cold day, with altimeter readings worked out from the actual pressure, so the temperature correction is tested
- METAR QNH rounded down, as real METARs do
- some positions too poor to use, and some aircraft with non-ICAO addresses
- an aircraft with no geometric altitude
- one sending sea-level height as geometric
- a reception gap near the garden
- QNH changing through the day
- an unreadable line
- a power cut at 12:10 that damages a log file and leaves the clock briefly unsynchronised

`truth.csv` gives the true values for every flight. The tests in `tests/test_simulate.py` check that the analysis recovers them. On the simulated day, 95% of arrivals come back within about 1.5 m of their true offset, 0.6 m of height and 0.01° of path angle. Real data will be worse, so these figures show the method works, not how accurate it will be in the garden.

The simulator only replaces its own earlier output. It won't write into a folder it didn't make.

To test the logger itself, run a fake readsb that replays the simulated day, and point the logger at it. See [Development](../README.md#development).
