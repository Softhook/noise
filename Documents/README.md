# Source documents for the London City approach noise model

Downloaded 4 November 2026. Page numbers are PDF page numbers, not the numbers printed on the page.

## Documents the model's figures or the analysis rely on

| File | What was taken from it | Where |
|---|---|---|
| `01_LCY_Stage3_Consultation_Document_Issue1.1.pdf` | The airport's arrival table: A320neo at 4.49° vs other types at 5.5°, dB(A) SEL, 0.5–5 km. This is the data behind the "Airport figures" scenario. | RWY 27 Figure 17, p.30; RWY 09 Figure 18 and the "not noticeable" statement, p.31 |
| `02_LCY_Annex_C_Aircraft_Noise_Technical_Report.pdf` | E190 and A220-100 arrivals modelled with AEDT 737-500 data (+1.5 and −1.5 dB) | Table 4, p.10 |
| | A320neo noise based on AEDT data | p.12 |
| | "Quieter per arrival at most locations"; "slightly louder" than other new-generation types | p.19 |
| | 6 dB per doubling of distance; about 20% lower gives under 2 dB | p.41 |
| `03_LCY_Consultation_FAQ_Week8.pdf` | Arrival differences described as not likely to be perceptible, with altitude accounted for | Section 2.5.5, p.3 |
| `04_LCY_Consultation_Summary_Document.pdf` | The airport's qualitative noise summary | Noise summary section |
| `08_AEF_Noise_Lessons_for_London_City_Airport.pdf` | Certification comparison; measured arrivals at Reagan National (LAmax, 1.8–2.2 dB) | Table 4, p.6; Table 5, p.8 |
| | Reproduction of the airport's Stage 2 arrival tables, which match Stage 3 | Table 7, p.10 |
| `09_EASA_TCDSN_A.064.3_A320_Issue42.pdf` | A320neo certified approach levels | A320-251N from p.175; A320-271N from p.226 |
| `10_EASA_TCDSN_IM.A.071_ERJ190_Issue24.pdf` | E190 certified approach levels; E190-E2 (ERJ 190-300) and E195-E2 (ERJ 190-400) | ERJ 190-100 STD from p.78; ERJ 190-300 from p.190 |
| `11_EASA_TCDSN_A.064_Cover_Issue93.pdf` | Confirms A320 models are in Volume 3 | p.2 |

## Certified approach levels extracted from the EASA sheets

| Aircraft | Landing mass | Approach (EPNdB) |
|---|---:|---:|
| A320neo, LEAP (A320-251N/252N/253N) | 66,300 kg | 92.5–92.7 |
| | 67,400 kg | 92.7–92.8 |
| | 68,400 kg | 92.9 |
| A320neo, PW1100G (A320-271N/272N/273N) | 66,300 kg | 92.0–92.3 |
| | 67,400 kg | 92.2–92.4 |
| | 68,400 kg | 92.3–92.6 |
| E190 (ERJ 190-100 STD, LR, SR, IGW) | 43,000–44,000 kg | 91.8–92.8 |
| E190-E2 (ERJ 190-300) | 49,050 kg | 91.4 |
| E195-E2 (ERJ 190-400) | 54,000 kg | 91.7 |

These were extracted by script from the PDF text and are ranges across all listed records. Certification figures are in EPNdB and come from standard certification test conditions, not London City's approach angles.

## Searched, with no figure used

| File | Why it is here |
|---|---|
| `05_LCY_Full_Options_Appraisal_Issue1.0.pdf` | Searched for a 2.5 dB figure and E190 arrival comparisons; none found |
| `06_LCY_Consultation_Response_Document_Issue1.0.pdf` | Searched for a 2.5 dB figure and E190 arrival comparisons; none found |
| `07_LCY_Stage3_Response_Addendum.pdf` | Searched for a 2.5 dB figure; none found |

## Values in the model with no source document

| Value | Used in | Status |
|---|---|---|
| +1.2 dB thrust/config | "EASA + thrust" scenario | No document here gives this figure; see "Evidence on the thrust effect" |
| +1.0 dB thrust/config | "vs E190-E2" scenario | No document here gives this figure; see "Evidence on the thrust effect" |
| 0.6 dB per 1,000 ft atmospheric absorption | All model curves | No document here gives this figure |
| 10 log for SEL | All model curves in SEL | A rule of thumb with no document behind it |
| Thrust term fades to zero over 0.3 nm around the 5.5° top of descent | Thrust slider | Spread over a distance because noise doesn't change at a single point. No thrust difference is modelled beyond that point, although the E190 is level there and the A320neo still descending. |
| 91.8 EPNdB A320neo | "vs E190-E2" scenario | Marked "est." in the model; below every A320neo level on the EASA sheet |

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
| Source, vs E190 | −2.0 to +1.1 dB | Low end: about −2 dB LAmax measured on arrival at Reagan National (file 08, Table 5, p.8). High end: least favourable certificate pairing, A320neo 92.9 vs E190-100 91.8 EPNdB (files 09, 10). |
| Source, vs E190-E2 | +0.6 to +1.5 dB | Certificates: A320neo 92.0–92.9 vs E190-E2 91.4 EPNdB (files 09, 10). |
| Thrust | 0 to 2.5 dB | See "Evidence on the thrust effect" below. |

The source bands combine different metrics and conditions, so they show a plausible range and not a statistical confidence interval.

## Evidence on the thrust effect

None of these documents gives a thrust penalty for 5.5° to 4.49°. The London City and NASA figures below are calculated from them, and the assumptions are stated.

| File | What it gives | What it implies for 5.5° to 4.49° |
|---|---|---|
| `12_LCY_Aircraft_Noise_Categorisation_Scheme_March2022.pdf` | AEDT example for the E190: 93.3 EPNdB at 3°, 87.9 EPNdB at 5.5°, a 5.4 EPNdB difference, at the 2 km certification point. The scheme says this method correlates well with turbofan measurements (p.11; example p.33; certification point p.6). | Height alone at 6 dB per doubling gives 5.3 dB (121 m vs 221 m), leaving about 0.1 dB over 2.5°. It is unclear whether AEDT changed thrust between the two runs. |
| `13_Heathrow_3.2deg_SSA_Trial_Report_2016.pdf` | Measured 3.2° vs 3.0°, many A320-family flights: average about −0.5 dBA SEL, against about −0.7 dB expected from distance and air absorption alone (pp.55–56). | No clear extra thrust benefit, but the change is only 0.2° and the event-to-event variability is 1.0–1.7 dB. |
| `14_Heathrow_3.2deg_SSA_Trial_Report_2018.pdf` | Second trial: average also about −0.5 dBA SEL (p.5). | As above. |
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

The UK CAA noise sheet cited for the "vs E190-E2" scenario was not obtained; the same 91.4 EPNdB appears on the EASA sheet above.

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
