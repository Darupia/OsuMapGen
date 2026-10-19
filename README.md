# OsuMapGen — one-click osu!standard beatmap generator

Pick an MP3, type a star rating, press **Generate**, get a validated `.osz` for the whole song.
Everything runs locally. Nothing is uploaded, and no API key or Claude conversation is needed.

## Start

1. Double-click **`Start OsuMapGen.bat`**.
   The first run sets itself up (about 150 MB of packages from PyPI, once, no admin rights).
2. Click **Browse...** and choose an MP3.
3. Enter target stars (e.g. `2.5`, `4.0`, `5.5`, `7.0`). Optionally choose a style; **Auto** is fine.
4. Click **Generate** and wait (usually 5–20 seconds).
5. Click **Open in osu!** to import the map, or **Open Output Folder** to see the files.

**osu! username:** on first launch the app asks for your osu! username and writes it into every map
as the *Creator*, which is the name osu! checks when you upload a map. It is **case-sensitive**: type it
exactly as it appears on your osu! profile ("Peppy" is not "peppy"). It's optional. Without it, maps
are credited to "OsuMapGen". You can change it any time in the main window.

**Styles** change the structure of the map, not just its look, at the same star rating: Stream-focused adds long 1/4 runs with tight spacing; Jump-focused has no streams and wide spacing; Slider-focused uses sliders on most gaps (down to half a beat); Technical mixes sharp angles with short and repeat sliders; Simple keeps rhythm sparse and spacing small. Available styles: Auto, Simple and readable, Stream-focused, Jump-focused, Technical, Slider-focused, or
**Balanced mix (all styles)**. The mix gives each section of the song the preset that suits it and
rotates through all of them: streams where the music has fast runs, jumps on hard-hitting parts,
sliders or simple patterns on calm or held parts, technical and balanced patterns on verses and builds.
The overall star target still applies to the whole map. The result window and `report.txt` list which
style each section got. Easy maps (below 3★) leave streams and technical patterns out of the mix.

**Full mapset:** tick **Make a full mapset (Easy to your target)** next to the style picker to get
several difficulties of the same song in **one** `.osz`. The song is analysed once. Each difficulty is then
generated and checked separately at 2.0, 3.2, 4.4 and 5.6★, up to your target. Your target is always the
hardest difficulty: spread steps above it (or less than 0.5★ below it) are left out, and a target above
5.6★ adds one more on top. Each difficulty is named by its estimated stars, using osu!'s usual names
(Easy < 2.0, Normal < 2.7, Hard < 4.0, Insane < 5.3, Expert < 6.5, Expert+). All of them share
`audio.mp3`, the title, the artist and the creator. The result panel and `report.txt` list every
difficulty with its requested and estimated stars. If one difficulty fails validation, the others are
still exported, and the report and status line say which one was **skipped** (its draft is kept as
`INVALID DRAFT - ...osu`). From the command line, add `--mapset`.

**Map length:** choose *Full song*, 1:00, 1:30 (TV size), 2:00, 2:30 or 3:00, or type your own
(for example `1:45`). The app picks the best part of the song for that length. It starts and ends on
section boundaries, keeps the most intense part (usually the chorus), and adds a short fade-out. It
cuts that part to a new MP3 for the map; your original file is never changed. If the song is already
about that long, the whole song is mapped.

**Shorter maps are more detailed than longer ones.** Every section is generated several times and the
cleanest version is kept: the one with the fewest overlapping notes, the least copy-paste and the most
varied angles and patterns. A 1-minute map compares 6 versions per section, 1:30 compares 4, 2:00
compares 3, 3:00 compares 2, and songs of about 4 minutes or more use 1. The star target is
re-checked afterwards. On real songs this raised the readability score of 1:30 maps by 3-14%. The
report shows which part was mapped and how many versions were compared. On the command line, use
`--length 1:30`.

Your last song folder, stars, style, username, mapset choice, map length and output folder are remembered.
Click **Optional details** to correct the title or artist, or to change the output folder.

**Requirements:** Windows with Python 3.10–3.13 (3.12 is installed on this PC).
If Python is missing, the setup offers to install it with `winget`, or tells you where to download it.
FFmpeg is optional: it is used when present, otherwise the built-in decoder reads the MP3.

If something breaks, double-click **`Setup or Repair.bat`**. It rebuilds the private environment in
`%LOCALAPPDATA%\OsuMapGen\venv` and changes nothing else on your system.

## DarupiMapper.exe (single-file app)

`DarupiMapper.exe` is the same generator packaged as one Windows program: no Python, no setup, no packages to
download. Double-click it to open the window; it also accepts the command-line options below
(`DarupiMapper.exe song.mp3 4.5 --style "Jump-focused"`).

* **Where to get it:** every push to GitHub builds it on a Windows machine, runs the tests, opens the window once as
  a self-test and generates a real map from audio before accepting the build. Open the repository's **Actions** tab,
  pick the latest "Build DarupiMapper.exe" run and download the `DarupiMapper-windows` artifact (a zip holding the exe).
* **Build it yourself:** double-click **`Build DarupiMapper.bat`** (needs the environment from `Setup or Repair.bat`).
  The result is `dist\DarupiMapper.exe`. PyInstaller is used only to build; it is not a runtime requirement.
* **Expect:** about 110 MB, a few seconds of start-up while it unpacks, and a Windows SmartScreen / antivirus prompt
  because the file is not code-signed ("More info" > "Run anyway"). Settings and logs go to the same folders as the
  Python version.

## Mapping styles and how they were tuned

The styles (Stream-focused, Jump-focused, Technical, Balanced mix, ...) are tuned against measurements of real
human maps. [`docs/styles/Instruction.md`](docs/styles/Instruction.md) is the entry point: it explains each style
with measured ranges and pictures, and [`docs/styles/Generator_status.md`](docs/styles/Generator_status.md) shows how
closely the generator matches them today. The measuring tools live in `tools/` (`analyze_maps.py`,
`style_profiles.py`, `compare_generated.py`, `pattern_svg.py`).

## What you get

Each run creates a new folder in `Documents\OsuMapGen Output\` (names never collide):

| File | Contents |
|---|---|
| `Artist - Title (OsuMapGen) [Generated 4.0 Stars - Balanced].osu` | the beatmap (format v14) |
| `audio.mp3` | your song, copied unchanged |
| `Artist - Title (4.0 stars).osz` | package for import into osu! |
| `report.txt` / `report.json` | requested and estimated stars, timing, sections, coverage, validation, warnings |
| `preview with clicks.mp3` | your song with a click on every note (higher pitch = new combo, softer = slider end/repeat) — check the timing by ear without osu!. Not part of the `.osz`. Falls back to `.wav` if no MP3 encoder is available |
| `background.jpg` / `.png` | only if the MP3 has embedded cover art: used as the map background and packaged in the `.osz` |

**Play timing preview** in the result panel opens the click preview in your default player: every click
should land on a beat or sound in the song. Clicks that drift ahead of or behind the music mean the
detected timing (BPM/offset) is off for that part of the song.

## Star ratings: what the numbers mean

* **Requested:** the number you typed. It is a target, never written into the map as a claim.
* **Estimated:** calculated with **rosu-pp** (a Rust port of osu!'s official difficulty calculator),
  using both the lazer and stable algorithms. The generator adjusts rhythm density, spacing, stream
  length and slider use until the estimate is close to the target (default tolerance ±0.5).
* **Client rating:** what your installed osu! shows after import. It is not read automatically.
  It should match the lazer estimate unless the game's algorithm has changed since rosu-pp 4.0.2.

If a target can't be reached without artificial density or absurd jumps, the closest musically
reasonable map is kept and the report says why. For example, a 140 BPM song tops out around 6★.

## How it works (pipeline)

1. **Decode** the full file (FFmpeg or libsndfile) and check that nothing was truncated.
2. **Analyse** the audio: spectral-flux onsets in low, mid and high bands, loudness, and where the
   music starts and ends (trailing silence is ignored).
3. **Timing:** whole-song phase-coherence fitting of the BPM and offset, at sub-millisecond
   resolution. Tempo changes are added only when sustained and clearly better than the current
   tempo. Drifting tempo is split only if that measurably reduces the timing error.
4. **Structure:** bar-level self-similarity finds sections. Each gets an intensity
   (intro / verse / build / chorus / breakdown / outro), and silent stretches become breaks.
   Kiai is set on choruses.
5. **Rhythm:** each section's intensity and the difficulty knob set a density level. Objects go on
   beats and onsets that are actually in the audio; streams appear only where the music has
   continuous 1/4 notes. Sliders follow held sounds or end on an un-mapped onset.
6. **Placement:** pattern-driven movement (flow, wave, triangle, square, zigzag, star,
   back-and-forth). Streams are planned as whole arcs or S-curves. Every position is checked
   against the playfield and against objects and slider bodies still on screen.
7. **Star refinement:** bounded search (at most 12 tries) over the knob, scored by rosu-pp.
8. **Validation:** the written file is re-parsed and checked for structure, timing points,
   object syntax, slider durations and paths, overlaps, playfield bounds, audio reference,
   metadata, coverage of every section up to the song's end, grid snapping, repetition, density
   versus intensity, and the `.osz` contents. Sections that fail are regenerated (at most 3 times).
   A map that still fails is **not** exported as an `.osz`.

## Command line (optional)

```bash
"%LOCALAPPDATA%\OsuMapGen\venv\Scripts\python.exe" -m osumapgen "song.mp3" 4.5 --style "Jump-focused"
"%LOCALAPPDATA%\OsuMapGen\venv\Scripts\python.exe" -m osumapgen "song.mp3" 6.0 --mapset
```

## Tests

Double-click **`Run Tests.bat`** (or run `python -m pytest tests`).
The tests use **procedurally synthesised, copyright-free songs** with exact ground truth:
short, full-length (2:47), ~6-minute, ambiguous tempo, tempo change (120→150), long silent break,
quiet intro, trailing silence and triplet feel. They also cover invalid files, missing dependencies,
malformed objects, unreachable star targets, `.osz` packaging, determinism and the GUI.

## Known limitations

* The automated tests use synthetic audio. Real songs were checked by hand: 8 rock/metal/electronic
  tracks (2:13–4:54, 123–220 BPM) at 2.5★, 4.5★ and 6.5★. All maps were valid with 100% coverage,
  and 23 of 24 were within 0.31★ of the target. Beat grids were checked against the audio, but
  nobody has played them yet.
* 4/4 meter is assumed. Waltzes and odd meters get a valid grid, but bar lines may be placed oddly.
* The beat grid offers 1/4 and 1/3 subdivisions per section (no 1/6 or 1/8 snaps).
* Hitsounds are basic (finish, clap and whistle on accents). There is no storyboard, and a background image only when
  the MP3 has embedded cover art.
* Maps were checked with an independent parser and rosu-pp. They were not opened in osu! during
  development; please report anything osu! rejects.
