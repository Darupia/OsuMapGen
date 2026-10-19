# Style documentation: start here

This folder describes how human mappers build four kinds of osu!standard maps (stream, jump, tech, balanced), with measured numbers and pictures, so the generator can be tuned toward real maps. Read this page first. It tells you which style page to open and what rules every style shares.

Everything here comes from 172 reference difficulties kept locally in `references/` (that folder is git-ignored, so the maps and audio never leave the machine). The docs only contain titles, measured numbers and short descriptions of patterns.

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

Each style guide has the same parts: what the style feels like to play, a table of measured ranges per star band, signature patterns (what mappers actually do), pacing and breathers, targets for the generator, and the list of reference maps used. The `.svg` files in `img/` are the sources of the pictures. Each `.json` file holds, for every star band, the 10th / 50th / 90th percentile (p10 / p50 / p90) of every metric, plus how many maps and mapsets it came from.

A note on words: "circle width" is the size of one circle, and all distances are measured in it, so they mean the same on every circle size. The glossary terms (stream, burst, jump, stack, buzz slider, kick slider, kiai, linear and circular flow and so on) are used the way you use them.

## Which page should I read?

Pick the feeling you want, then open the page.

| If the target map should feel like... | Read | Closest generator style (in `osumapgen/params.py`) |
|---|---|---|
| Fast continuous runs and bursts of notes, stamina, a wall of notes in the chorus | [stream.md](stream.md) | Stream-focused (`stream`) |
| Big snaps across the screen, half-beat hops, short sliders between groups, no streams | [jump.md](jump.md) | Jump-focused (`jump`) |
| Constantly changing rhythm, lots of short sliders, kick and buzz sliders, stacks, little bursts | [tech.md](tech.md) | Technical (`tech`) |
| A mix that changes with the music: hops and sliders in verses, bursts and streams in the loud parts | [balanced.md](balanced.md) | Balanced mix (`mix`, a different preset per section) and the single `balanced` preset |
| Calm, readable, beginner-friendly | no page yet | Simple and readable (`simple`) |
| Mostly sliders, slider art style | no page yet | Slider-focused (`slider`) |
| "Pick for me" | depends on what Auto chooses | Auto (`auto`) |

Things to know about this table:

- **Simple and readable and Slider-focused have no reference group yet.** We have no maps labelled for them, so there are no measured ranges for them. Do not take numbers from another style and call them "simple" or "slider". The nearest evidence is indirect: [tech.md](tech.md) and [balanced.md](balanced.md) both contain many sliders (see the comparison below), and the star bands below 4.5 were not used at all (the easy difficulties inside the labelled mapsets are not representative of any style). To fix this, add reference maps for these two styles (see "Refreshing the numbers").
- **Auto** looks at the song and picks one of the single presets: simple for low star targets, stream for dense 1/4 music at a moderate tempo, jump for fast or sparse music, otherwise balanced (see `resolve_style` in `osumapgen/params.py`). So it needs the page of whichever style it picked.
- **Balanced mix** gives each section of the song its own preset (slider or simple in quiet parts, stream, jump or tech in loud parts, and so on) and avoids repeating the same preset next to itself. A mixed map can therefore be checked against all four pages, section by section; [balanced.md](balanced.md) describes the human maps that do this on their own.
- The page you pick is a starting point. Star rating matters at least as much as the style (see the shared rules).

## The four styles side by side (5.5-6.5 stars, medians)

This band is the best covered one. Every cell is the median (p50) of the maps in that band, copied from the `data/*.json` files. Distances are in circle widths.

| Median at 5.5-6.5 stars | Stream | Jump | Tech | Balanced |
|---|---|---|---|---|
| Maps / mapsets | 5 / 4 | 17 / 7 | 9 / 6 | 10 / 7 |
| Objects per minute | 302 | 256 | 277 | 279 |
| Stream % of objects | 49.1 | 0 | 18.3 | 28.5 |
| Longest stream run (notes) | 41 | 0 | 21 | 17 |
| Stream spacing | 0.57 | none | 0.56 | 0.46 |
| Jump distance, mean | 2.35 | 3.12 | 2.01 | 2.41 |
| Jump distance, 90th pct | 3.6 | 4.3 | 3.16 | 3.77 |
| Sharp turns % | 34 | 84.8 | 37.8 | 32.6 |
| Straight-on turns % | 33.9 | 0.6 | 22.7 | 21.9 |
| Sliders % of objects | 27.7 | 37.7 | 50 | 34.7 |
| Slider repeat % | 17.1 | 2.1 | 4.9 | 5 |
| Buzz sliders per map | 0 | 0 | 2 | 0 |
| Kick sliders per map | 8 | 0 | 16 | 5 |
| Stacks % | 4.5 | 2.1 | 7.2 | 4.8 |
| Odd rhythm % | 1.8 | 0 | 9.8 | 1.1 |
| Longest tapping stretch (s) | 30 | 8.6 | 52.7 | 24 |
| Longest fast-tap stretch (s) | 5 | 0 | 4 | 4 |
| Total fast-tap time per map (s) | 30 | 0 | 24 | 16 |
| AR / OD / CS | 9.3 / 9 / 4 | 9.3 / 9 / 3.8 | 9.4 / 8.4 / 4 | 9.3 / 8.5 / 4 |

Sample size: no band in this table has n below 5, but Stream has exactly n = 5 from 4 mapsets, which is still thin, and Balanced counts one map twice (two difficulties with the same notes and a different AR), so it is 9 distinct maps. In a band of 5 to 10 maps one mapset can pull the median. The other bands are weaker (n is maps, then mapsets):

| Band | Stream | Jump | Tech | Balanced |
|---|---|---|---|---|
| 4.5-5.5 stars | 3 / 2 (weak) | 28 / 8 | 3 / 3 (weak) | 6 / 5 |
| 5.5-6.5 stars | 5 / 4 | 17 / 7 | 9 / 6 | 10 / 7 |
| 6.5+ stars | 3 / 3 (weak) | 2 / 2 (weak) | 9 / 4 | 2 files of 1 map (weak) |

What stands out in the 5.5-6.5 table:

- **Jump is the odd one out on direction.** About 85% of its turns are sharp and almost none are straight-on, versus roughly a third sharp in the other three. It also has the biggest hops, no streams, and almost no fast tapping.
- **Tech has the most sliders** (half the objects), the most kick and buzz sliders and by far the most odd rhythm (9.8% of gaps, mostly 3/4-beat gaps according to [tech.md](tech.md)), with the smallest hops.
- **Stream has the most streams and the most fast tapping**, and the straightest movement.
- **Balanced sits in between**: density, hop size and AR are close to Stream and Tech, and streams are mostly short bursts rather than long walls (median run 6 notes, and the median of each map's longest run is 17).
- **Density and approach rate do not separate the styles much.** Objects per minute are 256 to 302 and AR is 9.3 to 9.4 in all four. The styles differ in what the notes do (distance, angle, sliders, rhythm), not in how many there are.

## Shared rules (every style obeys these)

**1. The 10 to 15 second tapping rule, and breathers.** A player should not spam-tap for longer than about 10 to 15 seconds. Sliders and buzz sliders give the hands a break and can bring a player back to life, as in the map Honesty. What the human maps actually show depends on how you measure:

- *Fast tapping* (8 or more key presses in one second, real stream speed): the maps mostly follow the rule. Longest fast-tap stretch medians at 5.5-6.5 are 5 s (stream), 0 s (jump), 4 s (tech) and 4 s (balanced). The exceptions are in the stream guide: the 6.5+ stream band has a median of 15 s and DISHONEST has a 44 s stretch.
- *Any tapping without a rest* (a rest is a gap of 1.5 beats or more, or a slider held about one beat): the human maps break the rule in every style except jump. Medians at 5.5-6.5 are 30 s (stream), 8.6 s (jump), 52.7 s (tech) and 24 s (balanced). Mostly this is half-beat hops and short sliders, not stream speed.
- So the 10-15 s interval is the project's rule, not something the human maps follow by that second measure. The generator is meant to be stricter than the humans (the presets in `osumapgen/params.py` cap tapping at `max_tap_s`: 10 s for stream, 11 for tech, 12 for jump, 14 for simple, 15 for slider). Each style guide ends with a rule that fits both the data and your idea.
- What the humans use as breathers, in every style: a short slider at the end of a phrase, a gap of one beat or more, a long slider held about a beat or more, a buzz or kick slider as a connector, a spinner, and switching technique by section.

**2. Variety, no repetition.** Maps change shape constantly: spacing steps up inside a stream, a phrase ends differently each time, sections switch between jump, slider and burst windows. The analyzer has a repetition number (`rep8_pct`, the share of 8-note windows with the same rhythm, distance and turn that occur 3 or more times). Medians at 5.5-6.5: 0 (jump), 0.5 (tech), 2.6 (balanced) and 13.6 (stream, where long even runs are natural). Where a generated map is far above these, it is probably copying a pattern too often.

**3. Star bands matter more than style.** Within one style, difficulty rises with stars through density, spacing and run length, and the same style looks very different in different bands. Medians for stream: stream % of objects 28.6 (4.5-5.5), 49.1 (5.5-6.5), 56.7 (6.5+); objects per minute 264, 302, 345. Balanced shifts from a slider-and-burst map to a jump-and-slider map as stars go up (see [balanced.md](balanced.md)). Always compare against the band of the target star rating first, and use the style choice second. Do not read the p10-p90 range of a different band to fill a gap; the docs say where a band has no data. Below 4.5 stars there are no ranges at all.

## How to measure a generated map

Run everything from the project root. The tools need the project's Python packages (they use `rosu-pp-py` for star ratings; see `requirements.txt`). They only use the standard library otherwise.

**1. Measure a map.** One line per map with stream %, hop size, slider % and the timeline:

```
python tools/analyze_maps.py "output/test_pack/<generated map>.osu"
```

For every number (the same names as in the `data/*.json` files) write it to a file and open that file:

```
python tools/analyze_maps.py "path/to/map.osu" -o my_map.json
```

The timeline is one letter per 10 seconds: S stream, J jump, L slider-heavy, B bursts, m mixed, `.` rest. Definitions of every metric are at the top of [tools/analyze_maps.py](../../tools/analyze_maps.py). Then compare the generated map with the "Measured profile" table or the "Targets for the generator" list in the style page for the same star band, and with the `data/<style>.json` band for exact p10 / p50 / p90. A number outside p10-p90 is not an error by itself (those are only the middle 80% of a small set), but several in a row mean the map does not feel like that style.

**2. Look at the patterns.** Make a picture of a section of the map and compare it with the pictures in `img/`:

```
python tools/pattern_svg.py out.svg --panel "map.osu|61.0|69.0|stream section"
python tools/pattern_svg.py out.svg --auto "map.osu|jump|8|jump excerpt" --auto "map.osu|stream|8|stream excerpt"
node tools/svg_to_png.mjs out.svg out.png 1.2
```

The first form draws the seconds you name (file, start, end, label). The second lets the tool find the best excerpt of a kind in the map: stream, jump, slider, buzz, stack or odd. Numbers are play order and colours run from blue (first) to orange (last). The PNG step needs the Chromium that Playwright ships; it is a developer helper, not a project dependency.

**3. Compare to a band's full table.** To print every percentile of a style yourself:

```
python tools/style_profiles.py references/_analysis/metrics.json --group jump --min-stars 4.5
```

## Refreshing the numbers when new references are added

1. Put the new maps in `references/<group>/<mapset>/` where `<group>` is `stream`, `jump`, `tech` or `balanced`. The group comes from the folder name, so label whole mapsets. A new group folder such as `simple` or `slider` works the same way and would give those two generator styles their first page.
2. Measure everything again:
   ```
   python tools/analyze_maps.py references/ -o references/_analysis/metrics.json
   ```
3. Rebuild each style's data file. Reuse the exclusions that are already recorded in the `excluded` field of the old `data/<style>.json` (the maps the audit judged mislabeled), once per entry:
   ```
   python tools/style_profiles.py references/_analysis/metrics.json --group tech --min-stars 4.5 --exclude "<name from the old excluded list>" --json > tech_new.json
   ```
   The tool output has the percentiles and the sample sizes. The four fields `style`, `min_stars`, `excluded` and `note` at the top of each data file were added by hand, so copy them from the old file into the new one and update the note if the sample size changed. Then replace `data/<style>.json` with the new file.
4. Update the hand-written numbers. The style pages quote their tables and many sentences from the data and from the raw maps, and they do not update themselves. Go through the "Measured profile" table, the "Targets" list, the "Reference set" table and the sample-size warnings of each affected page, then redo the comparison table above.
5. If a new reference changes what a pattern looks like, redraw that picture (`tools/pattern_svg.py`, then `tools/svg_to_png.mjs`) and replace the files in `img/`.
6. Keep the rule that the maps stay local. Do not commit `references/` or copy beatmaps or audio into `docs/`.

## Limitations

- **Small samples.** Several bands have fewer than 5 maps (marked "weak" in the table above), and with 3 maps the median and the 90th percentile are the same map. Even the larger bands are dominated by a few mapsets (the guides list how many maps each mapset gave). Read p10-p90 as a rough range, not as a distribution.
- **Labels are by mapset.** The user labelled whole mapsets, and a mapset can hold a map that does not fit its label. An audit already removed some (listed in the "Reference set" part of each guide), and the guides point out bands that still look mixed, for example the 4.5-5.5 stream band. Difficulties below 4.5 stars were not used because they do not show the style.
- **Metrics are approximations.** The analyzer measures timing and distances, not how a map plays: it cannot see flow quality, readability, hitsounds, or whether a pattern fits the music. Slider curves are approximated, "stream" means a run of 4 or more objects with gaps of 0.3 beat or less, and tapping stretches depend on the definition of a rest (see the pacing rule above). No audio was analysed for the style pages, so statements about choruses (kiai) and breaks come from timing flags in a few maps, not from the music.
- **Pattern descriptions are readings.** Statements marked "in the examples I read" come from looking at a handful of maps and are not statistics.
- **Cut and sped-up maps.** Many reference maps are short cuts of songs (some from nightcore versions), which limits the longest stretches and makes per-map counts such as kick or buzz sliders hard to compare.
- **Two generator styles have no data** (Simple and readable, Slider-focused), and nothing above 6.5 stars is solid except in the tech band.
- **No human playtest of generated maps yet.** Passing these numbers shows a generated map resembles human maps on paper. It does not show that it is fun or fair to play. That needs players.

## See also

- [stream.md](stream.md), [jump.md](jump.md), [tech.md](tech.md), [balanced.md](balanced.md)
- [tools/analyze_maps.py](../../tools/analyze_maps.py), [tools/style_profiles.py](../../tools/style_profiles.py), [tools/pattern_svg.py](../../tools/pattern_svg.py), [tools/svg_to_png.mjs](../../tools/svg_to_png.mjs)
- [osumapgen/params.py](../../osumapgen/params.py) (the style presets), [osumapgen/rhythm.py](../../osumapgen/rhythm.py), [osumapgen/placement.py](../../osumapgen/placement.py)
