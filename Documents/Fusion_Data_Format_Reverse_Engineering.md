# Decoding the Fusion 4G data format

5 November 2026

## Purpose

Read our own Fusion 4G measurement data directly, especially the 100 ms levels, 100 ms spectra and RAW audio that the CSV output may not cover. This supports the [Thamesmead measurement plan](Thamesmead_Garden_Measurement_Plan.md).

We found no public specification or open-source parser for `.cmg`, so this would start from scratch. The campaign must not depend on it: run CSV and `.cmg` together, and treat the decoder as an extra route to the data.

Page numbers refer to the PDFs in this folder, which are listed in the [documents README](README.md).

## Ground rules

- Work only on files from our own meter, by observing their structure and comparing them with known signals.
- Ask Acoem for the specification first.
- Don't decompile dBTrait or the firmware, extract firmware, or get around licensed options such as HTTP commands.
- Don't open the meter. Its seal is part of the type approval (file 31, p.6).
- Check the Fusion and dBTrait licence terms before starting, and take advice before publishing a parser. Acoem says `.cmg` is "not intended to be used outside our ecosystem" (file 29, p.13). UK and EU law has some interoperability allowances, but we haven't checked how they apply here.

## What we know

The March 2024 manual (file 37) confirms the session layout and storage sizes below, but gives no byte-level format, and its session example still dates from 2012. The other format notes date from 2019 or earlier, so all of this needs testing.

### Hardware and software

| Item | Detail | Source |
| --- | --- | --- |
| Processors | DSP for signal processing; ARM9 for storage, web pages and communications | File 31, p.3 |
| Certified firmware | Metrology 3.00, application 3.xx | File 31, p.6 |
| Manual | DOC1130, "FUSION Manuel d'utilisation", revision V, March 2024, for application firmware 3.01 and metrology firmware 3.00. Newer firmware (3.02) and certificate revision 7 now exist | File 37, p.1 |
| Web interface tabs | Infos, Temps réel, Config. mesure, Données stockées, Calib, Config. Système | File 31, p.3 |
| Connections | USB mass storage, Ethernet, Wi-Fi, 4G, FTP server and FTP(S) client; MQTTS to Cadence | File 29, pp.10, 26; file 37, p.223 |
| PC software | dBTrait, dBFileManager, dBFA | File 29, pp.5, 10 |
| dBTrait Viewer | Usable without a licence since version 6.1 | File 33, p.1 |
| Latest version sheet we have | dBTrait 6.2 | File 34, p.1 |

### File format

| Finding | Confidence | Source |
| --- | --- | --- |
| Fusion and DUO sessions are folders with sub-folders | High | File 33, p.7 |
| A session folder is named by date and time, and holds a `.cmg`, `.bid` files, `Logging.txt` for manual comments, and `Audio`, `Periods`, `Settings` and `Weather` folders, plus `*_TriggerCode6` for parallel fast-period data | High for the layout; the example dates from 2012 | File 37, p.210 |
| The `.cmg` holds the rules for reading the session's files, and `.bid` files hold the binary values of each instantaneous quantity | High | File 37, p.210 |
| `Settings` holds `.xml` files: configuration, daily electrical check results and the system log | High | File 37, p.210 |
| Sessions close and reopen at midnight, and at each automatic electrical check, whose few seconds aren't stored | High | File 37, p.210 |
| Older sessions are a single `.cmg`, or a `.cmg` with numbered `.BID` binary files such as `TEST_1.BID` | Medium | File 33, p.7; dBTRAIT32 manual |
| Data can be fetched by type and date: instantaneous values, spectra, markers, fast-period events and audio | High | File 29, p.10 |
| Data is written to the SD card every 10 s | High | File 29, p.27 |
| Sessions hold channels such as Leq, Slow, Fast, Peak and band spectra | Medium; older manual | dBTRAIT32 manual |
| `Partial Storage` `.cmg` files exist | Medium | File 33, p.8 |
| Files may start with `CAMPAIGN`, and contain `_DESC_`, `_ITEM_` and `_DBTRAIT_GLOBAL_` | Low; a file-extension site, and the link to 01dB is our inference | FileExt |
| Some timestamps may be Unix-style, because a dBTrait bug dated audio fragments to 1970 | Low; our inference | File 33, p.3 |
| Sessions carry time zone information | Medium; dBTrait has time zone settings for them | File 33, p.6 |
| Firmware affects how data is read: dBTrait has fixes for specific versions | High | File 33, p.6; file 34, p.5 |

### Related files

| File | Role | Source |
| --- | --- | --- |
| `xxxx.cmg.lock` | Created by dBTrait while a session is open | File 33, p.7 |
| `Global.cmg`, `dBtrait_Global.cmg` | Global level values and saved items | File 33, p.9; dBTRAIT32 manual |
| `MetrologicalHistory.xml` | Metrological history, fetched by dBFileManager | File 33, p.2 |
| `dBTrait.ini` | Settings, including `[Campaign]` `LockCampaign` and `TZIMode` | File 33, p.6 |
| `C:\ProgramData\01dB\dBFile\dBFileManager.ini` | dBFileManager settings | File 33, p.7 |

### Signal settings to expect

| Item | Expected | Source |
| --- | --- | --- |
| 1/3-octave bands | 6.3 Hz–20 kHz, which is 36 bands, or from 25 Hz depending on the high-pass filter. Storing Leq and Slow together may mean 72 values per record | File 29, p.24; file 37, p.226 |
| Below-range bands | Stored as an arbitrary 0 dB | File 37, p.226 |
| Display and storage resolution | 0.1 dB is the display step. Each stored indicator takes 2 bytes, a 1/1-octave spectrum 24 bytes and a 1/3-octave spectrum 72 bytes, which is 2 bytes per band. So probably scaled 16-bit values; the scale is unknown | File 29, p.26; file 37, p.211 |
| Logging | Period T from 20 ms to 3,600 s; the short period must divide exactly into T | File 29, p.24 |
| Audio | RAW at 51.2 kHz down to 1.6 kHz; 24-bit, stored in 32 bits. Binary files, with a header holding what's needed to recover calibrated levels, and split at 30 minutes | File 29, p.25; file 37, p.211 |
| Reference | 94 dB at 1 kHz | File 31, p.4 |

## Routes that need no decoder

| Route | What it gives | Limits | Source |
| --- | --- | --- | --- |
| CSV output | A file appended every logging period, sent alongside the `.cmg` files. Set under "Format de stockage des données" | 1 s minimum; no column list in the manual, so we don't know whether it includes spectra | File 29, p.13; file 37, p.150 |
| Push and FTP | Files sent to our server, or fetched from the meter. Push types include instantaneous values, sliding values, spectra, weather, events, signals and settings, for closed or open sessions | Same files; push is in all packages. Cadence takes over Server 1 if enabled | File 29, pp.10, 22–23; file 37, pp.157–158 |
| Health file | XML pushed every minute, with its fields documented | Status only, not measurements | File 37, pp.157–160 |
| dBTrait copy values | Tabulated values, on the original or recomposed time base | Needs a licence; older manuals show decimal commas and day-first dates | dBTRAIT32 manual |
| dBTrait WAV export | Timestamped WAV files | "Gain optimized" since 6.1, so **not calibrated** | File 33, p.2 |
| HTTP commands | Live values through `GetRealTimeValuesList`, `ConfigureRealTimeValues` and `GetRealTimeValues`, as XML. Each value covers the logging period before the timestamp, and a `v` before a value appears to mark it as below range (our inference from an example) | Paid extra; at most 30 values, 2 spectra and 6 weather values per the manual, while the Congrego notes imply 3 sets of spectra | File 29, pp.21, 23; file 37, pp.256–258; Congrego notes |
| Cadence API | Documented, per Acoem | Aggregated data; no public reference found | File 30, p.3 |

## Method

### 1. Ask Acoem

Ask for the format specification, the CSV column list, the manual edition for our firmware, and certificate revision 7. The 2024 manual gives 01db.support@acoem.com (file 37, p.1).

### 2. Protect the source data

Copy each session folder from the card, record SHA-256 checksums, and work only on copies. Don't open originals in dBTrait: it creates lock files and can save sessions in different storage formats (file 33, p.7).

Record the serial number, firmware version and full configuration with each capture.

### 3. Make controlled recordings

Each run is 2–5 minutes, changes one thing and has a written log with times.

| Run | Setup | What it should reveal |
| --- | --- | --- |
| A | 1 s logging, broadband only, quiet room | Baseline structure and headers |
| B | As A, with the calibrator at 94 dB, 1 kHz | Where broadband values are stored, and their encoding |
| C | As B, with 1/3-octave Leq on | Spectrum files, record length, band order |
| D | As C, with Slow spectra too | How two spectrum types are stored |
| E | Stepped tones at noted times, at several frequencies | A searchable pattern that confirms band order and timing |
| F | Logging period changed to 0.5 s, then 2 s | Which sizes follow the period |
| G | Same as C for 25 minutes | The 10 s write blocks and any file rollover |
| H | Trigger on, 100 ms event logging | Event records and fast-period storage |
| I | RAW audio at 25.6 kHz with the calibrator, then at 51.2 kHz | Header, sample layout (24 bits in 32) and calibration scale |
| J | MP3 audio | Whether MP3 files are standard |
| K | Each broadband indicator added in turn: LAF, LAS, max values, PNLT | Channel identifiers |
| L | Weather on, if we have the option | Weather records |
| M | Run across midnight with the electrical check on | How the session split and the missing seconds are recorded |
| N | As C, with the high-pass filter at 0.3 Hz, then 10 Hz | Whether the band count or record length changes |
| O | As C, in a quiet room with no calibrator | How below-range bands appear in the file, including the 0 dB value |

### 4. Compare the outputs

- Map the folder tree, file names and sizes for each run.
- Compare file size against record count × logging period, to find record lengths and headers.
- Compare runs that differ by one setting to find which bytes change.
- Check for text, compression and known file signatures. High entropy would suggest compression or encryption, which would change this plan.

### 5. Decode in order

1. **Header:** signature, version, serial number and device strings. Start with the `.cmg`, which holds the reading rules.
2. **Timestamps:** search for the known start time as Unix time, Windows FILETIME and OLE dates, in local time and UTC.
3. **Broadband values:** search `.bid` files for values near 94.0, first as scaled 16-bit integers, because each indicator takes 2 bytes, then as other forms.
4. **Spectra:** look for the calibrator's peak at the 1 kHz band and the 72-byte, 36-band stride.
5. **Channel table:** match names and identifiers using run K.
6. **Events and fast data:** decode the trigger records and 100 ms series.
7. **RAW audio:** confirm the 24-in-32-bit layout, decode the header, then check its calibration against the recorded 94 dB tone.

### 6. Validate

A decoded session counts as correct only if it passes all of these:

- Broadband values match the CSV, and dBTrait, to 0.1 dB.
- A-weighted bands add up to the logged LAeq, within about 0.1 dB, treating below-range 0 dB bands as missing.
- 100 ms values add up to the matching 1 s values, within about 0.1 dB.
- The calibrator tone reads 94 dB in LAeq, the 1 kHz band and calibrated RAW audio.
- Timestamps match the written log and GPS time, including across the 10 s blocks and any file rollover.
- Band energy appears in the expected band for every step in run E.

Keep the small test recordings and their expected values as regression tests.

## What to build

A small read-only Python package that:

- Reads a session folder and never writes to it.
- Records the firmware version and refuses unknown format versions, rather than guessing.
- Exports levels, spectra, events and audio times to documented CSV or Parquet files.
- Calculates SEL as set out in the measurement plan.

## Open questions

- [ ] Will Acoem provide the format specification and the manual edition for our firmware?
- [ ] Which firmware version do we have?
- [ ] Does the CSV output include 1/3-octave spectra, and all the broadband indicators we've chosen?
- [ ] Can dBTrait Viewer show and copy all the values we need to check against?
- [ ] Are any files compressed or encrypted?
- [ ] Does the format change between firmware versions?
- [ ] Do the licence terms restrict this work, or publishing a parser?

## Sources

Saved in this folder:

- File 29: [Fusion 4G datasheet, November 2022](29_Acoem_Fusion_Datasheet.pdf)
- File 30: [Fusion datasheet, November 2024](30_Acoem_Fusion_Datasheet_Nov2024.pdf)
- File 31: [LNE type certificate, revision 5](31_LNE_Type_Certificate_27092_Fusion_rev5_2024.pdf)
- File 33: [dBTrait version sheet, November 2018, English](33_dBTrait_Version_Sheet_Nov2018_EN.pdf)
- File 34: [dBTrait version sheet, April 2019, French](34_dBTrait_Version_Sheet_Apr2019_FR.pdf)
- File 35: [CUBE datasheet, February 2018](35_Acoem_CUBE_Datasheet_Feb2018.pdf), a sibling meter with the same options
- File 36: [Fusion datasheet, May 2018](36_Acoem_Fusion_Datasheet_May2018.pdf)
- File 37: [Fusion user manual, DOC1130 revision V, March 2024](37_Acoem_Fusion_User_Manual_DOC1130_Mar2024_FR.pdf). In French. A third-party copy, kept locally and not published in this repository because of its copyright notice

Online only:

- [dBTRAIT32 user manual](https://manualzilla.com/doc/6901230/user-manual). Older software, so its details may not apply to the Fusion.
- [Acoem Congrego notes on 01dB instruments](https://public.docs.acoemcloud.com/congrego/01db)
- [Acoem Airodis supported instruments](https://public.docs.acoemcloud.com/airodis/supported-instruments-and-protocols), which lists CSV ingest for the Fusion
- [FileExt CMG entry](https://filext.com/file-extension/CMG). Unverified.

Not read, because we couldn't open them:

- [dBTrait manual on Scribd](https://www.scribd.com/document/617622094/Dbtrait-Manual)
- [CUBE manual on ManualsLib](https://www.manualslib.com/manual/3649016/Acoem-Cube.html), which has a section on HTTP command lines
