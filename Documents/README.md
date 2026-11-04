# Source documents for the London City approach noise model

Downloaded 4 November 2026. Page numbers are PDF page numbers, not the numbers printed on the page.

## Documents the model's figures or the analysis rely on

| File | What was taken from it | Where |
|---|---|---|
| `01_LCY_Stage3_Consultation_Document_Issue1.1.pdf` | The airport's arrival table: A320neo at 4.49° vs other types at 5.5°, dB(A) SEL, 0.5–5 km. This is the data behind the four "Airport" scenarios. | RWY 27 Figure 17, p.30; RWY 09 Figure 18 and the "not noticeable" statement, p.31 |
| `02_LCY_Annex_C_Aircraft_Noise_Technical_Report.pdf` | E190 and A220-100 arrivals modelled with AEDT 737-500 data (+1.5 and −1.5 dB) | Table 4, p.10 |
| | A320neo noise based on AEDT data | p.12 |
| | "Quieter per arrival at most locations"; "slightly louder" than other new-generation types | p.19 |
| | 6 dB per doubling of distance; about 20% lower gives under 2 dB | p.41 |
| `03_LCY_Consultation_FAQ_Week8.pdf` | Arrival differences described as not likely to be perceptible, with altitude accounted for | Section 2.5.5, p.3 |
| `04_LCY_Consultation_Summary_Document.pdf` | The airport's qualitative noise summary | Noise summary section |
| `08_AEF_Noise_Lessons_for_London_City_Airport.pdf` | Certification comparison; measured arrivals at Reagan National (LAmax, 1.8–2.2 dB) | Table 4, p.6; Table 5, p.8 |
| | Reproduction of the airport's Stage 2 arrival tables, which match Stage 3 | Table 7, p.10 |
| | "Doubling or halving the altitude results in a 10dBA" change in LAmax, given as a general rule with no reference | p.9 |
| `09_EASA_TCDSN_A.064.3_A320_Issue42.pdf` | A320neo certified approach levels | A320-251N from p.175; A320-271N from p.226 |
| `10_EASA_TCDSN_IM.A.071_ERJ190_Issue24.pdf` | E190 certified approach levels; E190-E2 (ERJ 190-300) and E195-E2 (ERJ 190-400) | ERJ 190-100 STD from p.78; ERJ 190-300 from p.190 |
| `11_EASA_TCDSN_A.064_Cover_Issue93.pdf` | Confirms A320 models are in Volume 3 | p.2 |
| `18_EASA_TCDSN_IM.A.570_BD500_A220_Issue14.pdf` | A220-100 certified approach level | BD-500-1A10 records, pp.3–5 |
| `19_EU_Directive_2015-996_Doc29_Noise_Method.pdf` | The Doc 29 aircraft noise method as adopted in 2015. Exposure over an infinite flight path is proportional to distance over speed times peak squared pressure, which gives 10 log for SEL against 20 log for peak. The text says real data don't necessarily follow this and calls the algorithm semi-empirical. | Appendix E, equation E-8 and section E3, pp.122–123 |
| | Average atmospheric attenuation rates in the notional AIR-1845 atmosphere: 0.131, 0.295 and 0.590 dB/100 m at 250, 500 and 1,000 Hz, which is 0.4, 0.9 and 1.8 dB/1,000 ft | Appendix D, Table D-1, p.118 |
| `20_NASA_TM83214_SEL_EPNL_Duration_Coefficients.pdf` | Contouring programs assumed a duration coefficient of 10, so SEL falls 10 log. Measured: 8.4 for a Boeing 747 and 5.5 for a T-38, and 6 was recommended after tests on military aircraft. SEL then falls by 20 minus the coefficient: about 11.6 log for the 747. These are lateral attenuation flights, not approaches. | pp.3–6, Table 1 |

## Certified approach levels extracted from the EASA sheets

| Aircraft | Landing mass | Approach (EPNdB) |
|---|---:|---:|
| A320neo, LEAP (A320-251N/252N/253N) | 66,300 kg | 92.5–92.7 |
| | 67,400 kg | 92.7–92.8 |
| | 68,400 kg | 92.9 |
| A320neo, PW1100G (A320-271N/272N/273N) | 66,300 kg | 92.0–92.3 |
| | 67,400 kg | 92.2–92.4 |
| | 68,400 kg | 92.3–92.6 |
| E190 (ERJ 190-100 STD, LR, SR): Block 2, improved chevron nozzle | 43,000 kg | 92.5 (used in the model) |
| E190: Block 2, improved chevron nozzle and Flap 06 inhibitor | 43,000 kg | 91.8 (not used) |
| E190: improved chevron nozzle, not listed as Block 2 | 43,000 kg | 92.4 |
| E190: low-loss chevron nozzle | 43,000 kg | 92.7 |
| E190 IGW: low-loss chevron nozzle | 43,000–44,000 kg | 92.8 |
| E190-E2 (ERJ 190-300) | 49,050 kg | 91.4 |
| E195-E2 (ERJ 190-400) | 54,000 kg | 91.7 |
| A220-100 (BD-500-1A10; PW1519G, PW1521G, PW1524G) | 54,658 kg | 91.9 |

These were extracted by script from the PDF text and are ranges across all listed records. They were re-extracted and matched on 4 November 2026. The AEF report quotes other NoisedB values in Table 4, p.6: A220 91.5 and A320neo 92.1–92.3. The model uses the EASA sheets. The airport's example E190 (flyover 81.9, sideline 91.7, approach 92.5 EPNdB; file 12, p.33) matches EASA records A19104, A19555, A19112 and A19556. The sources don't say which E190 modifications or which A320neo engine would be used at London City. Certification figures are in EPNdB and come from standard certification test conditions, not London City's approach angles.

## Searched, with no figure used

| File | Why it is here |
|---|---|
| `05_LCY_Full_Options_Appraisal_Issue1.0.pdf` | Searched for a 2.5 dB figure and E190 arrival comparisons; none found |
| `06_LCY_Consultation_Response_Document_Issue1.0.pdf` | Searched for a 2.5 dB figure and E190 arrival comparisons; none found |
| `07_LCY_Stage3_Response_Addendum.pdf` | Searched for a 2.5 dB figure; none found |

## Values in the model with no source document

| Value | Used in | Status |
|---|---|---|
| +1.2 dB thrust/config | All four "EASA" scenarios | Assumed, about the middle of the 0 to 2.5 dB range; no document here gives this figure. See "Evidence on the thrust effect" |
| 0.6 dB per 1,000 ft atmospheric absorption | All model curves | Assumed; no document here gives this figure. File 19 gives 0.4 at 250 Hz, 0.9 at 500 Hz and 1.8 at 1 kHz, so it may be low for A-weighted aircraft noise. At the largest height gap, 528 ft, 0.6 gives 0.3 dB and 1.8 would give 1.0 dB. |
| Thrust term fades to zero over 0.3 nm around the 5.5° top of descent | Thrust slider | Model choice. Spread over a distance because noise doesn't change at a single point. No thrust difference is modelled beyond that point, although the E190 is level there and the A320neo still descending. |
| Certificate comparison | All four "EASA" scenarios | The A320neo at its lowest listed landing mass, 66.3 t (92.0–92.7 across both engines, midpoint 92.35), minus the other type: E190 92.5 gives −0.15, E190-E2 +0.95, E195-E2 +0.65, A220 +0.45. Choosing 66.3 t assumes London City landings are nearer the lowest listed mass; no document gives typical weights. The midpoint is a simple choice for an unknown engine, not a sourced method. These replace an earlier midpoint method (92.45, with E190 92.3), which mixed landing masses and included the Flap 06 inhibitor records. |

## SEL against distance

The model uses 10 log plus air. This now has a source (files 19 and 20), but it is the theoretical value and the evidence points to a steeper fall:

| Basis | Fall with height | Note |
|---|---:|---|
| Model, 1–4 km on the 4.49° path | about 11 log | 10 log plus 0.6 dB/1,000 ft |
| Boeing 747 duration coefficient (file 20) | about 11.6 log, plus air | Not an approach |
| Airport's A320neo SEL table, Figure 17 (file 01), fitted against 4.49° height | about 15 log | 14.4 log from 0.5 to 2.5 km. Modelled, and includes air and any thrust change along the path |

The 14.4 log used in the Heathrow calculation below is that near-threshold fit. Using about 15 log instead of the model's SEL height term would add about 0.1–0.3 dB.

## Altitude waypoints

The RWY 27 altitudes in `sketch.js` come from `01_LCY_Stage3_Consultation_Document_Issue1.1.pdf`, Figure 9, p.23. That figure labels the proposed 1 nm altitude as 574 ft; the model uses 547 ft, which matches the 4.49° slope and the 1 nm label in Figure 8, p.22. The 5.03 nm and 6.14 nm descent points and the 55 ft and 70 ft threshold heights were not found in the document text, but are consistent with the slopes.

The RWY 09 altitudes come from Figure 8, p.22, where the final descent starts from 2,000 ft. That figure labels the 4.49° altitude at the current descent point as 1,692 ft; the model uses 1,656 ft, which matches the slope. The airport's own text also puts the gap at that point at "slightly more than 300ft". The 3.32 nm and 4.05 nm descent points are calculated from the slopes and match the airport's stated gap of about 0.7 nm.

RWY 09 arrivals join the final approach from a turn near Tower Bridge (Figure 8), so distances beyond that turn are not on a straight line under the approach.

RWY 09 place names, all from `01_LCY_Stage3_Consultation_Document_Issue1.1.pdf`, p.22:

| Marker | Name in model | Basis |
|---|---|---|
| Threshold | Silvertown | Map label in Figure 8, just south of the threshold |
| 1 nm | Royal Victoria | Not labelled; read from the marker's position at the west end of the dock in Figure 8 |
| 2 nm | Blackwall | Map label in Figure 8 |
| 3 nm | Limehouse | Map label in Figure 8, just north of the marker |
| 3.32 nm (current descent point) | Rotherhithe Tunnel | Section 5.3.5 |
| 4.05 nm (proposed descent point) | Wapping | Section 5.3.5 |

## Proposed approach angle by stage

| Stage | RWY 09 | RWY 27 | Where |
|---|---:|---:|---|
| Stage 2 (2025) | 4.49°–4.40° | 4.49°–4.05°; a second option at 4.05°–3.75° | `17_LCY_Stage2_Develop_and_Assess_V1.1.pdf`, pp.49, 60, 71 |
| Stage 3 consultation (2026) | 4.49° | 4.49° | `01_LCY_Stage3_Consultation_Document_Issue1.1.pdf`, section 4.4.1; background p.14 |
| Stage 4 final proposal (July 2026) | 4.49° | 4.49° | `16_LCY_Stage4_Airspace_Change_Proposal_Issue1.0.pdf`, section 2.7, p.6 |

The model uses 4.49° on both runways. Stage 2 also gives about 340 ft lower than 2,000 ft at the current RWY 09 descent point for 4.49° (p.49), which supports the 1,656 ft used in the model over the 1,692 ft label. It gives 547 ft at 1 nm for 4.49° (pp.49, 60), which supports the correction of the 574 ft label. Stage 4 repeats both labels (Figures 7 and 8, p.15).

## Ranges marked under the sliders

| Band | Range | Basis |
|---|---:|---|
| Source, vs E190 | −2.0 to +0.3 dB | Low end: about −2 dB LAmax measured on arrival at Reagan National (file 08, Table 5, p.8). High end: least favourable certificate pairing at 66.3 t, A320neo 92.7 vs E190 92.4 EPNdB, leaving out the Flap 06 inhibitor records (files 09, 10). |
| Source, vs E190-E2 | +0.6 to +1.3 dB | Certificates: A320neo at 66.3 t, 92.0–92.7, vs E190-E2 91.4 EPNdB (files 09, 10). |
| Source, vs E195-E2 | +0.3 to +1.0 dB | Certificates: A320neo at 66.3 t, 92.0–92.7, vs E195-E2 91.7 EPNdB (files 09, 10). |
| Source, vs A220 | +0.1 to +2.5 dB | Certificates: A320neo at 66.3 t, 92.0–92.7, vs A220-100 91.9 EPNdB gives +0.1 to +0.8 (files 09, 18). High end: 62.0 vs 59.5 dB LAmax on arrival at Reagan National, 19 flights each (file 08, Table 6, p.9). |
| Thrust | 0 to 2.5 dB | 0 is a lower limit, not a finding, because a shallower descent needs more thrust unless drag or speed also changes. About 2.5 is an upper limit from a turbojet study. See "Evidence on the thrust effect" below. |

The source bands combine different metrics and conditions, so they show a plausible range and not a statistical confidence interval.

## Evidence on the thrust effect

None of these documents gives a thrust penalty for 5.5° to 4.49°. The London City and NASA figures below are calculated from them, and the assumptions are stated.

| File | What it gives | What it implies for 5.5° to 4.49° |
|---|---|---|
| `12_LCY_Aircraft_Noise_Categorisation_Scheme_March2022.pdf` | AEDT example for the E190: 93.3 EPNdB at 3°, 87.9 EPNdB at 5.5°, a 5.4 EPNdB difference, at the 2 km certification point. The scheme says this method correlates well with turbofan measurements (p.11; example p.33; certification point p.6). | Height alone at 6 dB per doubling gives 4.8 dB (120 m vs 208 m, the same threshold height on a 5.5° path), leaving about 0.6 dB over 2.5°, or about 0.25 dB when scaled by thrust to 5.5° vs 4.49°. It is unclear whether AEDT changed thrust between the two runs. |
| `13_Heathrow_3.2deg_SSA_Trial_Report_2016.pdf` | Measured 3.2° vs 3.0° across nine aircraft types at three monitors: average about −0.5 dBA SEL. The aircraft averaged 3.14° because of low temperatures. The −0.7 dB the report expects assumes a true 3.2° (pp.55–56). It names thrust and flap settings only as uncontrolled variation, allows 0.4 dB for instrument error, and has event variability of 1.0–1.7 dB. | Doesn't isolate thrust and can't show that it is zero. Reduction beyond height and air, scaled by sin 5.5° − sin 4.49° against the angle change: about +1.2 to +1.8 dB (14.4 log and 10 log). The instrument allowance alone scales to about ±3 dB, and the conditions differ from London City's. |
| `14_Heathrow_3.2deg_SSA_Trial_Report_2018.pdf` | Second trial: average angle about 3.24° and also about −0.5 dBA SEL (pp.5, 54). Monitor averages: −0.32, −0.55, −0.68 dBA, against −0.25, −0.49, −0.74 in the first trial. | Calculated the same way: about 0 to +0.5 dB, ±1.7 dB from the instrument allowance alone. The result barely changed although the angle change was 70% larger, so scatter dominates at this scale. |
| `15_NASA_Effect_of_Thrust_and_Altitude_in_Steep_Approaches.pdf` | Four-engine turbojet, 1960s: about 7.5 dB from thrust between 3° and 6°; 19.4 dB per 100,000 N (p.6; aircraft p.4). | About 2.0–2.5 dB. Likely an upper bound, as turbojets are dominated by engine noise. |

Calculation: the extra thrust needed is sin 5.5° − sin 4.49° = 0.0176 of aircraft weight, about 10 kN in total at 60 tonnes. This ignores any change in speed, flap or spoiler setting.

The direct source would be A320neo and E190 noise-power-distance data from the ANP or AEDT databases, which was not obtained.

## Assumptions behind the airport's arrival prediction

From `02_LCY_Annex_C_Aircraft_Noise_Technical_Report.pdf` unless stated.

| Assumption | Where |
|---|---|
| Predictions come from the AEDT 3g model, not measurement | p.5 |
| E190 and A220-100 arrivals use AEDT 737-500 data, adjusted +1.5 and −1.5 dB | Table 4, p.10 |
| One adjustment per type and operation, fitted at noise monitors 1–6 | pp.9–10 |
| A320neo uses AEDT data with no local adjustment; measured data from other airports was considered and not used | pp.11–12 |
| A320neo flies London City's existing profiles, altered only for the 4.49° final approach | pp.8, 12 |
| Thrust is estimated from weight, altitude and speed; weight is estimated from destination; no thrust values are published | p.7 |
| Only the A320neo uses 4.49°; all other types stay at 5.5° | p.41; Stage 4 draft rule change limits it to authorised A320neo operators (file 16, p.33) |
| Other types on 4.49°: under 2 dB, from height and 6 dB per doubling only | p.41 |
| Lateral tracks and dispersion do not change | p.6 |
| Differences under 3 dB are treated as generally not noticeable | Consultation Document, p.30 |

A text search of files 01–04 found no mention of flap, landing gear, spoiler, engine variant, temperature, humidity or atmospheric conditions.

## Not saved

The UK CAA noise sheet cited for the "EASA: E190-E2" scenario was not obtained; the same 91.4 EPNdB appears on the EASA sheet above.

ECAC Doc 29 itself was not obtained: the fourth edition link at ECAC did not return the PDF. File 19 is used instead, as adopted in 2015. It has since been amended, and the amended text was not checked. ISO 9613-2 and SAE ARP 866A are paid standards and were not obtained.

## Where each file came from

- **01–07:** London City Airport, RNP-AR consultation: https://consultations.airspacechange.co.uk/london-city-airport/rnp-ar-approaches/
- **08:** Aviation Environment Federation: https://www.aef.org.uk/uploads/2025/12/Noise-Lessons-for-London-City-Airport-1.pdf
- **09:** EASA: https://www.easa.europa.eu/en/downloads/139012/en
- **10:** EASA: https://www.easa.europa.eu/en/downloads/8275/en
- **11:** EASA: https://www.easa.europa.eu/en/downloads/8289/en
- **12:** London City Airport noise categorisation scheme: https://gat04-live-1517c8a4486c41609369c68f30c8-aa81074.divio-media.org/filer_public/67/94/6794b25f-cf1c-486a-b4cc-865ad2377c38/approved_cadp1_condition_18_2022_ancs_update_.pdf
- **13–14:** Heathrow Airport: https://www.heathrow.com/content/dam/heathrow/web/common/documents/company/local-community/noise/reports-and-statistics/reports/operational-trial-reports/slightly-steeper-approach-trial/
- **15:** NASA Technical Reports Server: https://ntrs.nasa.gov/api/citations/19680001785/downloads/19680001785.pdf
- **18:** EASA: https://www.easa.europa.eu/en/downloads/20962/en
- **19:** legislation.gov.uk copy of Commission Directive (EU) 2015/996: https://www.legislation.gov.uk/eudr/2015/996/pdfs/eudr_20150996_adopted_en.pdf
- **20:** NASA Technical Reports Server: https://ntrs.nasa.gov/api/citations/19820003987/downloads/19820003987.pdf
- **16–17:** CAA airspace change portal, ACP-2025-003: https://airspacechange.caa.co.uk/PublicProposalArea?pID=695
