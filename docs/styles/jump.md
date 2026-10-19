# Jump

A Jump map is built from circles placed far apart, so the cursor has to snap across the playfield from one note to the next. Most hops are half a beat or one beat apart and cover roughly 2 to 4 circle widths; the cursor usually reverses direction at the next note instead of flowing on. Sliders are short and sit between jump groups, stacks give a double-tap on one spot, and kick sliders add a small snap. Fast streams are not part of the style. In this reference set only 2 of 47 maps contain any stream at all.

This page is based on 47 human-made osu!standard difficulties of 4.5 stars and above, measured with `tools/analyze_maps.py` and summarised with `tools/style_profiles.py`. The numbers are in [data/jump.json](data/jump.json). The generator style it documents is "Jump-focused" (params key `jump`).

## What it feels like

You are always moving, and the notes arrive on a steady half-beat or one-beat pulse. A typical phrase in the maps I read is one to seven circles at half-beat spacing, then a short slider, then a one-beat gap before the next group. Each circle is a new target on the other side of the screen from the last one, so the difficulty is aim and cursor speed, not tapping speed. The measured fast-tap stretch (8 or more key presses in a second) is 0 s at the 90th percentile in both main star bands.

In the examples I read, the jump sections follow the song's beat grid: half-beat and one-beat gaps are 84% of all gaps in the 47 maps. Four of the nine reference mapsets are explicitly nightcore, sped-up or cut versions, and the BPM is mostly 136 to 210, so the pulse is fast. The timeline strings (one letter per 10 seconds) show jump sections in 53% of windows at 4.5-5.5 stars and 68% at 5.5-6.5 stars, with slider-heavy windows in most of the rest.

What makes it hard:

- **Distance.** The mean jump is 2.7 circle widths at 4.5-5.5 stars and 3.1 at 5.5-6.5 stars (medians). The longest jumps in a map (90th percentile) are 3.7 and 4.3 circle widths.
- **Direction changes.** Median 78% (4.5-5.5) and 85% (5.5-6.5) of turns are sharp (120 degrees or more). Straight-on turns (30 degrees or less) are about 1% of turns. The cursor mostly snaps back and forth rather than gliding.
- **Fast approach.** AR is 9.0 median at 4.5-5.5 stars and 9.3 at 5.5-6.5, so circles are on screen briefly and you read and aim at the same moment.
- **Density.** About 233 and 256 objects per minute (median), with the busiest 10 seconds at 47 and 49 objects.

## Measured profile

All cells are p10 - p50 - p90 over the maps in that band (from `data/jump.json`). Jump distance is in circle widths. Bands with n below 5 are weak evidence; the 6.5+ band has only 2 maps, and for n=2 the tool reports the lower of the two values for all three percentiles, so read that column as an anecdote and not as a range.

| Metric | 4.5-5.5 stars | 5.5-6.5 stars | 6.5+ stars (n=2) |
|---|---|---|---|
| Maps / mapsets | 28 / 8 | 17 / 7 | 2 / 2 |
| Objects per minute | 180-233-261 | 198-256-272 | 290-290-290 |
| Busiest 10 s (objects) | 40-47-51 | 45-49-55 | 51-51-51 |
| Jump distance, mean | 1.93-2.7-3.16 | 2.23-3.12-3.43 | 2.39-2.39-2.39 |
| Jump distance, p90 | 3.04-3.71-4.3 | 3.81-4.3-4.61 | 3.51-3.51-3.51 |
| Sharp turns (120 deg or more), % of turns | 36.8-77.8-90.8 | 53-84.8-92.5 | 32.5-32.5-32.5 |
| Straight-on turns (30 deg or less), % | 0-1.2-8 | 0-0.6-9.8 | 1.1-1.1-1.1 |
| Sliders, % of objects | 27.6-41.6-47.9 | 31.5-37.7-46.7 | 32.6-32.6-32.6 |
| Sliders with a repeat, % of sliders | 0-1.9-7.6 | 0-2.1-4.6 | 1.7-1.7-1.7 |
| Kick sliders per map | 0-0-5 | 0-0-3 | 2-2-2 |
| Buzz sliders per map | 0-0-0 | 0-0-1 | 0-0-0 |
| Stacks, % of objects | 0-3.8-10.7 | 0-2.1-6.3 | 2.1-2.1-2.1 |
| Odd rhythm (1/3, 1/6, 2/3, 3/4), % of gaps | 0-0-6.8 | 0-0-3 | 0.3-0.3-0.3 |
| Longest tapping stretch (s) | 4.6-9.2-18.7 | 4.6-8.6-14.5 | 6.7-6.7-6.7 |
| Longest fast-tap stretch (s) | 0-0-0 | 0-0-0 | 1-1-1 |
| AR | 8.8-9-9.2 | 9.2-9.3-9.4 | 9.4-9.4-9.4 |
| OD | 8-8.5-9 | 8.7-9-9.3 | 9.3-9.3-9.3 |
| CS | 3.4-4-4.2 | 3.5-3.8-4.2 | 4-4-4 |

Rows left out because they are zero in every band: stream %, run length median and max, stream spacing, stream turn angle, and burst runs. In other words, the typical Jump map has no 4+ note streams. The timeline shares (mean over maps, `timeline_share_mean`) are: 4.5-5.5 stars jump 53%, slider-heavy 29%, mixed 11%, rest 7%; 5.5-6.5 stars jump 68%, slider-heavy 24%, mixed 2%, rest 6%.

Other things measured over the 47 maps (summed from `metrics.json`, not from the profile file): half-beat gaps are 54.9% of all gaps, one-beat gaps 29.2%, 1.5-beat gaps 7.5%, quarter-beat gaps 4.5%. Slider shapes are about 48% perfect-circle arcs, 35% straight and 18% bezier. All 47 maps change slider velocity at least once, and 11 maps contain a spinner.

## Signature patterns

![Jump patterns](img/jump.png)

The picture shows four excerpts of about 3 to 4 seconds (2.7 to 3.8 s) from reference maps (numbers are play order; blue is first, orange is last). What follows is what I saw when reading the raw maps and the timeline strings. Items marked "in the examples I read" are my reading of a few maps, not statistics.

**Constant spacing inside a phrase.** The jump distance barely changes within a phrase. The median coefficient of variation is 0.34 in both main bands (p10-p90: 0.22-0.58 and 0.24-0.43). In the Take Us To Vegas "Extra" the hops are mostly 2 to 3 circle widths and edge upward over the 18 seconds I read. In the Determinate "Fearless Rockstar" they are mostly 3 to 5, with the biggest at 5.4.

**Groups of circles, then a short slider, then a gap.** In the examples I read (Vegas, Determinate, Get Jinxed, PADORU), the pulse is 1 to 7 circles at half-beat spacing, a slider about half a beat long, then a one-beat gap. Sliders are short: the median slide is 0.5 beat and 94 to 100% of sliders (p10 to p90) are under one beat. About 2% have a repeat.

**Phrase ends with a longer gap.** A 1.5-beat gap closes many phrases (7.5% of all gaps). This is about half a second at 180 BPM. It is the smallest breather in these maps.

**Hard direction changes, few straight lines.** With 78 to 85% sharp turns and about 1% straight-on turns, the dominant shape is the cursor going back across the screen. The zig-zag panel in the picture (Cookie-Triangle-Spicy-Cookie) shows this. In the stretch I read of that map the mapper cycles through a handful of spots on the field (the same position comes back every eight notes or so), so the cursor keeps returning to places it has just been. Linear flow and circular flow are not measured separately.

**Stacks as a double-tap on one spot.** 39 of 47 maps have at least one stack, but most have few (median 3.8% of objects at 4.5-5.5 stars, 2.1% at 5.5-6.5). Seven maps have 10% or more: six from the PADORU mapset and Take Us To Vegas "Insane". In PADORU the stack is a circle, then a second circle and a slider on the very same spot at quarter-beat gaps, so the player taps three times quickly without moving. In Mir's Insane (Chikatto Chika Chika, 7.1% stacks) it is a run of pairs: each spot is hit twice at half-beat spacing, then the cursor jumps about 2.4 to 2.5 circle widths to the next spot (shown in the picture).

**Kick and buzz sliders are accents, not the base.** 22 of 47 maps have at least one kick slider (short slider with one reverse), median 0, p90 of 5 and 3 per map. Only 6 of 47 maps have any buzz slider, at most 4 in one map (Reform's Expert). The Recollection map (7.03 stars) is the heavy outlier with 20 kick sliders. In Reform's Expert the buzz sliders come in pairs and are followed by one long slider that is held for the rest of the gap, which is how that map takes a breath (bottom right in the picture).

**Streams are rare and short, between jump sections.** Only two maps have any: Mir's Insane (4.81 stars, 2 runs, longest 5 notes, spacing 0.28 circle widths) and Recollection (7.03 stars, 23 runs, median 7 notes, longest 19, spacing 0.55 circle widths). In Recollection a 17-note run (the map's longest is 19) starts after a 1.5-beat gap that follows a slider. After it come a second short burst, then single notes 1.5 and 2 beats apart that sit almost on the same spot, then sliders, and then a 32.5-beat gap of about 9 seconds. A note count that high at quarter-beat spacing is the exception here, not the rule.

## Pacing and breathers

The 10-15 second rule is about spam-tapping. Jump maps do not ask for that: the longest fast-tap stretch is 0 s at p90 in both main bands, and only 3 of 47 maps have any (1 to 2 seconds). What they ask for is continuous aiming.

The longest tapping stretch (time between rests, where a rest is a gap of 1.45 beats or more, or a slider held for 0.97 beat or more) is:

- 4.5-5.5 stars: 4.6 s (p10), 9.2 s (median), 18.7 s (p90).
- 5.5-6.5 stars: 4.6 s (p10), 8.6 s (median), 14.5 s (p90).

So the median map stays within the 10-15 second rule, but not all of them do. Counting the per-map numbers in `metrics.json`, 14 of 47 maps have a stretch longer than 10 s and 7 of 47 are longer than 15 s: Get Jinxed "Master" (43.0 s) and "Irrelvis' Diamond" (33.0 s), Take Us To Vegas "Extreme" (26.5 s), PADORU "FuJu's Expert" (21.8 s), Backstabber "skylaa's Extra" (19.1 s), Cookie-Triangle-Spicy-Cookie (18.7 s) and Bubblegum Bitch "Mekadon's Extra" (15.9 s). Human Jump maps do break the rule at the top end, though the stretches are half-beat aiming at about 4 notes per second on average (233 to 256 objects per minute), not stream-speed tapping. Also note that the reference maps are mostly cuts of 0.5 to 3.3 minutes, so these maxima are capped by map length.

What the maps do instead of resting:

- **The 1.5-beat gap** at the end of a phrase (about half a second at 180 BPM).
- **A long slider plus a gap.** Reform's Expert has a slider of about 3.75 beats, and the next note comes 4 beats after it starts (0.25 beat after it ends). Get Jinxed "Master" has a 2-beat slider, then a 3-beat slider, and the next note comes 4 beats after the second one starts (1 beat after it ends).
- **Real breaks.** Timeline rest windows (fewer than 3 objects in 10 s) are about 7% and 6% of windows at 4.5-5.5 and 5.5-6.5 stars. Recollection has one gap of 32.5 beats.
- **A slower section.** After that 9-second gap, Recollection moves to mostly 1.5 to 2.5-beat gaps (with a few 0.5, 1 and 4-beat gaps) and 1.5 to 2-beat sliders for about 7 seconds.
- **Slider-heavy windows.** 29% and 24% of windows are slider-heavy, and 28 to 48% of objects are sliders, so there is usually a short slider to catch up on every few notes.

For the generator, the practical reading is: a half-beat jump phrase of 8 to 10 seconds, then a slider or a 1.5 to 4 beat gap, matches the median human map. Going past 15 seconds without a rest is something the human maps do but only about one map in seven.

## Targets for the generator

Ranges are the p10 to p90 of the human maps in the band. A generated Jump map should fall inside them. Where the human p90 for the longest tapping stretch is above 15 s, keep the generator under 15 s to follow your own pacing rule.

**4.5-5.5 stars (28 maps, 8 mapsets)**

- Objects per minute 180 to 261; busiest 10 s 40 to 51 objects.
- Mean jump distance 1.9 to 3.2 circle widths; p90 jump distance 3.0 to 4.3.
- Sharp turns 36.8 to 90.8% of turns (median 77.8%); straight-on turns 8% or less.
- Sliders 27.6 to 47.9% of objects; sliders with a repeat 7.6% or less; kick sliders 0 to 5; buzz sliders 0.
- Stacks 10.7% or less; odd rhythm 6.8% or less.
- No stream runs of 4+ notes (stream % = 0); fast-tap stretch 0 s.
- Longest tapping stretch 4.6 to 18.7 s (aim for 15 s or less).
- AR 8.8 to 9.2, OD 8.0 to 9.0, CS 3.4 to 4.2.

**5.5-6.5 stars (17 maps, 7 mapsets)**

- Objects per minute 198 to 272; busiest 10 s 45 to 55 objects.
- Mean jump distance 2.2 to 3.4 circle widths; p90 jump distance 3.8 to 4.6.
- Sharp turns 53 to 92.5% of turns (median 84.8%); straight-on turns 9.8% or less.
- Sliders 31.5 to 46.7% of objects; sliders with a repeat 4.6% or less; kick sliders 0 to 3; buzz sliders 0 to 1.
- Stacks 6.3% or less; odd rhythm 3.0% or less.
- No stream runs of 4+ notes; fast-tap stretch 0 s.
- Longest tapping stretch 4.6 to 14.5 s.
- AR 9.2 to 9.4, OD 8.7 to 9.3, CS 3.5 to 4.2.

**6.5+ stars (2 maps)**: too thin for a range. The two maps measure about 290 objects per minute on the lower side, and one of them (Recollection) mixes in streams and is not a pure Jump map. Use the 5.5-6.5 ranges and allow a little more density.

To check a generated map against these numbers:

```
python tools/analyze_maps.py <file.osu>
```

Compare the printed jump distance, sliders %, stream % and timeline with the ranges above, or run `tools/style_profiles.py` on a metrics file for the full table.

## Reference set

Selected from the maps the user labeled "jump", keeping 4.5 stars and above (47 maps, 9 mapsets). Titles, artists and mapset hosts only; no files are stored or published.

| Mapset | Host | Maps used | Stars |
|---|---|---|---|
| Turbo - PADORU / PADORU | DeRandom Otaku | 12 | 4.97-5.83 |
| Minstrel - Fiction | Shoenen | 1 | 7.03 |
| Ke$ha - Backstabber (Sped Up & Cut Ver.) | wetdog123 | 3 | 5.29-5.62 |
| Take Us To Vegas - For The Love Of The Game (Nightcore & Cut Ver.) | browiec | 4 | 4.73-6.58 |
| Marina and the Diamonds - Bubblegum Bitch (Nightcore & Cut Ver.) | Parad0xa | 10 | 4.73-5.94 |
| Bridgit Mendler, Adam Hicks, Naomi Scott and Hayley Kiyoko - Determinate (Nightcore & Cut Ver.) | My Angel Ram | 7 | 4.70-5.75 |
| Agnete Kjolsrud - Get Jinxed | Tarrasky | 3 | 5.47-6.03 |
| Elmo and Cookie Monster - Cookie-Butter-Choco-Cookie | Monstrata | 2 | 4.53-4.97 |
| Nanahira - Chikatto Chika Chika | Agatsu | 5 | 4.57-5.80 |

Excluded (verified mislabeled by the audit, so not Jump): Shii's Extra and Ipas' Insane (both from Minstrel - Fiction) and Weedy's Extra (Backstabber). Their measurements show why they do not fit: the two Fiction maps contain streams (12.6% of objects with a 19-note run at 6.10 stars, and 5.4% at 5.05 stars), and Weedy's Extra is 72.3% sliders with a slider-heavy timeline.

Below 4.5 stars the mapsets contain easier difficulties that are not representative of the style (38 maps, 1.7 to 4.5 stars). Most mapsets measure mean jump distances of about 0.8 to 1.3 circle widths at 2.4 to 3.7 stars, and the Cookie-Butter-Choco-Cookie mapset is the exception at 1.4 to 2.4 in that range (1.3 to 3.3 over all its 14 easier maps), so they are not used.

Weak spots in the evidence:

- The 6.5+ band has 2 maps from 2 mapsets, so no range can be given.
- The 5.5-6.5 band has 17 maps from 7 mapsets, and the 4.5-5.5 band 28 maps from 8 mapsets. Several mapsets contribute 10 or 12 difficulties each (PADORU 12, Bubblegum Bitch 10, Determinate 7), so a few mapping styles weigh heavily.
- Four mapsets are nightcore, sped-up or cut versions. Map lengths run from 0.5 to 3.3 minutes and 8 of the 9 mapsets are 2.2 minutes or shorter, so tapping-stretch maxima and pacing statements are limited by this.
- One map (Irre's Extra, 4.97 stars) uses CS 7.0, much smaller circles than the rest (CS 3.0 to 4.5), so its distances in circle widths are not directly comparable to the rest.
- The pattern descriptions come from reading excerpts of a handful of maps; the numbers are measured, the "in the examples I read" statements are not statistics.

## See also

- [Stream](stream.md)
- [Tech](tech.md)
- [Balanced](balanced.md)
