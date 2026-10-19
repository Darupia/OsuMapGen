# Generator status against the human reference maps

How closely OsuMapGen's output matches the measured human maps in this folder, and what is still off. Numbers come from `tools/compare_generated.py`, which compares generated maps with the p10-p90 ranges in [data/](data/). It is a measure of *resemblance on paper*, not of how a map plays: nobody has playtested these maps yet.

## How it was measured

- 96 generated maps: 4 styles (Stream-focused, Jump-focused, Technical, Balanced mix) x 8 full-length songs x target stars 4.5, 6.0 and 7.0. Every map reached its star target (within the 0.5 tolerance) and passed validation.
- Each map is measured with `tools/analyze_maps.py` (the same code that measured the human maps) and put in the band of its own estimated stars.
- For each style and band, 18 metrics are checked: the generated median counts as a match when it lies inside the human p10-p90.
- The human bands with only 1-3 maps (marked *weak*) are anecdotes; a low score there says little.

## Score by style and band (metrics matching, out of 18)

| Style | Band | Human maps | Generated maps | Before tuning | After tuning |
|---|---|---|---|---|---|
| stream | 4.5-5.5 (weak) | 3 | 3 | 3 | 3 |
| stream | 5.5-6.5 | 5 | 8 | 6 | 12 |
| stream | 6.5+ (weak) | 3 | 8 | 1 | 6 |
| jump | 4.5-5.5 | 28 | 4 | 14 | 17 |
| jump | 5.5-6.5 | 18 | 8 | 13 | 16 |
| jump | 6.5+ (weak) | 1 | 8 | 4 | 6 |
| tech | 4.5-5.5 (weak) | 3 | 7 | 1 | 6 |
| tech | 5.5-6.5 | 9 | 8 | 10 | 11 |
| tech | 6.5+ | 9 | 8 | 10 | 12 |
| balanced | 4.5-5.5 | 6 | 4 | 8 | 11 |
| balanced | 5.5-6.5 | 10 | 8 | 14 | 15 |
| balanced | 6.5+ (weak) | 3 | 8 | 2 | 3 |

Overall: **86/216 (40%) before tuning, 118/216 (55%) after**.

## What is still outside the human range (5.5-6.5 stars, the best-covered band)

**stream** (12/18 match; 8 generated vs 5 human maps)

- `objects_per_min`: generated 389.5, human 275.0 / 302.0 / 318.0 (high)
- `stream_pct`: generated 52.0, human 30.6 / 49.1 / 50.3 (high)
- `run_median`: generated 8.0, human 9.0 / 9.0 / 9.0 (low)
- `straight_pct`: generated 54.0, human 18.0 / 33.9 / 37.7 (high)
- `odd_rhythm_pct`: generated 0.5, human 1.7 / 1.8 / 2.5 (low)
- `rep8_pct`: generated 17.4, human 0.0 / 13.6 / 13.8 (high)

**jump** (16/18 match; 8 generated vs 18 human maps)

- `objects_per_min`: generated 279.5, human 190.0 / 254.0 / 272.0 (high)
- `jump_p90`: generated 4.7, human 3.8 / 4.3 / 4.6 (high)

**tech** (11/18 match; 8 generated vs 9 human maps)

- `objects_per_min`: generated 338.5, human 233.0 / 277.0 / 291.0 (high)
- `run_median`: generated 4.0, human 5.0 / 5.0 / 5.0 (low)
- `run_max`: generated 5.0, human 9.0 / 21.0 / 33.0 (low)
- `jump_p90`: generated 3.6, human 2.7 / 3.2 / 3.4 (high)
- `sharp_turn_pct`: generated 44.5, human 28.4 / 37.8 / 40.2 (high)
- `slider_repeat_pct`: generated 9.5, human 3.9 / 4.9 / 7.1 (high)
- `longest_tap_s`: generated 9.9, human 17.6 / 52.7 / 58.4 (low)

**balanced** (15/18 match; 8 generated vs 10 human maps)

- `jump_mean`: generated 1.7, human 2.1 / 2.4 / 2.9 (low)
- `jump_p90`: generated 3.1, human 3.4 / 3.8 / 4.2 (low)
- `buzz_sliders`: generated 3.5, human 0.0 / 0.0 / 1.0 (high)

## Pacing (your 10-15 second rule)

| Style | Longest tapping stretch, median / max (s) | Maps over 15 s | Longest stream-speed stretch, median / max (s) | Maps over 10 s |
|---|---|---|---|---|
| stream | 10.2 / 12.7 | 0 | 7.0 / 12 | 4 |
| jump | 10.4 / 10.7 | 0 | 0.0 / 1 | 0 |
| tech | 10.0 / 13.9 | 0 | 3.0 / 13 | 2 |
| balanced | 12.0 / 13.6 | 0 | 5.0 / 10 | 0 |

"Tapping stretch" = time between rests (a gap of 1.5 beats or more, or a slider held a full beat). "Stream-speed" = consecutive seconds with 8 or more key presses. The generator is deliberately stricter than the human maps here (the human Honesty map has a 44 s stream-speed stretch).

## What changed in the generator to get here

- **Stacks** (none before): half-beat-or-closer notes can sit on the previous note, as pairs and triples; rate per style in `osumapgen/params.py` (`stack_rate`).
- **Streams** are cut on beat boundaries into runs of 5, 9, 13... notes with a one-beat gap between them, and about a third to a half of them end on a short slider (kick, 3-slide or plain). Long streams step their spacing up as they build, and hops out of a stream are wider.
- **Stream maps** no longer reach their star target by making every note a stream: note density saturates early and spacing carries the rest.
- **Jump** maps get many short sliders (human: 38% of objects), no buzz sliders, and stacks.
- **Tech** maps get kick sliders, dotted (3/4-beat) rhythm where the audio has the onset, and more sliders and stacks.
- **Pacing** gained a separate cap on stream-speed tapping, with a longer breather (about a second or more) after fast tapping.

## Known gaps and next steps

- **Stream maps at 6.5+ stars are still too dense and too smooth** (human: about 345 objects per minute and 56% of notes in streams; generated: far more). Human streams get their stars from spacing and varied angles; the generator's streams are smooth arcs. Adding angle variety inside streams is the next lever.
- **Slider share** is still below the human range in stream and tech maps, and sliders in stream maps are mostly the short run-ending kind.
- **Odd rhythm outside tech** (human stream/balanced maps use a little 3/4-beat rhythm) is not generated.
- **Simple and Slider-focused** have no human reference group, so they were not tuned.
- **The human ranges are small** (3-5 maps in several bands). Add more references (see Instruction.md, "Refreshing the numbers") and rerun.
- **No playtest yet.** The next real signal is how these maps feel to play.

## Reproduce

```
python tools/analyze_maps.py <folder with generated .osu files> -o generated.json   # add a "group" field per map (stream/jump/tech/balanced)
python tools/compare_generated.py generated.json
```
