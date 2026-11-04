# Source documents for the London City approach noise model

Downloaded 4 November 2026. Page numbers are PDF page numbers, not the numbers printed on the page.

## Documents the model's figures or the analysis rely on

| File | What was taken from it | Where |
|---|---|---|
| `01_LCY_Stage3_Consultation_Document_Issue1.1.pdf` | Runway elevation of 20 ft AMSL; 2038 forecast fleet mix (E195-E2 most-flown type without the change) | Section 3.7.8, p.11; Figure 3, p.12 |
| | Approach altitude profiles: RWY 09 from 2,000 ft AMSL and RWY 27 from 3,000 ft AMSL | Figure 8, p.22; Figure 9, p.23 |
| | The airport's arrival tables: A320neo at 4.49° vs other types at 5.5°, dB(A) SEL, 0.5–5.0 km ("Airport" scenarios), and the 3 dB "noticeable" criterion | RWY 27 Figure 17 and section 5.4.11, p.30; RWY 09 Figure 18, p.31 |
| | Level-flight SEL table at 2,000, 3,000 and 4,000 ft, including E190 level vs descending at 4,000 ft (73 vs 71 dB SEL) | Figure 22, p.32 |
| `02_LCY_Annex_C_Aircraft_Noise_Technical_Report.pdf` | E190 (+1.5 dB) and A220-100 (−1.5 dB) arrivals modelled with AEDT 737-500 data; E190-E2 modelled with EMB190 (−0.9 dB); E195-E2 scaled from E190-E2 | Table 4, p.10; p.11 |
| | A320neo modelled with unadjusted AEDT data on LCY profiles altered only for 4.49° | pp.8, 11–12 |
| | "Quieter per arrival at most locations"; "slightly louder" than other new-generation types | p.19 |
| | `N65` (`65 dB LASmax`) contour counts alongside `LAeq` and `SEL` | pp.23–25, 58–59 |
| | 6 dB per doubling of distance (`20 log`); about 20% lower gives under 2 dB | p.41 |
| `03_LCY_Consultation_FAQ_Week8.pdf` | Arrival differences described as not likely to be perceptible, with altitude accounted for | Section 2.5.5, p.3 |
| `04_LCY_Consultation_Summary_Document.pdf` | The airport's qualitative noise summary | pp.6–7 |
| `08_AEF_Noise_Lessons_for_London_City_Airport.pdf` | Certification comparison (from earlier EASA issues); measured arrivals at Reagan National: vs E190 (1.8–2.2 dB LAmax, 2024–25) and vs A220 (+2.5 dB LAmax, Jan 2022, 19 flights each) | Table 4, p.6; Table 5, p.8; Table 6, p.9 |
| | Reproduction of the airport's Stage 2 arrival tables, which match Stage 3 | Table 7, p.10 |
| | "Doubling or halving the altitude results in a 10dBA" change in LAmax, given as an unsourced rule of thumb | p.9 |
| `09_EASA_TCDSN_A.064.3_A320_Issue42.pdf` | A320neo certified approach levels (LEAP-1A and PW1100G) | A320-251N from p.175; A320-271N from p.226 |
| `10_EASA_TCDSN_IM.A.071_ERJ190_Issue24.pdf` | E190, E190-E2 (ERJ 190-300) and E195-E2 (ERJ 190-400) certified approach levels | ERJ 190-100 STD from p.78; ERJ 190-300 from p.190 |
| `11_EASA_TCDSN_A.064_Cover_Issue93.pdf` | Confirms A320 models are in Volume 3 | p.2 |
| `12_LCY_Aircraft_Noise_Categorisation_Scheme_March2022.pdf` | ICAO Chapter 4 requirement at LCY; E190 certification example (92.5 EPNdB) and AEDT 3° vs 5.5° run (93.3 vs 87.9 EPNdB at 2 km) | Section 2.4.2, p.13; pp.6, 11, 33 |
| `17_LCY_Stage2_Develop_and_Assess_V1.1.pdf` | Threshold crossing heights above runway threshold: 35 ft on current 5.5° ILS and 50 ft on proposed 4.49° RNP-AR (giving 55 and 70 ft AMSL at 20 ft runway elevation) | pp.50–51, 61–62, 72–73, 80–81 |
| `18_EASA_TCDSN_IM.A.570_BD500_A220_Issue14.pdf` | A220-100 certified approach level (91.9 EPNdB at 54,658 kg) | BD-500-1A10 records, pp.3–5 |
| `19_EU_Directive_2015-996_Doc29_Noise_Method.pdf` | Doc 29 method as adopted in 2015: 24-band AIR-1845 atmospheric attenuation rates (`50 Hz–10 kHz`) and spectral air-absorption equation | Appendix D, equation D-1 and Table D-1, p.118 |
| | Lossless infinite-path exposure scaling (`10 log` for SEL vs `20 log` for peak) and finite-segment exposure method | Appendix E, equation E-8 and section E3, pp.122–123 |
| | 2015 ANP aircraft profiles, approach NPD curves and reference spectra: `737500` (`CFM563`), `A320-211`/`232` (`CFM565`/`V2527A`), `EMB190` (`CF3410E`), and Spectral Class `205` (*"Approach, 2-Engine High-Bypass"*) | Appendix I: pp.146, 153, 166, 189–190, 198–199, 221, 747, 752–754, 793–794; Table I-10, p.800 |
| | Lateral attenuation, Λ(β,ℓ), for a listener beside the path ("Thamesmead garden" scenario, not applied) | Equations 2.7.40–2.7.44, p.80 |
| `20_NASA_TM83214_SEL_EPNL_Duration_Coefficients.pdf` | Lateral-attenuation duration coefficients: contouring programs assumed 10 (`10 log` SEL); measured 8.4 for a Boeing 747 (`11.6 log` before air) and 5.5 for a T-38 | pp.3–6; Table 1, p.8 |
| `21_BAP_Aircraft_Noise_Survey_Thamesmead_Nov2024.pdf` | Arrivals measured by aircraft type at London City's NMT6, 2 September to 8 October 2024 ("Monitor 6" scenarios), and at the Thamesmead survey site ("Thamesmead garden" scenario). The report also has departures, which the model doesn't use. | Table 3, p.8; NMT6 overflown by RWY 27 arrivals, p.9; Table 1, p.6; site position, pp.4–5 |

## Certified approach levels extracted from the EASA sheets

| Aircraft | Landing mass | ICAO chapter | Approach (EPNdB) |
|---|---:|---|---:|
| A320neo, LEAP (A320-251N/252N/253N) | 66,300 kg | 4 / 14 | 92.5–92.7 |
| | 67,400 kg | 4 / 14 | 92.7–92.8 |
| | 68,400 kg | 4 / 14 | 92.9 |
| A320neo, PW1100G (A320-271N/272N/273N) | 66,300 kg | 4 / 14 | 92.0–92.3 |
| | 67,400 kg | 4 / 14 | 92.2–92.4 |
| | 68,400 kg | 4 / 14 | 92.3–92.6 |
| E190 (ERJ 190-100 STD, LR, SR): Block 2, improved chevron nozzle | 43,000 kg | 3 or 4 | 92.5 (used in the model) |
| E190 IGW: Block 2, improved chevron nozzle | 43,000–44,000 kg | 4 | 92.5 |
| E190 / E190 IGW: Block 2, improved chevron nozzle and Flap 06 inhibitor | 43,000–44,000 kg | 4 | 91.8 (not in the default; in the evidence band) |
| E190: improved chevron nozzle, not listed as Block 2 | 43,000 kg | 3 only | 92.4 (not used: Chapter 3 prohibited at LCY) |
| E190: low-loss chevron nozzle | 43,000 kg | 3 or 4 | 92.7 |
| E190 IGW: low-loss chevron nozzle | 43,000–44,000 kg | 3 or 4 | 92.8 |
| E190-E2 (ERJ 190-300) | 49,050 kg | 14 | 91.4 |
| E195-E2 (ERJ 190-400) | 54,000 kg | 14 | 91.7 |
| A220-100 (BD-500-1A10; PW1519G, PW1521G, PW1524G) | 54,658 kg | 4 / 14 | 91.9 |

These were extracted by script from the PDF text across all listed records (`file 09`: 2,552 records; `file 10`: 313 records; `file 18`: 5 BD-500-1A10 records) and verified on 4 November 2026:

- **ICAO Chapter 3 exclusion (`file 12`, section 2.4.2, p.13):** London City requires at least Chapter 4 certification. All 14 E190 records at `92.4 EPNdB` are Chapter 3 only. The airport's example E190 (`flyover 81.9, sideline 91.7, approach 92.5 EPNdB`; `file 12`, p.33) matches Chapter 4 records `A19555` and `A19556` (records `A19104` and `A19112` have the same levels under Chapter 3).
- **Flap 06 inhibitor records:** The default leaves out the E190 `91.8 EPNdB` records, which file 10 lists with a Flap 06 inhibitor. The reasoning is that a steep approach would need Flap 6, but no document here states the flap setting E190s use at London City, so this is an assumption. The band under the slider therefore extends to `+0.9 dB` (A320neo 92.7 vs 91.8).
- **What the sources don't say:** Which E190 modifications or which A320neo engine would be used at London City, and what its typical landing weights are. Choosing 66.3 t assumes landings are nearer the lowest listed mass. The midpoint is a simple choice for an unknown engine, not a sourced method.
- **AEF Table 4 differences (`file 08`, p.6):** AEF cites earlier EASA issues (`A.064.3` Issue 41 and `IM.A.570` Issue 10): its `91.5 EPNdB` A220 figure is a reduced-weight (55,791 kg) **A220-300** (`BD-500-1A11`, `file 18` p.10, which does not operate at LCY), and its `92.1–92.3 EPNdB` A320neo range quotes PW1100G variants while omitting LEAP-1A (`92.5–92.9 EPNdB`).

## Searched, with no 2.5 dB figure or E190 arrival table found

| File | Why it is here |
|---|---|
| `05_LCY_Full_Options_Appraisal_Issue1.0.pdf` | Searched for a 2.5 dB figure and E190 arrival tables; none found. Contains `N65` (`65 dB LASmax`) contour population counts (p.20, matching `file 02` and `file 16` p.23). |
| `06_LCY_Consultation_Response_Document_Issue1.0.pdf` | Searched for a 2.5 dB figure and E190 arrival tables; none found |
| `07_LCY_Stage3_Response_Addendum.pdf` | Searched for a 2.5 dB figure; none found |

## Model parameters: sourced physics vs modelling choices

| Parameter | Value in model | Basis and limitations |
|---|---|---|
| Atmospheric absorption | 24-band spectral `airLossDB(h)` | **Sourced (`file 19`):** `AIR-1845` 1/3-octave attenuation (`Table D-1`, p.118) applied to unattenuated ANP Spectral Class `205` (*"Approach, 2-Engine High-Bypass"*, `Table I-10`, p.800; `Eq. D-1`), the same spectrum for both aircraft. Effective A-weighted rate is about 4–5 dB/1,000 ft below 300 ft, 2.2 dB/1,000 ft at 1,000 ft and 1.4 dB/1,000 ft at 2,500 ft. Against the `CF3410E` approach NPD table (p.747) the model is within `0.13 dB` per table interval for `SEL`, and overstates the fall by `0.2–0.4 dB` per interval for `LAmax`. Other engines differ by up to about `0.4 dB` per doubling (`CFM565`/`737500` use Spectral Class `202`). |
| Runway elevation and `0.5 km` limit | 20 ft AMSL subtracted; ground noise plotted from 0.5 km (0.27 nm) | **Sourced (`file 01` pp.11, 23, 30; `file 17` pp.50, 61):** Profile waypoints (55, 70, ..., 2,000, 3,000 ft) are AMSL; acoustic distances use height above the 20 ft runway plane. **Model choice:** 0.5 km is the airport's first assessment point, and no estimate is plotted closer. Aircraft are still descending before the threshold: the flare and touchdown come after it. |
| Default thrust difference relative to 3° data | `+0.9 dB` vs E190; `+0.1 dB` vs E190-E2; `+0.2 dB` vs E195-E2 and A220 | **Estimate, not a measurement; slopes from `file 19` Appendix I:** Certificates and the Reagan National data are on about `3.0°`, so adjusting to `4.49°` vs `5.5°` requires `ΔL_base(3°→5.5°) − ΔL_A320(3°→4.49°)`. Assuming constant speed and drag, an E190 at 43 t sheds `18.3 kN` (`2,062 lbf/engine`) from `3°` to `5.5°`, quieting by `1.20–1.55 dB` (`CF34-10E`, p.747), while an A320 at 66.3 t sheds `16.9 kN` (`1,896 lbf/engine`) from `3°` to `4.49°`, quieting by `0.34–0.51 dB` (`CFM56-5A`/`V2527-A5`, pp.753, 793), giving `+0.7 to +1.2 dB`. About half the E190 thrust range is below the table's 3,000 lbf. No NPD data here covers neo, PW1500G or PW1900G engines, so the E2 and A220 defaults assume an A320-like slope, which gives about `−0.1 to +0.4 dB`. That assumption is untested: the airport's proxies have steeper slopes (see the bands below). |
| Where the thrust difference applies | Up to `3.7 nm`, or the `5.5°` top of descent if nearer (`3.32 nm` on RWY 09); hatched beyond | **Model choice (`file 19` pp.189, 198, 221; `file 02` p.8):** The estimate compares aircraft in landing configuration. In Doc 29 default profiles the `A320-211` is on landing flap from about `1,820 ft`, which is `3.7 nm` on `4.49°`, and the `EMB190` from `1,500 ft`, which is `2.5 nm` on `5.5°`. From `2.5` to `3.7 nm` the E190 may still be at idle while the A320neo isn't, so the difference could be larger than the default. Beyond that point no estimate is made: the area is hatched, a thin dotted line leaves thrust out, and it isn't treated as zero. These are 3° defaults, the `737500` profile has no idle steps, and Annex C says London City's profiles are custom, so the limit is a reasonable reading rather than a sourced value. |
| Certificate baseline ("EASA" scenarios) | A320neo 66.3 t midpoint (92.35 EPNdB) | **Model choice (`files 09, 10, 18`):** Uses the A320neo's lowest listed landing mass (66.3 t: PW1100G 92.0–92.3, LEAP-1A 92.5–92.7, midpoint 92.35 EPNdB) minus each Chapter 4+ certificate: E190 `−0.15`, E190-E2 `+0.95`, E195-E2 `+0.65`, A220-100 `+0.45 dB`. Using an `EPNdB` difference as a `dB(A)` difference is an assumption: `EPNdB` adds tone corrections and a different frequency weighting, and includes duration (`10 log(V_A320 / V_base)` alone is `~0.1–0.3 dB`). The difference is also held constant with distance, while in `file 19` the A320ceo minus E190 gap falls about `1.2–2.5 dB` from 200 to 4,000 ft. |
| Measured baseline ("Measured" scenarios) | E190 `−2.0`, A220 `+2.5 dB` | **Measured, at another airport (`file 08`):** Arrivals at Reagan National, LAmax, on typical approach angles. Weights, engine variants and flight settings aren't reported. The monitors are 3.1–7.1 km from the airport, but the figure is applied unchanged from 0.5 km. The A220 figure is a small sample, 19 arrivals each in one month. Uses the same thrust estimate as the EASA scenarios, although some of these measurements may be from before landing configuration. |
| Monitor 6 baseline ("Monitor 6" scenarios) | E190 minus type: A220 `+0.5` LAmax, `+0.1` SEL; E190-E2 `+2.1` LAmax, `+2.2` SEL | **Measured at London City (`file 21`, Table 3), added to an A320neo minus E190 figure:** No source measures the A320neo at London City, so that part comes from elsewhere. The sliders and chart line use the certificates (`−0.15 dB`), to match the default E190 scenario, and the description also gives the result from Reagan National (`−2.0 dB`). Both aircraft were measured on the 5.5° approach, so only the E190's thrust estimate (`+0.9 dB`) is used, not one for the other type. The evidence range is the E190's, shifted by the gap. The gap comes from one place, about 3 km from the threshold, and is applied unchanged at every distance. The E190 and E195-E2 scenarios don't use monitor 6: the E195-E2 wasn't measured. |
| Evidence range (shaded) | Height + air, plus band extremes | **Model choice:** Adds the low ends and the high ends of the two bands below, at full width at every distance, because a missing thrust estimate isn't a known zero. Where the E190 is level and the A320neo still descending, the low end uses `−2 dB` (`73 vs 71 dB SEL` at 4,000 ft, `file 01` Figure 22, p.32). It is an outer limit that combines unrelated sources, not a confidence interval. The chip describes the selected value, and a note beside it says whether the range crosses no change or 3 dB. |

## Arrivals measured at London City

From `file 21`, by Bickerdike Allen Partners, who also wrote `file 02`. RWY 27 arrivals overfly NMT6 (p.9), and these are real arrivals on the 5.5° approach, so they include actual thrust, configuration and weights. There are no A320neo figures, because it can't yet fly there. The report gives no spread for these averages.

| NMT6 arrivals (Table 3, p.8) | Flights | LAmax | SEL | Difference from E190, LAmax | Difference from E190, SEL | Certificates (EPNdB, 3°) | Airport's table at 3 km (SEL) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Embraer E190 | 955 | 74.8 | 83.8 | | | | |
| Airbus A220-100 | 53 | 74.3 | 83.7 | −0.5 | −0.1 | −0.6 | −3.0 |
| Embraer E190-E2 | 15 | 72.7 | 81.6 | −2.1 | −2.2 | −1.1 | −2.5 |

The differences are calculated here. The certificates match the A220's LAmax difference and understate the E190-E2's by about 1 dB, on only 15 flights. The airport's A220 difference is 2.9 dB larger than NMT6 shows in SEL, though its fit is across NMTs 1–6 (`file 02` pp.9–10), so one monitor doesn't test all of it. NMT6 is about 3 km from the RWY 27 threshold, read from the map in `file 02` Figure 1.

## Thamesmead garden

The Thamesmead survey site in `file 21`, around 4 km from the RWY 27 threshold and around 500 m north of the arrival path (pp.4–5). It was a temporary monitor, not one of the airport's NMTs. RWY 09 arrivals don't fly near it, so the scenario is RWY 27 only. Because it isn't under the path, its gaps between aircraft aren't used to test the Monitor 6 scenarios.

| Arrivals at the site (Table 1, p.6) | Flights | LAmax | SEL |
|---|---:|---:|---:|
| Embraer E190 | 1,009 | 63.0 | 72.9 |
| Airbus A220-100 | 48 | 62.1 | 71.1 |
| Embraer E190-E2 | 12 | 61.3 | 70.5 |
| **A320neo, estimated here** | | **64.5** (61.1 to 67.2) | **74.1** (70.7 to 76.8) |
| A320neo, estimated from Reagan National's −2.0 dB | | 62.7 | 72.3 |

**Method (model choice):** The A320neo level is the E190's measured level plus the "EASA: E190" difference (`−0.15 dB` aircraft, `+0.9 dB` thrust), with height and air worked out over the straight-line distance to a listener 500 m to the side. At 4 km that makes height + air `+0.8 dB` LAmax and `+0.5 dB` SEL, against `+2.1` and `+1.3 dB` directly below the path. The bracketed range is the usual evidence range. These are per-flight averages, not the loudest flights, and no A320neo has been measured there.

**Limits:**

- The aircraft and thrust differences aren't specific to a listener beside the path.
- The 500 m is the report's rounded figure. At 300 or 700 m the height part alone is `0.95` or `0.34 dB` LAmax, against `0.55 dB` at 500 m.
- Doc 29 lateral attenuation isn't included. It would lower the difference by about `0.1 dB`, because the lower A320neo is seen at a shallower angle, `33°` against `38°` (`file 19`, equations 2.7.40–2.7.43, p.80).
- Departures on RWY 09 fly over the site and are louder (E190 `74.8` LAmax, `84.5` SEL, Table 2, p.6), but the model doesn't estimate them.

## Where the evidence disagrees

| A320neo minus E190 at 2 km, RWY 27 | SEL |
|---|---:|
| EASA scenario defaults | `+1.8 dB` |
| Measured scenario defaults | `−0.1 dB` |
| Measured difference with no thrust term | `−1.0 dB` |
| Airport's table (`file 01`, Figure 17) | `−1.3 dB` |

The airport's E190 curve uses 737-500 data but is fitted at London City's noise monitors, while its A320neo curve is unadjusted AEDT data (`file 02`, pp.9–12). The measured difference with no thrust term is closest to it. That closeness doesn't settle which is right, since the measured figure is LAmax from another airport.

The E190–A220 gap also differs by source: about `4.7 dB` measured at Reagan National (`65.0` vs `62.8`, and `62.0` vs `59.5 dB`, all at its NMT 6), `0.5 dB` LAmax and `0.1 dB` SEL measured at London City's NMT6 (`file 21`), `3.0 dB` in the airport's tables and `0.6 dB` on certificates. The model doesn't treat any of these as correct by default.

## SEL and LAmax against distance

Combining geometric spreading (`20 log` for `LAmax`, `10 log` lossless line-integral scaling for `SEL`) with the 24-band `file 19` Class `205` spectral atmosphere matches how the airport's A320neo level falls with height. This tests the fall with height only, not the difference between aircraft types.

| Basis | Effective SEL slope with height | Note |
|---|---:|---|
| Pure lossless line integral (`file 19`, Eq. E-8) | `10 log` | No atmospheric absorption or finite-segment effects |
| Boeing 747 lateral-attenuation duration coefficient (`file 20`, Table 1, p.8) | `11.6 log` before air | Lateral flyover test (`c = 8.4`), not an approach |
| Model (`10 log` + `file 19` Class `205` spectral air, height above the runway) | `13.2 log` (0.5–2.5 km), `13.9 log` (0.5–5 km); about `12–16 log` locally | Compared with the `CF3410E` NPD table above |
| Airport's A320neo SEL table (`file 01`, Figure 17), height above the runway | `13.6 log` (0.5–2.5 km), `14.5 log` (0.5–5 km) | AEDT 3g output, including spectral air and profile thrust |

## Altitude waypoints and place names

The RWY 27 and RWY 09 altitudes in `sketch.js` are in **feet AMSL** (`file 01`, Figure 8 p.22 and Figure 9 p.23). Runway elevation is `20 ft` AMSL (`file 01`, section 3.7.8, p.11), and threshold crossing heights are `35 ft` on the `5.5°` ILS and `50 ft` on the `4.49°` RNP-AR above threshold (`file 17`, pp.50, 61), giving `55 ft` and `70 ft` AMSL at `0.0 nm`.

Two misprinted chart labels in `file 01` (repeated in `file 16`, Figures 7–8, p.15) are corrected to match the `4.49°` slope and `file 17`:
- **RWY 27 at 1 nm:** Figure 9 prints `574 ft` (a digit transposition of `547 ft`); `sketch.js` uses `547 ft`, matching Figure 8 and `file 17` (pp.49, 60).
- **RWY 09 at 3.32 nm (`Curr TOD`):** Figure 8 prints `1,692 ft`; `sketch.js` uses `1,656 ft`, matching the `4.49°` slope and `file 17` p.49 ("circa 340ft" below 2,000 ft).
- Note also a compass typo in `file 01` section 5.3.9 (p.23), which describes RWY 27's `Prop TOD` at the A13/A1306 junction as `"west of"` `Curr TOD` at Rainham Marshes when it lies `1.1 nm` **east** of `Curr TOD` (copied from RWY 09's section 5.3.5).

RWY 27 place names (`file 01`, Figure 9 p.23):

| Marker | Name in model | Basis |
|---|---|---|
| Threshold (0.0 nm) | Woolwich | Map label in Figure 9 (North Woolwich at the threshold, Woolwich immediately south across the river) |
| 1 nm | Thamesmead | Map label in Figure 9 |
| 2 nm | Abbey Wood | Map label in Figure 9 |
| 3 nm | Belvedere | Map label in Figure 9 |
| 4 nm | Erith Marshes | South/west bank of Erith Reach (`51.5021° N, 0.1720° E`) at the 4 nm pin in Figure 9's 2D plan view, ~300 m west of where the centreline crosses the Thames to Rainham Marshes |
| 5.03 nm (`Curr TOD`) | Rainham Marshes | Map label in Figure 9 and section 5.3.9 |
| 6.14 nm (`Prop TOD`) | Purfleet | Map label at the eastern end of Figure 9 (near the A13/A1306 junction, section 5.3.9) |

RWY 09 place names (`file 01`, Figure 8 p.22; note arrivals join from a turn near Tower Bridge around 4 nm, so the straight ground track is a simplification beyond that point):

| Marker | Name in model | Basis |
|---|---|---|
| Threshold (0.0 nm) | Silvertown | Map label in Figure 8, just south of the threshold |
| 1 nm | Royal Victoria | West end of Royal Victoria Dock at the 1 nm mark in Figure 8 |
| 2 nm | Blackwall | Map label in Figure 8 |
| 3 nm | Limehouse | Map label in Figure 8, just north of the marker |
| 3.32 nm (`Curr TOD`) | Rotherhithe Tunnel | Section 5.3.5, p.22 |
| 4.05 nm (`Prop TOD`) | Wapping | Section 5.3.5, p.22 |

## Proposed approach angle by stage

| Stage | RWY 09 | RWY 27 | Where |
|---|---:|---:|---|
| Stage 2 (2025) | 4.49°–4.40° | 4.49°–4.05°; a second option at 4.05°–3.75° | `17_LCY_Stage2_Develop_and_Assess_V1.1.pdf`, pp.49, 60, 71 |
| Stage 3 consultation (2026) | 4.49° | 4.49° | `01_LCY_Stage3_Consultation_Document_Issue1.1.pdf`, section 4.4.1; p.14 |
| Stage 4 final proposal (July 2026) | 4.49° | 4.49° | `16_LCY_Stage4_Airspace_Change_Proposal_Issue1.0.pdf`, section 2.7, p.6 |

## Ranges marked under the sliders

| Band | Range | Basis |
|---|---:|---|
| Source, vs E190 | −2.2 to +0.9 dB | Low end: −2.2 dB LAmax measured on arrival at Reagan National's monitor 6 in 2024–25 (`file 08`, Table 5, p.8; the three monitors give 1.8–2.2 dB, and monitor 17's 1.8 dB has only `n = 8` A320neo arrivals). High end: A320neo 92.7 vs E190 92.5 EPNdB gives +0.2, or +0.9 with the Flap 06 inhibitor records at 91.8 (`files 09, 10`). |
| Source, vs E190-E2 | +0.6 to +1.3 dB | Certificates: A320neo at 66.3 t, 92.0–92.7, vs E190-E2 91.4 EPNdB (`files 09, 10`). |
| Source, vs E195-E2 | +0.3 to +1.0 dB | Certificates: A320neo at 66.3 t, 92.0–92.7, vs E195-E2 91.7 EPNdB (`files 09, 10`). |
| Source, vs A220 | +0.1 to +2.5 dB | Certificates: A320neo at 66.3 t, 92.0–92.7, vs A220-100 91.9 EPNdB gives +0.1 to +0.8 (`files 09, 18`). High end: 62.0 vs 59.5 dB LAmax at Reagan National in Jan 2022, 19 flights each, which `file 08` calls a snapshot (Table 6, p.9). It comes from the same monitor as the E190's −2.2 dB, where the A320neo reads similarly in both periods (62.0 and 62.8 dB). |
| Source, Monitor 6 scenarios | E190 band plus the measured gap | vs A220: −1.7 to +1.4 LAmax, −2.1 to +1.0 SEL. vs E190-E2: −0.1 to +3.0 LAmax, 0.0 to +3.1 SEL (`file 21`, Table 3). These scenarios use the E190's thrust band. Across all scenarios, the aircraft slider spans −4.0 dB to +3.5 dB. |
| Thrust, vs E190 | −0.45 to +2.5 dB | Low end: spoiler drag cancels all E190 relief, leaving the A320's mid relief of about 0.45 dB. Middle: `+0.7 to +1.2 dB` from `file 19` NPD slopes (`+0.9 dB` default). High end: `file 12`'s AEDT example implies `1.7–3.0 dB` of E190 relief, which gives `+1.25 to +2.55 dB` net. |
| Thrust, vs E190-E2 and E195-E2 | −0.45 to +1.4 and +1.6 dB | Low end as above. High end: the slope of the airport's proxy engine for this family, the EMB190's `CF34-10E`, scaled by each type's mass. Defaults `+0.1` and `+0.2 dB` assume an A320-like slope. |
| Thrust, vs A220 | −0.45 to +2.7 dB | Low end as above. High end: the slope of the airport's proxy, the 737-500's `CFM56-3` (`1.07–1.17 dB` per 1,000 lbf at 1,000 ft, `file 19` Appendix I), over `2,621 lbf/engine`, minus the A320's relief. This isn't the A220's engine, so it is an outer limit under the same rule as the E2 family. The `+0.2 dB` default assumes an A320-like slope. Across all scenarios, the slider spans −1.5 dB to +3.0 dB. |

The bands combine different metrics and operating conditions, so they indicate plausible evidence bounds rather than statistical confidence intervals.

## Evidence on the thrust effect

At 66.3 t, maintaining constant speed and drag on a `4.49°` glideslope instead of `5.5°` requires `sin 5.5° − sin 4.49° = 0.0176` of aircraft weight, or `11.4 kN` total (`1,284 lbf` per engine). Relative to `3.0°` certification, an E190 at 43 t on `5.5°` sheds `18.3 kN` (`2,062 lbf/engine`) while an A320neo at 66.3 t on `4.49°` sheds `16.9 kN` (`1,896 lbf/engine`).

| File | What it gives | What it implies for LCY (4.49° vs 5.5°, and relative to 3° certificates) |
|---|---|---|
| `19_EU_Directive_2015-996_Doc29_Noise_Method.pdf` | 2015 ANP approach NPD tables at 2,000–6,000 lbf/engine: `A320-211` (`CFM56-5A`, pp.753–754) `0.18–0.21 dB` per 1,000 lbf; `A320-232` (`V2527-A5`, pp.793–794) `0.21–0.27 dB` per 1,000 lbf; `EMB190` (`CF34-10E`, p.747) `0.58–0.75 dB` per 1,000 lbf. | Same-type `5.5° → 4.49°`: **`+0.23 to +0.35 dB`** (A320) and **`+0.48 to +0.62 dB`** (E190). Differential from `3.0°` reference data: **`+0.7 to +1.2 dB`** for A320 vs E190 (`+0.9 dB` default). |
| `12_LCY_Aircraft_Noise_Categorisation_Scheme_March2022.pdf` | AEDT example for the E190 at 2,000 m from threshold: `93.3 EPNdB` at `3°` vs `87.9 EPNdB` at `5.5°`, a `5.4 EPNdB` difference (pp.6, 11, 33). It is unclear whether AEDT changed thrust between the two runs. | With 35 ft (10.7 m) TCH (`file 17`, p.50), overhead heights at 2,000 m are 115.5 m (`3°`) vs 203.2 m (`5.5°`). Height + air (`~10–15 log`) accounts for `2.4–3.7 EPNdB`, leaving `1.7–3.0 EPNdB` of other E190 relief from `3°` to `5.5°`. Subtracting the A320's `~0.45 dB` gives `+1.25 to +2.55 dB` net, above the NPD estimate, so this disagrees with `file 19` rather than confirming it. |
| `13_Heathrow_3.2deg_SSA_Trial_Report_2016.pdf` | Measured `3.2°` (actual `3.14°` in cold weather) vs `3.0°` across nine aircraft types at three monitors: mean `−0.5 dB` SEL (`−0.25, −0.49, −0.74 dB`; pp.12, 34, 48–49, 55–56). Most type and monitor differences are statistically significant (para 132). | Doesn't isolate thrust: the report names uncontrolled thrust, flap and gear settings and allows `0.4 dB` for instruments (p.56). The angle change is about `7×` smaller than London City's `1.01°`, so that allowance alone scales to about `±3 dB`. Reduction beyond height and air, scaled the same way: very roughly `+1.2 to +1.8 dB`. |
| `14_Heathrow_3.2deg_SSA_Trial_Report_2018.pdf` | Warm-weather trial (`3.24°` actual vs `3.0°`): also about `−0.5 dB` SEL (`−0.32, −0.55, −0.68 dB`; pp.5, 54, Table 16). `EA320NEO` appears in the statistical tables (pp.49, 51, 53) with only 10–11 RNAV events. | Calculated the same way: about `0 to +0.5 dB`, `±1.7 dB` from the instrument allowance alone. The result barely changed although the angle change was 70% larger, so the two trials together can't pin down a thrust effect. |
| `15_NASA_Effect_of_Thrust_and_Altitude_in_Steep_Approaches.pdf` | 1967 four-engine pure turbojet: `~7.5 dB` unweighted `OASPL` change between `3°` (with `50°` flaps) and `6°` (with `0°` flaps); `19.4 dB` per `100,000 N` (`pp.4, 6`; `Table I, p.9`). | Scales to `2.0–2.5 dB` `OASPL`, an historical upper bound confounded by low-bypass jet dominance, unweighted `OASPL`, and `0°–50°` flap changes. |

## Assumptions behind the airport's arrival prediction

From `02_LCY_Annex_C_Aircraft_Noise_Technical_Report.pdf` unless stated.

| Assumption | Where |
|---|---|
| Predictions come from the AEDT 3g model, not measurement | p.5 |
| E190 (`+1.5 dB`) and A220-100 (`−1.5 dB`) arrivals use AEDT `737-500` proxy data, so their arrival tables differ by exactly `3.0 dB` at every distance | Table 4, p.10; `file 01` Figs. 17–18 |
| **Inference:** The ANP default `737500` profile changes from `Flap D-15` to `Flap D-30` at `1,000 ft`, which is `3.0 km` on `5.5°`, and the E190 and A220-100 tables both drop `2.2 dB` between `3.0 km` and `5.0 km`. The `EMB190` default changes at `1,500 ft` (`4.6 km`), and the E190-E2 table steps at about that point. This is a plausible cause, but those defaults are for 3° and `file 02` p.8 says London City's profiles are custom. | `file 19`, pp.189, 221 |
| The model plots the airport's table only over its published `0.5–5.0 km` (`0.27–2.70 nm`) range and cites `file 01` Figure 22 (p.32) for level flight | `file 01`, pp.30–32 |
| One calibration offset per type and operation, fitted at noise monitors 1–6 | pp.9–10 |
| A320neo uses AEDT data with no local adjustment; measured data from other airports was considered and not used | pp.11–12 |
| A320neo flies London City's existing profiles, altered only for the `4.49°` final approach | pp.8, 12 |
| Thrust is estimated from weight, altitude and speed; weight is estimated from destination; no thrust values, flap schedules or weather settings are published | p.7 |
| Only the A320neo uses `4.49°`; all other types stay at `5.5°` | p.41; Stage 4 draft rule change limits it to authorised A320neo operators (`file 16`, p.33) |
| Other types on `4.49°`: under `2 dB`, from height and `6 dB` per doubling only | p.41 |
| Lateral tracks and dispersion do not change | p.6 |
| Differences under `3 dB` are treated as generally not noticeable | `file 01`, section 5.4.11, p.30 |

## Not saved

The UK CAA noise sheet originally noted for E190-E2 was not obtained; the same `91.4 EPNdB` is verified in `file 10` above.

ECAC Doc 29 4th edition itself was not downloaded from ECAC; `file 19` (Commission Directive (EU) 2015/996, including the 2015 ANP database in Appendix I) is used instead. Later Commission Delegated Directive amendments and proprietary AEDT 3g neo-engine NPD tables (`PW1100G` / `LEAP-1A`) were not obtained. ISO 9613-2 and SAE ARP 866A are paid standards and were not obtained.

## Where each file came from

- **01–07:** London City Airport, RNP-AR consultation: https://consultations.airspacechange.co.uk/london-city-airport/rnp-ar-approaches/
- **08:** Aviation Environment Federation: https://www.aef.org.uk/uploads/2025/12/Noise-Lessons-for-London-City-Airport-1.pdf
- **09:** EASA: https://www.easa.europa.eu/en/downloads/139012/en
- **10:** EASA: https://www.easa.europa.eu/en/downloads/8275/en
- **11:** EASA: https://www.easa.europa.eu/en/downloads/8289/en
- **12:** London City Airport noise categorisation scheme: https://gat04-live-1517c8a4486c41609369c68f30c8-aa81074.divio-media.org/filer_public/67/94/6794b25f-cf1c-486a-b4cc-865ad2377c38/approved_cadp1_condition_18_2022_ancs_update_.pdf
- **13–14:** Heathrow Airport: https://www.heathrow.com/content/dam/heathrow/web/common/documents/company/local-community/noise/reports-and-statistics/reports/operational-trial-reports/slightly-steeper-approach-trial/
- **15:** NASA Technical Reports Server: https://ntrs.nasa.gov/api/citations/19680001785/downloads/19680001785.pdf
- **16–17:** CAA airspace change portal, ACP-2025-003: https://airspacechange.caa.co.uk/PublicProposalArea?pID=695
- **18:** EASA: https://www.easa.europa.eu/en/downloads/20962/en
- **19:** legislation.gov.uk copy of Commission Directive (EU) 2015/996: https://www.legislation.gov.uk/eudr/2015/996/pdfs/eudr_20150996_adopted_en.pdf
- **20:** NASA Technical Reports Server: https://ntrs.nasa.gov/api/citations/19820003987/downloads/19820003987.pdf
- **21:** London City Airport: https://assets.ctfassets.net/lmkdg513arga/1dAp1OIK1za3G7I6ogmvX5/cd18f1a9a3b47a9ae987239abdb153e2/London_City_Airport__Aircraft_Noise_Survey_-_Thamesmead.pdf
