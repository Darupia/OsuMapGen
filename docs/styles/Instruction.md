# Style documentation: start here

This folder describes how human mappers build four kinds of osu!standard maps (stream, jump, tech, balanced), with measured numbers and pictures, so the generator can be tuned toward real maps. Read this page first. It tells you which style page to open, what rules every style shares, and how to check a generated map.

We measured 172 reference difficulties, kept locally in `references/`. The ranges use 98 of them: 4.5 stars and up, minus 11 the audit judged mislabeled (stream 11, jump 47, tech 21, balanced 19 maps). The other 63 were below 4.5 stars. That folder is git-ignored, so the maps and audio never leave the machine. The docs hold titles, measured numbers, short descriptions of patterns, and 16 small drawings (1-4 s excerpts) of object positions in `img/`. Stars are the values `rosu-pp-py` computes, which can differ a little from the star rating shown in the game or on the website.

## How the folder works

```
Instruction.md  ->  <style>.md  ->  img/<style>.png
 (this page)        (the guide)     (1 picture of 4 panels per style)
                        |
                        +-->  data/<style>.json   (exact numbers)
```

| Style | Guide (read this) | Picture | Exact numbers |
|---|---|---|---|
| Stream | [stream.md](stream.md) | [img/stream.png](img/stream.png) | [data/stream.json](data/stream.json) |
| Jump | [jump.md](jump.md) | [img/jump.png](img/jump.png) | [data/jump.json](data/jump.json) |
| Tech | [tech.md](tech.md) | [img/tech.png](img/tech.png) | [data/tech.json](data/tech.json) |
| Balanced | [balanced.md](balanced.md) | [img/balanced.png](img/balanced.png) | [data/balanced.json](data/balanced.json) |

Each guide has the same parts: what the style feels like to play, a table of measured ranges per star band, signature patterns (what mappers actually do), pacing and breathers, targets for the generator, and the list of reference maps used. The `.svg` files in `img/` are the sources of the pictures (they hold the exact object positions of the excerpts, so if you want no object positions in git, keep only the PNGs). Each `.json` file holds, for every star band, the 10th / 50th / 90th percentile (p10 / p50 / p90) of every metric, plus how many maps and mapsets it came from. In words: p50 is the typical map, p10 to p90 is the range the middle 80% of the maps fall in.

The tool picks an actual map's value by position (no averaging). With 10 maps or fewer, p10 is the lowest map; with 5 to 10 maps, p90 is the second-highest map; with 3 maps, p90 is the middle map. For an even number of maps, p50 is the lower of the two middle maps. So p10-p90 is a rough range, and a good generated map can legitimately sit just outside it.

A note on words: "circle width" is the size of one circle, and all distances are measured in it, so they mean the same on every circle size (the physical circle is smaller at high CS, so the same distance is harder to hit there). Turn angle 0 is straight on and 180 is straight back. The glossary terms (stream, burst, jump, stack, buzz slider, kick slider, kiai and so on) are used the way you use them.

### Metric definitions

These are the exact thresholds in [tools/analyze_maps.py](../../tools/analyze_maps.py). Every guide uses them.

- **Sharp turn**: a turn angle of 120 degrees or more. **Straight-on**: 30 degrees or less. A turn is counted only when both neighbouring gaps are 1.1 beats or less.
- **Jump distance**: measured only over gaps of 0.45 to 1.1 beats (from where the cursor leaves an object to the next head).
- **Stream**: a run of 4 or more objects with gaps of 0.3 beat or less. **Burst**: a short stream (the metric `burst_runs_3_7` counts runs of 4 to 7 objects, despite its name).
- **Buzz slider**: 4 or more slides and under 90 px long. **Kick slider**: exactly 2 slides (one reverse) and at most 0.55 beat per slide.
- **Slides and reverses**: slides = the number of times the slider is travelled; reverses = slides minus 1. When a guide says "repeats" it means slides.
- **Stack**: distance under 0.05 circle widths and a gap of 0.55 beat or less.
- **Odd rhythm**: gaps of 1/3, 1/6, 2/3 and 3/4 beat.
- **Rest**: a gap of 1.45 beats or more, or a slider held 0.97 beat or more. **Tapping stretch**: time between rests. **Fast-tap stretch**: consecutive seconds with 8 or more key presses.
- **Timeline windows** (one letter per 10 s, checked in this order): `.` fewer than 3 objects; S 50% or more of the gaps at 0.3 beat or less; L 50% or more sliders; J 50% or more of the 0.45-1.1 beat gaps are 2.2 circle widths or farther; B 20% or more fast gaps; otherwise m (mixed).
- **Star bands** include their lower edge: a 5.50 star map is in 5.5-6.5, and 6.50 is in 6.5+.

## Which page should I read?

Pick the feeling you want, then open the page.

| If the target map should feel like... | Read | Generator style (name in the app, key in `osumapgen/params.py`) |
|---|---|---|
| Fast continuous runs and bursts of notes, stamina, a wall of notes in the chorus | [stream.md](stream.md) | Stream-focused (`stream`) |
| Big snaps across the screen, half-beat hops, short sliders between groups, no streams | [jump.md](jump.md) | Jump-focused (`jump`) |
| Constantly changing rhythm, half the notes are short sliders, kick and buzz sliders, stacks, small bursts | [tech.md](tech.md) | Technical (`tech`) |
| A mix that changes with the music: hops and sliders in the verses, bursts and some streams in the loud parts | [balanced.md](balanced.md) | Balanced mix (`mix`, a different preset per section) and the single Balanced preset (`balanced`, used when Auto picks it) |
| Calm, readable, beginner-friendly | no page yet | Simple and readable (`simple`) |
| Mostly sliders, slider art | no page yet | Slider-focused (`slider`) |
| "Pick for me" | whichever page matches the style Auto chose | Auto (`auto`) |

Things to know about this table:

- **Simple and readable and Slider-focused have no reference group yet.** No maps were labelled for them, so there are no measured ranges and no pattern pictures. Do not take numbers from another style and call them "simple" or "slider". The nearest indirect evidence is the slider share by style (median of each band, 4.5-5.5 / 5.5-6.5 / 6.5+): tech 56.2 / 50 / 42.5%, balanced 49 / 34.7 / 35.1%, jump 41.6 / 37.7 / 34.6%, stream 31.1 / 27.7 / 19.8%. Tech has the most sliders. Balanced and jump have about a third to a half, and stream the fewest. There is no slider-art style in the data. Maps below 4.5 stars were not used at all, because the easy difficulties inside the labelled mapsets do not show any style. To fix this, add reference maps for these two styles (see "Refreshing the numbers").
- **Auto** looks at the song and picks one single preset: simple if the star target is below 2.5, stream for dense 1/4 music at a tempo of 190 BPM or less, jump for fast (185 BPM or more) or sparse music, otherwise balanced (see `resolve_style` in [osumapgen/params.py](../../osumapgen/params.py)). Auto never picks tech or slider. So read the page of whichever style it picked.
- **Balanced mix** gives each section of the song its own preset (simple or slider in quiet parts, stream, jump or tech in loud parts, balanced in between) and avoids repeating the same preset next to itself. A mixed map can therefore be checked against several pages, section by section. [balanced.md](balanced.md) describes the human maps that mix techniques on their own. Note that quiet sections of a mix can get `simple` or `slider`, which have no reference data.
- The page you pick is a starting point. Star rating matters at least as much as the style (see the shared rules).

## The four styles side by side (5.5-6.5 stars, medians)

This band is the best covered one. Every cell is the median (p50) of the maps in that band, copied from the `data/*.json` files. Distances are in circle widths.

| Median at 5.5-6.5 stars | Stream | Jump | Tech | Balanced |
|---|---|---|---|---|
| Maps / mapsets | 5 / 4 | 18 / 7 | 9 / 6 | 10 / 7 |
| Objects per minute | 302 | 254 | 277 | 279 |
| Stream % of objects | 49.1 | 0 | 18.3 | 28.5 |
| Stream run length, median (notes) | 9 | none | 5 | 6 |
| Stream run length, longest in a map (notes) | 41 | none | 21 | 17 |
| Stream spacing | 0.57 | none | 0.56 | 0.46 |
| Jump distance, mean | 2.35 | 3.06 | 2.01 | 2.41 |
| Jump distance, 90th pct | 3.6 | 4.3 | 3.16 | 3.77 |
| Sharp turns % | 34 | 82.5 | 37.8 | 32.6 |
| Straight-on turns % | 33.9 | 0.6 | 22.7 | 21.9 |
| Sliders % of objects | 27.7 | 37.7 | 50 | 34.7 |
| Slider repeat % | 17.1 | 2.1 | 4.9 | 5 |
| Buzz sliders per map | 0 | 0 | 2 | 0 |
| Kick sliders per map | 8 | 0 | 16 | 5 |
| Stacks % | 4.5 | 2 | 7.2 | 4.8 |
| Odd rhythm % | 1.8 | 0 | 9.8 | 1.1 |
| Longest tapping stretch (s) | 30 | 8.6 | 52.7 | 24 |
| Longest fast-tap stretch (s) | 5 | 0 | 4 | 4 |
| Total fast-tap time per map (s) | 30 | 0 | 24 | 16 |
| Repeated 8-note patterns % (`rep8_pct`) | 13.6 | 0 | 0.5 | 2.6 |
| AR / OD / CS | 9.3 / 9 / 4 | 9.3 / 9 / 3.8 | 9.4 / 8.4 / 4 | 9.3 / 8.5 / 4 |
| Gap mix, 1/4 beat, % of gaps (all 4.5+ star maps of the style) | 51.7 | 2.7 | 31.0 | 27.5 |
| Gap mix, 1/2 beat | 26.0 | 56.2 | 37.9 | 33.3 |
| Gap mix, 1 beat | 15.5 | 29.8 | 17.5 | 29.5 |
| Gap mix, 1.5 beat | 3.3 | 7.5 | 1.5 | 5.6 |
| Gap mix, 3/4 beat | 0.6 | 0.9 | 6.6 | 1.7 |

The five gap-mix rows are sums over every 4.5+ star map of the style (12,059 / 10,362 / 21,853 / 13,794 gaps), not 5.5-6.5 medians. The rest of each column is other gaps (1/3, 2/3, 1/6, over 2 beats, and gaps that fit none of the usual snaps). They come from the `snaps` field of `metrics.json` and are saved in `references/_analysis/gap_mix.json` (local only, like everything in `references/`).

Sample sizes in this band: no style has n below 5, but Stream has exactly 5 maps from 4 mapsets, which is still thin. Balanced counts one map twice (Kakushigoto [Insane] and its AR10 copy have the same notes), so it is 9 distinct maps. In a band of 5 to 10 maps one mapset can pull the median. Jump has the most maps (18) but they are mostly short 0.5 to 2.2 minute cuts. The other bands are weaker (cells are maps / mapsets):

| Band | Stream | Jump | Tech | Balanced |
|---|---|---|---|---|
| 4.5-5.5 stars | 3 / 2 (n<5, weak) | 28 / 8 | 3 / 3 (n<5, weak) | 6 / 5 |
| 5.5-6.5 stars | 5 / 4 | 18 / 7 | 9 / 6 | 10 / 7 |
| 6.5+ stars | 3 / 3 (n<5, weak) | 1 / 1 (n<5, weak, one map) | 9 / 4 | 3 / 2 (n<5, weak: 2 different maps) |

What stands out in the 5.5-6.5 table:

- **Jump is the odd one out on direction.** About 83% of its turns are sharp and almost none are straight-on, against roughly a third sharp in the other three. It also has the biggest hops, no streams, and almost no fast tapping.
- **Tech has the most sliders** (half of all objects), the most kick and buzz sliders and by far the most odd rhythm (9.8% of gaps, mostly 3/4-beat gaps according to [tech.md](tech.md)), with the smallest hops.
- **Stream has the most streams, the most fast tapping and the straightest movement.** It is also the most repetitive, because long even runs repeat.
- **Balanced sits in between**: density, hop size and AR are close to Stream and Tech, and its streams are mostly short bursts rather than long walls.
- **Density and approach rate do not separate the styles much.** Objects per minute are 254 to 302 and AR is 9.3 to 9.4 in all four. The styles differ in what the notes do (distance, angle, sliders, rhythm), not in how many there are.

## Shared rules (every style obeys these)

**1. The 10 to 15 second tapping rule, and breathers.** A player should not spam-tap for longer than about 10 to 15 seconds. Sliders and buzz sliders give the hands a break and can bring a player back to life, as in the map Honesty. What the human maps actually show depends on how you measure:

- *Fast tapping* (8 or more key presses in one second, real stream speed): the human maps mostly follow the rule. Longest fast-tap stretch medians at 5.5-6.5 are 5 s (stream), 0 s (jump), 4 s (tech) and 4 s (balanced). The exceptions are in [stream.md](stream.md): the 6.5+ stream band has a median of 15 s, and DISHONEST has a 44 s stretch.
- *Any tapping without a rest* (a rest is a gap of 1.45 beats or more, or a slider held about one beat): the human maps break the rule in the median map of every style except jump. Medians at 5.5-6.5 are 30 s (stream), 8.6 s (jump), 52.7 s (tech) and 24 s (balanced). Jump medians are 8.6-9.2 s, and even there 7 of 47 maps exceed 15 s (the longest is Get Jinxed Master with 43.0 s; jump p90 is 18.7 s at 4.5-5.5 and 14.5 s at 5.5-6.5). Mostly this is half-beat hops and short sliders, not stream speed.
- So the 10-15 s interval is the project's rule, not something the human maps follow by that second measure. The generator is meant to be stricter than the humans. Its presets cap tapping with `max_tap_s` (and stream-speed tapping with `max_fast_tap_s`), see the table below and [osumapgen/params.py](../../osumapgen/params.py). Each style guide ends its pacing part with a rule that fits both the data and your idea.
- What the humans use as breathers, in the examples I read (all four guides): a short slider at the end of a phrase, a gap of one beat or more, a long slider held about a beat or more, a buzz or kick slider as a connector, a spinner (present in 6 of 11 stream, 11 of 47 jump and 9 of 17 distinct balanced maps), and switching technique by section.

| Style | Preset `max_tap_s` (s) | Preset `max_fast_tap_s` (s) | Human median of the longest tapping stretch (s), 4.5-5.5 / 5.5-6.5 / 6.5+ | Human maximum fast-tap stretch (s) |
|---|---|---|---|---|
| Stream | 10 | 8 | 24.2 / 30 / 37.5 | 10, except two finales of 15 and 44 (ABSOLUTION, DISHONEST) |
| Jump | 12 | 10 (default) | 9.2 / 8.6 / 6.7 (one map) | 1 |
| Tech | 11 | 10 (default) | 36.2 / 52.7 / 22 | 8 |
| Balanced | 12 (default) | 10 (default) | 10.2 / 24 / 34.4 | 8 |
| Simple / Slider | 14 / 15 | 10 (default) | no data | no data |

Do not use the human tapping-stretch ranges as generator targets; they contradict the 10-15 s rule. Use `max_tap_s`.

**2. Variety (except inside streams).** Outside streams, maps change shape constantly: a phrase ends differently each time and sections switch between jump, slider and burst windows. (The one example I read of spacing stepping up inside a stream is DISHONEST, see [stream.md](stream.md).) The analyzer has a repetition number, `rep8_pct`: the share of 8-note windows with the same rhythm, distance and turn that occur 3 or more times. Medians at 5.5-6.5: 0 (jump), 0.5 (tech), 2.6 (balanced) and 13.6 (stream, where long even runs are natural). Stream repetition is high in the data (p50 13.6 at 5.5-6.5 and 27.1 at 6.5+), so the number is a check against copy-paste in the other styles, not a ban. A generated jump, tech or balanced map far above the number for its style probably copies a pattern too often.

**3. Star bands matter more than style.** Within one style, difficulty rises with stars through density, spacing and run length, and the same style looks very different in different bands. For stream the median stream share goes 28.6, 49.1, 56.7% and objects per minute 264, 302, 345 across the three bands. For jump the mean hop goes 2.7, 3.06, 3.43 circle widths. Balanced shifts from a slider-and-burst map to a jump-and-slider map as stars go up (see [balanced.md](balanced.md)). Always compare against the band of the target star rating first and use the style second. Do not borrow the p10-p90 range of another band to fill a gap: the docs say where a band has no data or only one or two maps. Below 4.5 stars there are no ranges at all.

## From metric to generator knob

Which field of `MapParams` in [osumapgen/params.py](../../osumapgen/params.py) moves which measured number. This is read from the code comments, not tested one knob at a time.

| Measured number | Knob(s) in `params.py` |
|---|---|
| Objects per minute, stream % | `level_lo`, `level_hi` (rhythm density), `quarter_bias` (more or fewer 1/4 notes), `max_burst` (longest 1/4 run), `stream_fill` |
| Jump distance (mean, p90) | `spacing`, `jump_boost`, `max_distance` |
| Stream spacing | `stream_spacing`, `stream_step` (long streams step their spacing up) |
| Sharp-turn % and straight-on % | `angle_sharpness` |
| Sliders % | `slider_rate`, `slider_force`, `slider_min_gap` |
| Slider repeat %, buzz, kick sliders | `slider_repeat`, `buzz_chance`, `kick_chance`; `run_slider_end` (a stream run ends on a short slider) |
| Stack % | `stack_rate` |
| Odd rhythm % (3/4 beat) | `dotted_rate` |
| Longest tapping stretch, longest fast-tap stretch | `max_tap_s`, `max_fast_tap_s` |
| AR / OD / CS / HP | not a style knob: `difficulty_settings` follows the star target |
| `rep8_pct` | no direct knob |

## Where the generator stands

On 2026-10-19, `python tools/compare_generated.py references/_analysis/generated.json --quiet` reports 118 of 216 metrics (55%) inside the human p10-p90, up from 86 (40%) before tuning. The lowest scores are stream 4.5-5.5 and balanced 6.5+ (3 of 18 each), then jump 6.5+, tech 4.5-5.5 and stream 6.5+ (6 of 18 each). Each of those five bands has only 1 to 3 human maps, so a low score there says little. Best covered: jump 4.5-5.5 (17 of 18), jump 5.5-6.5 (16) and balanced 5.5-6.5 (15). The full table and the list of what is still off are in [Generator_status.md](Generator_status.md).

## How to measure a generated map

Run everything from the project root (`OsuMapGen/`). The tools need `rosu-pp-py` for star ratings (it is in `requirements.txt`) and nothing else beyond the standard library. The last step needs Node and the Chromium that Playwright ships; that is a developer helper, not a project dependency.

**1. Measure one map.** One line with stars, stream %, hop size, slider % and the timeline:

```
python tools/analyze_maps.py "path/to/generated map.osu"
```

The timeline is one letter per 10 seconds: S stream, J jump, L slider-heavy, B bursts, m mixed, `.` rest. To get every number (the same names as in the `data/*.json` files), write it to a file:

```
python tools/analyze_maps.py "path/to/generated map.osu" -o my_map.json
```

Every metric is defined at the top of [tools/analyze_maps.py](../../tools/analyze_maps.py).

**2. Score generated maps against the human ranges.** [tools/compare_generated.py](../../tools/compare_generated.py) prints, for each style and star band, the generated median next to the human p10 / p50 / p90 from `data/*.json` and marks each metric `ok`, `LOW` or `HIGH`:

```
python tools/compare_generated.py my_maps.json --style stream --band 5.5-6.5
```

It needs to know which style each generated map was made as. The analyzer takes that from the folder name right below a folder called `references`, so put the generated maps in a throwaway folder such as `scratch/references/stream/`, `scratch/references/jump/`, `scratch/references/tech/` and `scratch/references/balanced/` (outside this repository's `references/`) and run `python tools/analyze_maps.py scratch/references -o my_maps.json`. Maps are put in the band of their own measured stars, so a 6.0 star map is compared with 5.5-6.5. A number outside p10-p90 is not an error by itself (those are only the middle 80% of a small set), but several `LOW` or `HIGH` in a row mean the map does not feel like that style. A band with a "weak" mark in the table above gives only a rough guide.

**3. Look at the patterns.** Draw a section of the map and compare it with the pictures in `img/`:

```
python tools/pattern_svg.py out.svg --panel "map.osu|61.0|69.0|stream section"
python tools/pattern_svg.py out.svg --auto "map.osu|jump|8|jump excerpt" --auto "map.osu|stream|8|stream excerpt"
node tools/svg_to_png.mjs out.svg out.png 1.2
```

The first form draws the seconds you name (file, start, end, label). The second lets the tool find the best excerpt of a kind in the map: stream, jump, slider, buzz, stack or odd. Numbers are play order and colours run from blue (first) to orange (last). Write the pictures somewhere outside `docs/styles/img/` unless you are deliberately replacing a reference picture.

**4. Print a full table for a style.** To see every percentile of a style yourself:

```
python tools/style_profiles.py references/_analysis/metrics.json --group jump --min-stars 4.5
```

Without `--exclude` this includes the maps the audit removed, so the counts differ from the docs (see the next section).

## Refreshing the numbers when new references are added

1. Put the new maps in `references/<group>/<mapset>/` where `<group>` is `stream`, `jump`, `tech` or `balanced`. The group comes from the folder name, so label whole mapsets. A new group folder such as `simple` or `slider` works the same way and would give those two generator styles their first page. `compare_generated.py` would need that style added to its default list before it scores it.
2. Measure everything again:
   ```
   python tools/analyze_maps.py references/ -o references/_analysis/metrics.json
   ```
3. Rebuild each style's data file. Reuse the exclusions recorded in the `excluded` field of the old `data/<style>.json` (the maps an audit judged mislabeled), one `--exclude` per entry:
   ```
   python tools/style_profiles.py references/_analysis/metrics.json --group tech --min-stars 4.5 --exclude "<name from the old excluded list>" --json > tech_new.json
   ```
   The four fields `style`, `min_stars`, `excluded` and `note` at the top of each data file were added by hand. Copy them from the old file into the new one, update the note if the sample size changed, then replace `data/<style>.json` with the new file. Each `--exclude` is matched as a substring of the file path, so use a name long enough to hit one map (the recorded entries are file-name tails such as `Inferno (Monstrata) [The Eclipse].osu`, not just `[Insane].osu`).
4. Update the hand-written numbers. The style pages quote their tables and many sentences from the data and from the raw maps, and they do not update themselves. Go through the "Measured profile" table, the "Targets" list, the "Reference set" table and the sample-size warnings of each affected page, then redo the comparison tables on this page.
5. If a new reference changes what a pattern looks like, redraw that picture (`tools/pattern_svg.py`, then `tools/svg_to_png.mjs`) and replace the files in `img/`.
6. Keep the maps local. Do not commit `references/` and do not copy beatmaps or audio into `docs/`.

## Limitations

- **Small samples.** Several bands have fewer than 5 maps (marked "weak" above), and with 3 maps the median and the 90th percentile are the same map. Even the larger bands are dominated by a few mapsets (each guide lists how many maps each mapset gave). Read p10-p90 as a rough range, not as a distribution.
- **Labels are by mapset.** The user labelled whole mapsets, and a mapset can hold a map that does not fit its label. An audit already removed some (listed in the "Reference set" part of each guide), and the guides point out bands that still look mixed, for example the 4.5-5.5 stream band. Difficulties below 4.5 stars were not used because they do not show the style.
- **Metrics are approximations.** The analyzer measures timing and distances, not how a map plays: it cannot see flow quality, readability, hitsounds or whether a pattern fits the music. Slider curves are approximated, "stream" means a run of 4 or more objects with gaps of 0.3 beat or less, and tapping stretches depend on the definition of a rest (see the pacing rule above). No audio was analysed for the style pages, so statements about choruses (kiai) and breaks come from the kiai flags in the maps' timing sections, not from the music. A one-off check of those flags (object rate inside versus outside kiai) is saved in `references/_analysis/kiai_density.json`. Other one-off numbers in the guides are marked "(one-off script)".
- **Not measured yet.** Flow type (linear, angular, circular), cross-screen jumps and 1-2 jumps, slider length and slider velocity, distances for 1/4 or 1.5-beat-and-longer gaps, the distance from a slider's end to the next head, how long breaks last, and the glossary words Transition and Slider art. The guides mention these only as readings of a few maps.
- **Pattern descriptions are readings.** Statements marked "in the examples I read" come from looking at a handful of maps and are not statistics.
- **Cut and sped-up maps.** Many reference maps are short cuts of songs (some from nightcore versions), which caps the longest stretches and makes per-map counts such as kick or buzz sliders hard to compare.
- **Two generator styles have no data** (Simple and readable, Slider-focused), and above 6.5 stars only tech has more than 3 maps.
- **No human playtest of generated maps yet.** Matching these numbers shows a generated map resembles human maps on paper. It does not show that it is fun or fair to play. That needs players.

## See also

- [stream.md](stream.md), [jump.md](jump.md), [tech.md](tech.md), [balanced.md](balanced.md)
- [Generator_status.md](Generator_status.md): how closely the generator matches these ranges today
- Tools: [analyze_maps.py](../../tools/analyze_maps.py), [style_profiles.py](../../tools/style_profiles.py), [compare_generated.py](../../tools/compare_generated.py), [pattern_svg.py](../../tools/pattern_svg.py), [svg_to_png.mjs](../../tools/svg_to_png.mjs)
- Generator code: [params.py](../../osumapgen/params.py) (the style presets), [rhythm.py](../../osumapgen/rhythm.py), [placement.py](../../osumapgen/placement.py)
