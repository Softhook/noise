# Thamesmead garden noise measurement plan

4 November 2026

## Purpose

Measure arrivals in the garden now, then again once A320neos fly the proposed 4.49° approach, to test the model's estimate of about +1.5 dB LAmax against the E190.

The measurements can show the real difference at the garden, and the combined effect of aircraft noise and thrust. From that we can estimate the difference directly under the path, currently +2.8 dB in the model. They can't separate aircraft noise from thrust, or confirm the under-the-path figure directly.

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
4. **Do the two sites agree?** If we can get NMT6 data for the same flights, compare them. The model explains only about 8.6 dB of the E190's measured 11.8 dB LAmax drop from NMT6 to the garden, and this may show why.

## Stage 2: compare the A320neo

Repeat the same setup once A320neos fly the 4.49° approach, using flight data to confirm each flight's type and approach. Measure E190s in the same period, so that both aircraft have similar weather and conditions.

Compare aircraft at the garden rather than relying on absolute levels, because differences should cancel much of the unexplained error between sites. Then work back in three steps, using the flights' real positions rather than the nominal figures below:

1. Take the average A320neo level minus the average E190 level at the garden.
2. Subtract the calculated distance and air effect at the garden. The result is the aircraft and thrust effect combined.
3. Add the calculated distance and air effect directly under the path.

This example uses an invented measurement of +2.0 dB LAmax:

| Step | LAmax (dB) | Model today (dB) |
| --- | ---: | ---: |
| Difference at the garden | +2.0 (invented) | +1.5 |
| Subtract distance and air, 500 m to the side | −0.75 | −0.75 |
| Aircraft and thrust combined | +1.25 | +0.75 |
| Add distance and air, directly under the path | +2.06 | +2.06 |
| Estimated difference under the path | +3.3 | +2.8 |

Do the same for SEL, where distance and air are +0.48 dB at the garden and +1.26 dB under the path.

## What to record

Each flight needs its noise event matched to its aircraft type and position, otherwise the comparison can't be made.

| Data | Used for | Source |
| --- | --- | --- |
| LAmax and SEL for each event, with time | The levels being compared | Our monitor |
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
- [ ] Which monitor can we use, and can it record each event's LAmax and SEL?
- [ ] Can we get flight type, track and height data, and from whom?
- [ ] Can we get NMT6 levels for the same flights?
- [ ] Where will weather data come from?
- [ ] When would A320neos start flying the 4.49° approach?
