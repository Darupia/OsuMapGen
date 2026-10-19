# Style documentation: start here

This folder describes how human mappers build four kinds of osu!standard maps (stream, jump, tech, balanced), with measured numbers and pictures, so the generator can be tuned toward real maps. Read this page first. It tells you which style page to open, what rules every style shares, and how to check a generated map.

Everything here comes from 172 reference difficulties kept locally in `references/`. That folder is git-ignored, so the maps and audio never leave the machine. The docs only hold titles, measured numbers and short descriptions of patterns.

## How the folder works

```
Instruction.md  ->  <style>.md  ->  img/<style>.png
 (this page)        (the guide)     (4 pattern pictures)
                        |
                        +-->  data/<style>.json   (exact numbers)
```

| Style | Guide (read this) | Picture | Exact numbers |
|---|---|---|---|
| Stream | [stream.md](stream.md) | [img/stream.png](img/stream.png) | [data/stream.json](data/stream.json) |
| Jump | [jump.md](jump.md) | [img/jump.png](img/jump.png) | [data/jump.json](data/jump.json) |
| Tech | [tech.md](tech.md) | [img/tech.png](img/tech.png) | [data/tech.json](data/tech.json) |
| Balanced | [balanced.md](balanced.md) | [img/balanced.png](img/balanced.png) | [data/balanced.json](data/balanced.json) |

Each guide has the same parts: what the style feels like to play, a table of measured ranges per star band, signature patterns (what mappers actually do), pacing and breathers, targets for the generator, and the list of reference maps used. The `.svg` files in `img/` are the sources of the pictures. Each `.json` file holds, for every star band, the 10th / 50th / 90th percentile (p10 / p50 / p90) of every metric, plus how many maps and mapsets it came from. In words: p50 is the typical map, p10 to p90 is the range the middle 80% of the maps fall in.

A note on words: "circle width" is the size of one circle, and all distances are measured in it, so they mean the same on every circle size. Turn angle 0 is straight on and 180 is straight back. The glossary terms (stream, burst, jump, stack, buzz slider, kick slider, kiai and so on) are used the way you use them.

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

- **Simple and readable and Slider-focused have no reference group yet.** No maps were labelled for them, so there are no measured ranges and no pattern pictures. Do not take numbers from another style and call them "simple" or "slider". The nearest indirect evidence is that [tech.md](tech.md) (about half sliders) and [balanced.md](balanced.md) (about a third to a half sliders) are the slider-rich styles in the data. Maps below 4.5 stars were not used at all, because the easy difficulties inside the labelled mapsets do not show any style. To fix this, add reference maps for these two styles (see "Refreshing the numbers").
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

Sample sizes in this band: no style has n below 5, but Stream has exactly 5 maps from 4 mapsets, which is still thin. Balanced counts one map twice (Kakushigoto [Insane] and its AR10 copy have the same notes), so it is 9 distinct maps. In a band of 5 to 10 maps one mapset can pull the median. Jump has the most maps (18) but they are mostly short 0.5 to 2.2 minute cuts. The other bands are weaker (cells are maps / mapsets):

| Band | Stream | Jump | Tech | Balanced |
|---|---|---|---|---|
| 4.5-5.5 stars | 3 / 2 (n<5, weak) | 28 / 8 | 3 / 3 (n<5, weak) | 6 / 5 |
| 5.5-6.5 stars | 5 / 4 | 18 / 7 | 9 / 6 | 10 / 7 |
| 6.5+ stars | 3 / 3 (n<5, weak) | 1 / 1 (n<5, weak, one map) | 9 / 4 | 3 / 2 (n<5, weak: 2 different maps) |

What stands out in the 5.5-6.5 table:

- **Jump is the odd one out on direction.** About 83% of its turns are sharp and almost none are straight-on, against roughly a third sharp in the other three. It also has the biggest hops, no streams, and almost no fast tapping.
- **Tech has the most sliders** (half of all objects), the most kick and buzz sliders and by far the most odd rhythm (9.8% of gaps, mostly 3/4-beat gaps according to [tech.md](tech.md)), with the smallest hops.
- **Stream has the most streams, the most fast tapping and the straightest movement.** It is also the most repetitive on purpose: long even runs repeat.
- **Balanced sits in between**: density, hop size and AR are close to Stream and Tech, and its streams are mostly short bursts rather than long walls.
- **Density and approach rate do not separate the styles much.** Objects per minute are 254 to 302 and AR is 9.3 to 9.4 in all four. The styles differ in what the notes do (distance, angle, sliders, rhythm), not in how many there are.

## Shared rules (every style obeys these)

**1. The 10 to 15 second tapping rule, and breathers.** A player should not spam-tap for longer than about 10 to 15 seconds. Sliders and buzz sliders give the hands a break and can bring a player back to life, as in the map Honesty. What the human maps actually show depends on how you measure:

- *Fast tapping* (8 or more key presses in one second, real stream speed): the human maps mostly follow the rule. Longest fast-tap stretch medians at 5.5-6.5 are 5 s (stream), 0 s (jump), 4 s (tech) and 4 s (balanced). The exceptions are in [stream.md](stream.md): the 6.5+ stream band has a median of 15 s, and DISHONEST has a 44 s stretch.
- *Any tapping without a rest* (a rest is a gap of 1.45 beats or more, or a slider held about one beat): the human maps break the rule in every style except jump. Medians at 5.5-6.5 are 30 s (stream), 8.6 s (jump), 52.7 s (tech) and 24 s (balanced). Mostly this is half-beat hops and short sliders, not stream speed.
- So the 10-15 s interval is the project's rule, not something the human maps follow by that second measure. The generator is meant to be stricter than the humans. Its presets cap tapping with `max_tap_s`: 10 s for stream, 11 for tech, 12 for jump (and for balanced, the default), 14 for simple, 15 for slider (see [osumapgen/params.py](../../osumapgen/params.py)). Each style guide ends its pacing part with a rule that fits both the data and your idea.
- What the humans use as breathers, in every style: a short slider at the end of a phrase, a gap of one beat or more, a long slider held about a beat or more, a buzz or kick slider as a connector, a spinner, and switching technique by section.

**2. Variety, no repetition.** Maps change shape constantly: spacing steps up inside a stream, a phrase ends differently each time, sections switch between jump, slider and burst windows. The analyzer has a repetition number, `rep8_pct`: the share of 8-note windows with the same rhythm, distance and turn that occur 3 or more times. Medians at 5.5-6.5: 0 (jump), 0.5 (tech), 2.6 (balanced) and 13.6 (stream, where long even runs are natural). A generated map far above the number for its style probably copies a pattern too often.

**3. Star bands matter more than style.** Within one style, difficulty rises with stars through density, spacing and run length, and the same style looks very different in different bands. For stream the median stream share goes 28.6, 49.1, 56.7% and objects per minute 264, 302, 345 across the three bands. For jump the mean hop goes 2.7, 3.06, 3.43 circle widths. Balanced shifts from a slider-and-burst map to a jump-and-slider map as stars go up (see [balanced.md](balanced.md)). Always compare against the band of the target star rating first and use the style second. Do not borrow the p10-p90 range of another band to fill a gap: the docs say where a band has no data or only one or two maps. Below 4.5 stars there are no ranges at all.

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
   The four fields `style`, `min_stars`, `excluded` and `note` at the top of each data file were added by hand. Copy them from the old file into the new one, update the note if the sample size changed, then replace `data/<style>.json` with the new file.
4. Update the hand-written numbers. The style pages quote their tables and many sentences from the data and from the raw maps, and they do not update themselves. Go through the "Measured profile" table, the "Targets" list, the "Reference set" table and the sample-size warnings of each affected page, then redo the comparison tables on this page.
5. If a new reference changes what a pattern looks like, redraw that picture (`tools/pattern_svg.py`, then `tools/svg_to_png.mjs`) and replace the files in `img/`.
6. Keep the maps local. Do not commit `references/` and do not copy beatmaps or audio into `docs/`.

## Limitations

- **Small samples.** Several bands have fewer than 5 maps (marked "weak" above), and with 3 maps the median and the 90th percentile are the same map. Even the larger bands are dominated by a few mapsets (each guide lists how many maps each mapset gave). Read p10-p90 as a rough range, not as a distribution.
- **Labels are by mapset.** The user labelled whole mapsets, and a mapset can hold a map that does not fit its label. An audit already removed some (listed in the "Reference set" part of each guide), and the guides point out bands that still look mixed, for example the 4.5-5.5 stream band. Difficulties below 4.5 stars were not used because they do not show the style.
- **Metrics are approximations.** The analyzer measures timing and distances, not how a map plays: it cannot see flow quality, readability, hitsounds or whether a pattern fits the music. Slider curves are approximated, "stream" means a run of 4 or more objects with gaps of 0.3 beat or less, and tapping stretches depend on the definition of a rest (see the pacing rule above). No audio was analysed for the style pages, so statements about choruses (kiai) and breaks come from timing flags in a few maps, not from the music.
- **Pattern descriptions are readings.** Statements marked "in the examples I read" come from looking at a handful of maps and are not statistics.
- **Cut and sped-up maps.** Many reference maps are short cuts of songs (some from nightcore versions), which caps the longest stretches and makes per-map counts such as kick or buzz sliders hard to compare.
- **Two generator styles have no data** (Simple and readable, Slider-focused), and above 6.5 stars only tech has more than 3 maps.
- **No human playtest of generated maps yet.** Matching these numbers shows a generated map resembles human maps on paper. It does not show that it is fun or fair to play. That needs players.

## See also

- [stream.md](stream.md), [jump.md](jump.md), [tech.md](tech.md), [balanced.md](balanced.md)
- Tools: [analyze_maps.py](../../tools/analyze_maps.py), [style_profiles.py](../../tools/style_profiles.py), [compare_generated.py](../../tools/compare_generated.py), [pattern_svg.py](../../tools/pattern_svg.py), [svg_to_png.mjs](../../tools/svg_to_png.mjs)
- Generator code: [params.py](../../osumapgen/params.py) (the style presets), [rhythm.py](../../osumapgen/rhythm.py), [placement.py](../../osumapgen/placement.py)
