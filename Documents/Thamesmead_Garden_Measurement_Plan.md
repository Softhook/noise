# Thamesmead garden noise measurement plan

4 November 2026

## Purpose

Measure arrivals in the garden now, then again once A320neos fly the proposed 4.49° approach, to test the model's estimate of about +1.0 dB LAmax against the E190.

The measurements can show the real difference at the garden, and the combined effect of aircraft noise and thrust. From that we can estimate the difference directly under the path, currently +2.3 dB in the model. They can't separate aircraft noise from thrust, or confirm the under-the-path figure directly.

This plan assumes the garden is at the Thamesmead survey site in the [Bickerdike Allen report](https://assets.ctfassets.net/lmkdg513arga/1dAp1OIK1za3G7I6ogmvX5/cd18f1a9a3b47a9ae987239abdb153e2/London_City_Airport__Aircraft_Noise_Survey_-_Thamesmead.pdf): around 4 km from the RWY 27 threshold and around 500 m north of the arrival path.

## Stage 1: measure today's aircraft

Start now, because this needs no A320neos and gives us the baseline and a test of our setup. To compare directly with the report, copy its setup where we can: a calibrated noise monitor checked at the start and end, microphone about 3 m up on a tripod, clear of reflecting surfaces, running for about 37 days.

Check the results against the report's RWY 27 arrivals, measured from 2 September to 8 October 2024:

| Aircraft | Flights | Average LAmax (dB) | Average SEL (dB(A)) |
| --- | ---: | ---: | ---: |
| Embraer E190 | 1,009 | 63.0 | 72.9 |
| Airbus A220-100 | 48 | 62.1 | 71.1 |
| Embraer E190-E2 | 12 | 61.3 | 70.5 |

Then answer four questions:

1. **Does the setup match?** Compare our averages and the gaps between aircraft with the table above. The airport's fleet may have changed since 2024, so compare type by type.
2. **How much do flights vary?** Record the spread for each type, which the report doesn't give. It tells us how many flights we need to trust a 1–2 dB difference.
3. **Does distance behave as the model predicts?** Compare E190 levels with each flight's actual distance from the garden. Flights passing closer should be louder by the amount the model calculates.
4. **Do the two sites agree?** If we can get NMT6 data for the same flights, compare them. The model explains only about 8.6 dB of the E190's measured 11.8 dB LAmax drop from NMT6 to the garden, and 5.4 dB of its 10.9 dB SEL drop. Alongside local shielding by houses and fences, quieter events in the garden (58–63 dB LAmax) may clip against the monitor's event trigger threshold before completing a full 10 dB-down window. The report gives no trigger settings, but in its Table 1 SEL minus LAmax tends to shrink with level, from 9.9 dB on the E190 to 8.5 dB on the Dash 8-Q400, where NMT6 reads 9.0 and 9.7 dB.

## Stage 2: compare the A320neo

Repeat the same setup once A320neos fly the 4.49° approach, using flight data to confirm each flight's type and approach. Measure E190s in the same period, so that both aircraft have similar weather and conditions.

Compare aircraft at the garden rather than relying on absolute levels, because differences should cancel much of the unexplained error between sites. Then work back in three steps, using the flights' real positions rather than the nominal figures below:

1. Take the average A320neo level minus the average E190 level at the garden.
2. Subtract the calculated distance and air effect at the garden. The result is the aircraft and thrust effect combined.
3. Add the calculated distance and air effect directly under the path.

This example uses an invented measurement of +2.0 dB LAmax:

| Step | LAmax (dB) | Model today (dB) |
| --- | ---: | ---: |
| Difference at the garden | +2.0 (invented) | +1.0 |
| Subtract distance and air, 500 m to the side | −0.75 | −0.75 |
| Aircraft and thrust combined | +1.25 | +0.25 |
| Add distance and air, directly under the path | +2.06 | +2.06 |
| Estimated difference under the path | +3.3 | +2.3 |

Do the same for SEL, where distance and air are +0.48 dB at the garden and +1.26 dB under the path.

## Spectra and tone check

A320neos could sound different from E190s even at the same LAmax, because LAmax doesn't capture tonal components (Alves Vieira et al., 2019). Record all 24 1/3-octave bands from 50 Hz to 10 kHz for each event, by aircraft type in both stages, so that Stage 1 gives the baseline for today's aircraft. This lets us compare spectra between aircraft and test the model's use of one spectrum for all of them (ANP Spectral Class 205; [file 19](19_EU_Directive_2015-996_Doc29_Noise_Method.pdf), Table I-10, p.800).

### 1.6 kHz and 2 kHz bands

Merino-Martinez et al. (2024) report a tone from the nose landing gear around 1,700 Hz across the A320 family, including the A320neo. That falls in the 1.6 kHz band (about 1.4–1.8 kHz). The 2 kHz band (about 1.8–2.2 kHz) is included because Doppler shift raises the frequency heard as an aircraft approaches.

At the moment of LAmax and through the flyover, compare each band with its own neighbours. A tone should show as a peak above them.

| Band | Compare with |
| --- | --- |
| 1.6 kHz | Average of 1.25 kHz and 2 kHz |
| 2 kHz | Average of 1.6 kHz and 2.5 kHz |

As a starting point, treat a band more than 5 dB above its neighbours as a prominent tone (Flindell). This is an older criterion, and we haven't checked it against current standards.

A peak in these bands wouldn't show that the sound is unique to the A320neo, or that it comes from the landing gear. The same study found A320neos less tonal on average than A320ceos, from few A320neo flights, so we shouldn't assume they are more tonal. To test the landing gear explanation, check whether the level changes with each flight's speed, as the study reports, and compare with any other A320-family aircraft measured.

### Audio recordings

1/3-octave bands can miss a tone. By our calculation, a tone 10 dB above broadband noise in 10 Hz bins adds only about 1 dB to the 1.6 kHz band, which is about 365 Hz wide. They also limit how tones are detected in EPNL, which only considers the strongest tone ([file 28](28_Torija_Aircraft_Noise_Complex_Tones_CEAS_2018.pdf), p.4). Record calibrated audio for at least a sample of events of each aircraft type, so that we can run narrowband analysis such as Aures tonality (file 28, p.5) and listen back.

## Monitor setup: Acoem Fusion 4G

We're using the weatherproof version of the Fusion 4G. The report used an 01dB DUO, so this is a different instrument and the Stage 1 comparison also tests that change. Page numbers below refer to the Acoem datasheet ([file 29](29_Acoem_Fusion_Datasheet.pdf)) unless another file is named. We don't have the manual yet, so menu names may differ.

### Instrument summary

| Item | Specification | Source |
| --- | --- | --- |
| Standard | IEC 61672-1:2013 Class 1 | p.24 |
| Type approval | LNE-27092 revision 5, valid to 17 March 2034. Acoem's portal now lists [revision 7, dated 4 November 2026](https://support.01db.acoem.com/en/support/solutions/articles/5000902114-fusion-certificat-lne-27092-r%C3%A9v-7-du-04-nov-2026-fr), which we haven't read | [File 31](31_LNE_Type_Certificate_27092_Fusion_rev5_2024.pdf), p.1 |
| Firmware covered | Metrology 3.00, application 3.xx; shown in the meter's Information menu. Our manual is for application 3.01, and [3.02 came out in April 2025](https://support.01db.acoem.com/en/support/solutions/articles/5000896263-faq-about-update-firmaware-fwa-3-02-fwm-3-00-) | File 31, p.6; file 37, p.1 |
| Microphone | G.R.A.S. 40CD or 40CE, ½-inch; check which ours has. The manual says the 4G comes with a 40CD, but also lists both as standard. The 40CE is free-field, while the 40CD is close to random-field | File 31, pp.3–4; file 37, pp.11, 161, 227, 234 |
| A-weighted range at 1 kHz | 24–138 dB (40CE) or 22–137 dB (40CD), on the meter's own input | File 31, p.5 |
| SEL lower limit | 10 dB above the lower LAeq limit | File 31, p.5 |
| Typical self-noise | 16.1 dB LA, 20.2 dB LZ with a 40CD; 18 dB LA, 22.1 dB LZ with a 40CE. The datasheet gives the lower figures for the 40CE, so we've followed the more detailed manual | File 37, p.222; p.25 |
| 1/3-octave bands | 6.3 Hz–20 kHz; linear from 17 dB at 40 Hz–5 kHz and from 21 dB at other bands | p.24; file 31, p.5 |
| Logging period | 20 ms to 3,600 s, in 5 ms steps | p.24 |
| Audio | RAW at 51.2, 25.6, 12.8, 6.4, 3.2 or 1.6 kHz, or MP3. RAW is 24-bit, stored in 32 bits, in files of up to 30 minutes | p.25; file 37, p.211 |
| Clock | GPS to within 50 ms; internal clock within 0.5 s per 24 hours | p.27 |
| Environment | −10 to +50 °C; 90% humidity, non-condensing | p.27 |
| Power | 8–28 V DC; 6,750 mAh internal battery, not removable | pp.26–27 |
| Free-field correction | Default −0.4 dB for a 40CD or −0.3 dB for a 40CE on the meter's own input, allowing for the windscreen and meter body | File 37, p.232 |

### Certified configurations

The certificate covers these setups (file 31, p.4):

- The meter's own input, with a 40CD or 40CE microphone at 0° and a short windscreen.
- The DMK01 outdoor microphone, with a 40CD microphone at 0° or 90°, its dedicated short windscreen and a nose cone.

**The weatherproof kit isn't named in that list.** The certificate does list an integral windscreen and nose cone as accessories (p.3), and revision 4 added them for a 40CD at 90°. Revision 5 then removed the own-input 40CD at 90° configuration (p.2). So our setup may fall outside the certified configurations, even though the meter itself is Class 1. The manual has the same conflict: it recommends the integral windscreen and nose cone for outdoor use (file 37, pp.24–25), but its approved setup on the meter's own input is a short windscreen without a nose cone (file 37, pp.263–264).

This doesn't stop us measuring, and differences between aircraft should largely cancel the kit's effect, but:

- Don't describe the setup as a certified Class 1 configuration until Acoem confirms it.
- Ask Acoem for the kit's frequency response and any correction the meter applies, because a windscreen effect at high frequencies would change absolute band levels. For a 40CD at 0°, the manual's corrections are 0 dB with the nose cone and −0.1 dB without it at 1.6 and 2 kHz, but −2.9 to −6.0 dB with it and −1.0 to −2.9 dB without it from 6.3 to 10 kHz (file 37, p.234). It doesn't say whether these apply to the integral windscreen, so also confirm that the meter's correction matches what's fitted.
- Use the same kit, microphone and settings in both stages.
- Don't treat audio recordings as certified measurements. Audio recording, weather stations and data transfer are outside the type examination (file 31, p.4).

### Mounting

- Mount the meter upright on a tripod with the microphone about 3 m up, clear of reflecting surfaces, as in the report. The weatherproof kit is designed for direct tripod mounting (p.15).
- Keep the connector cover on. The meter is rated IP55 upright with the cover, and IP42 without it (p.28). IP55 also needs a 40CD microphone (file 37, p.254). Neither document gives a separate rating for the kit, so ask Acoem about long-term outdoor use.
- Make the tripod rigid and secure, because the microphone is on the meter body. Vibration of 1 m/s² raises the lower limit of the linear range to 80 dB perpendicular to the diaphragm, or 60 dB parallel to it (p.28).
- Point the microphone straight up and use the 0° setting. The DUO datasheet says statutory aircraft noise measurements require 0° ([file 32](32_Acoem_DUO_Datasheet_May2018.pdf), p.5), and 0° is the only direction approved on the meter's own input (file 37, p.263). A 40CD can also be set to 90° there, but the manual describes that for horizontal sound such as land transport (file 37, pp.106, 221). Keep this the same in both stages.
- Expect some high-frequency uncertainty on arrivals. The standard pays particular attention to response within ±30° of the reference direction (p.8), which suits departures overhead, but arrivals reach the garden about 51–57° from vertical by our calculation. With the short windscreen, a 40CD deviates by up to 0.2 dB at ±30° and 1.2 dB at ±90° at 1–2 kHz, and by up to 1.4 dB and 4.8 dB at 4–8 kHz (file 37, p.235). Our angles fall between those columns, and the table doesn't cover the integral windscreen.

### Measurement settings

Run continuously and calculate SEL afterwards, so that no event threshold can clip it. Use triggers only for audio and faster spectra.

| Setting | Value | Why |
| --- | --- | --- |
| Mode | LOG, running continuously | Keeps SEL independent of triggers |
| Logging period | 1 s | Gives the continuous time history |
| Event logging period | 100 ms | Shows a tone moving between bands; must divide exactly into the 1 s period (p.24) |
| Broadband levels | LAeq, LAS and LAF, with LASmax and LAFmax per period | The report doesn't say whether its LAmax is Fast or Slow |
| Spectra | 1/3-octave, Leq and Slow together | Gives event totals and the spectrum at LASmax (p.19) |
| Aircraft indicators | PNL and PNLT on, if we have the PNL option (file 37, p.217) | Gives a rough comparison with the certificates' tone correction |
| Audio | RAW at 25.6 kHz, not MP3 | Keeps audio usable for narrowband analysis up to about 12 kHz (p.25) |
| Event trigger | Set after a few days of background data. Start with the maximum 10 s pre-trigger and 15–20 s post-trigger. At 25.6 kHz, audio can start at most 18 s before the trigger is confirmed, and pre-trigger plus minimum duration can't exceed 70 s (file 37, pp.100, 103) | Should capture the whole event; SEL comes from the continuous 1 s data, so it isn't affected |
| Electrical check | Once a day at midnight, adding 1,600 Hz as a user-defined frequency | Avoids flying hours. Each automatic check closes and reopens the session, and its few seconds aren't stored (file 37, p.210) |

Calculate SEL across each event's 10 dB-down window from the 1 s values: SEL = 10·log10(Σ 10^(LAeq,i/10)).

### Reading the spectra

These estimates are our own calculations, for a 3 m microphone, 500 m to the side and 4 km from the threshold.

- **Ground reflections:** over hard ground, cancellations would fall at about 137, 229 and 320 Hz for an E190 at 5.5°, and 156, 260 and 364 Hz for an A320neo at 4.49°. Treat differences between them below about 500 Hz with caution, and use Stage 1 to see how much this matters at the garden.
- **Tones:** reflections can also make a tone rise and fall as the aircraft moves, so judge tones over several seconds.
- **High bands:** at 63 dB LAmax with the Class 205 spectrum, we'd expect about 48 dB at 1.6 kHz and 45 dB at 2 kHz, but only about 26 dB at 5 kHz and 10 dB at 6.3 kHz. The 6.3 kHz figure is below the meter's 21 dB linear limit for that band. Bands from about 5 kHz up will probably be background noise. A band below its measuring range is stored as an arbitrary 0 dB (file 37, p.226), so treat those values as missing rather than averaging them.
- **Low bands:** wind noise affects these first, so check them against wind data. The meter doesn't detect overloads at 31.5 Hz (file 31, p.5), which is below the bands we're analysing, but strong wind could still affect it.

### Running the campaign

- **Power:** the internal battery lasts about 20 hours (p.27), or 15 hours with an active mobile connection (file 37, p.224), so use mains power through the optional IP67 external charger, which has a 10 m cable (p.28). The standard charger isn't waterproof, and the manual suggests a small cut in the connector cover, sealed with silicone, for any added cable (file 37, p.25). The report had a gap for battery changes.
- **Storage:** the supplied 2 GB card is too small. RAW audio takes 4 bytes per sample (file 37, p.211), so at 25.6 kHz, 150 one-minute events a day comes to about 34 GB over 37 days, and continuous audio about 327 GB. Logging adds about 1 GB by our estimate, so a 32 GB card won't last the full period; plan a card swap or use a larger card. With a card nearly full, the 100 ms data and audio stop at 50 MB left and the 1 s data at 3 MB (file 37, pp.211–212). The meter takes SD, SDHC or SDXC cards, Class 10 or better, but Acoem accepts no liability for data lost on cards it didn't supply (file 37, pp.224–225, 253).
- **4G:** use it for health checks and instantaneous values, and collect audio from the card. The modem raises power use from about 1.2 W to as much as 3.8 W (p.27). If Cadence is on, it takes over push Server 1, so use Server 2 for our own server. Push can only be switched on or off in Ready mode (file 37, pp.157–158, 160).
- **Calibration:** use a certified Class 1 calibrator at 94 dB (file 31, p.6), such as Acoem's CAL31 ([file 30](30_Acoem_Fusion_Datasheet_Nov2024.pdf), p.7). One isn't listed in the standard package. Record the reading at the start and end, and reject the new sensitivity offered at the end, so that any drift is reported rather than absorbed. Keep the default free-field correction and record it.
- **Weather:** weather logging is an extra on every package (p.23). The WXT536 records wind, temperature, humidity, rain and pressure, and can share the meter's power supply (p.17). The weather logging period must be a multiple of the noise period, with a 1 s minimum (p.24). Temperature and humidity also affect air absorption.
- **Clock:** confirm a GPS fix on site, and check whether the flight data uses UTC. Turn on GPS synchronisation, which needs at least 4 satellites. Without "synchronisation priority", the clock is only corrected when a measurement ends, so at midnight in continuous running; a clock that was running fast leaves overlapping data after midnight. With it on, a drift over 1 s lasting 15 s restarts the session (file 37, pp.149–150). We'd leave it off, because the clock drifts less than 0.5 s a day, but check the event log for corrections.
- **Remote checks:** the meter can send an SMS at 10% battery and if it's moved, and it stops and saves its data at 3% battery (pp.3, 20). Use these alerts during the campaign. The movement alert defaults to 200 m and needs a SIM that can send SMS (file 37, p.150). The meter can also push a health file every minute, giving battery, free card space, GPS, signal, weather station state and electrical check result (file 37, pp.157–160).
- **Data:** CSV export is limited to periods of 1 s or longer (p.13), and the manual doesn't list its columns (file 37, p.150), so the 100 ms data will probably need Acoem's software or our own decoder. See the [data format plan](Fusion_Data_Format_Reverse_Engineering.md). Copy the data and record its checksums before opening it in any software.
- **Firmware:** note the version at the start and don't update it between stages unless Acoem says it's necessary. On an approved instrument, a firmware change invalidates its previous verification (file 37, p.263).

Before the full deployment, run a 2–3 day trial and take the data all the way through export, SEL calculation, spectra and flight matching.

## What to record

Each flight needs its noise event matched to its aircraft type and position, otherwise the comparison can't be made.

| Data | Used for | Source |
| --- | --- | --- |
| LASmax, LAFmax and SEL for each event, with time | The levels being compared | Our monitor; SEL calculated from the 1 s LAeq |
| Continuous 1 s LAeq time history and monitor trigger settings | Computing true 10 dB-down SEL without event-threshold truncation on quieter arrivals | Our monitor |
| 1 s 1/3-octave levels, all 24 bands from 50 Hz to 10 kHz | Comparing spectra between aircraft and checking for tones | Our monitor |
| Calibrated audio for a sample of events of each type | Narrowband tone analysis and listening back | Our monitor or a separate recorder |
| Calibration checks and any gaps in recording | Showing the data is sound | Our monitor |
| Aircraft type, runway and time for each flight | Matching events to aircraft | To be confirmed; the airport supplied this for the report |
| Track and height for each flight | Replacing the nominal 500 m and heights | To be confirmed; the airport supplied this for the report |
| Aircraft weight, if available | Explaining differences between aircraft | To be confirmed |
| Wind, temperature and rain | Removing or explaining weather effects | To be confirmed |
| Other noise during events | Removing events that aren't only the aircraft | Our monitor or site notes |
| NMT6 levels for the same flights, if available | Comparing the two sites | To be confirmed; the report used airport system data |

Report each average with its number of flights and its spread. Calculate both a simple average and an energy average, because the report doesn't say which it used. Keep departures as a separate set, since they fly over the site and the model doesn't estimate them.

## Limits and open questions

The under-the-path figure will remain an estimate, because it assumes the aircraft and thrust effect is the same from the side as from below. Lateral attenuation, which the model leaves out, would change the garden's difference by only about 0.1 dB at 500 m. A monitor under the path, such as NMT6, would be the direct check.

- [ ] Is the garden at the report's survey location, and how far is it from the usual arrival track?
- [ ] Does our Fusion have the audio recording and weather options? Spectra are included, but these two may be extras (file 29, p.23). The Infos page shows installed options as letters: S spectra, T trigger, A audio, P PNL, O weather, F FTP, D push and H HTTP commands (file 37, p.217).
- [ ] Do we have a Class 1 calibrator, a larger SD card, the external charger and Acoem's dBTrait software?
- [ ] Is the weatherproof kit within the certified configurations, what correction does the meter apply for it, and what is its frequency and directional response at 51–57° from vertical? The manual doesn't answer these.
- [ ] Which microphone (40CD or 40CE) and firmware version does our Fusion have?
- [ ] What Fast or Slow setting, event trigger, SEL method and microphone direction did Bickerdike Allen use?
- [ ] Can we get flight type, track and height data, and from whom?
- [ ] Can we get NMT6 levels for the same flights?
- [ ] Where will weather data come from?
- [ ] When would A320neos start flying the 4.49° approach?

## References

Full details are in the [documents README](README.md). Files 19, 28–32 and 37 are saved in this folder. The other three are online only, and we've read only their abstracts or search excerpts, so check the full texts before relying on them.

- File 19: Directive (EU) 2015/996, Doc 29 method and ANP spectral classes.
- File 28: Torija, Self and Lawrence (2018), [Impact assessment of aircraft noise with high content in complex tones](28_Torija_Aircraft_Noise_Complex_Tones_CEAS_2018.pdf). Slides; the recordings are of take-offs at Heathrow.
- File 29: Acoem, [Fusion 4G technical datasheet, November 2022](29_Acoem_Fusion_Datasheet.pdf). Manufacturer's specifications.
- File 30: Acoem, [Fusion datasheet, November 2024](30_Acoem_Fusion_Datasheet_Nov2024.pdf). Shorter and more recent.
- File 31: LNE, [type examination certificate LNE-27092 revision 5](31_LNE_Type_Certificate_27092_Fusion_rev5_2024.pdf), 2024. In French.
- File 32: Acoem, [DUO datasheet, May 2018](32_Acoem_DUO_Datasheet_May2018.pdf). The model of meter used in the report.
- File 37: Acoem, [Fusion user manual, DOC1130 revision V, March 2024](37_Acoem_Fusion_User_Manual_DOC1130_Mar2024_FR.pdf), for application firmware 3.01 and metrology firmware 3.00. In French. A third-party copy, kept locally and not published in this repository because of its copyright notice.
- Merino-Martinez, Besnea, von den Hoff and Snellen (2024), [Psychoacoustic analysis of the noise emissions from the Airbus A320 aircraft family and its nose landing gear system](https://research.tudelft.nl/en/publications/psychoacoustic-analysis-of-the-noise-emissions-from-the-airbus-a3/), AIAA 2024-3398.
- Alves Vieira, Mehmood, Merino-Martinez, Snellen and Simons (2019), [Variability of sound quality metrics for different aircraft types during landing and takeoff](https://research.tudelft.nl/en/publications/variability-of-sound-quality-metrics-for-different-aircraft-types/), AIAA 2019-2512.
- Flindell, [Sounds with tonal features: research methods and assessment](https://www.ioa.org.uk/system/files/proceedings/ih_flindell_sounds_with_tonal_features_-_research_methods_and_assessment.pdf), Institute of Acoustics proceedings.
