# Handoff prompt: paste everything below the line into your earlier Claude chat

(You can also give Claude this file. It is written so a Claude that has never seen the cloud session understands it.)

---

Hi Claude. I have been working on my osu!standard map generator ("OsuMapGen", now also called "DarupiMapper") in a separate cloud session. That session made a lot of changes. I want to continue on my own PC with you, so please read this, check my local copy against it, and bring it up to date.

## The short version

1. The generator now makes four mapping styles (Stream, Jump, Tech, Balanced) that behave like real human maps, because I measured about 170 human maps and tuned the generator to match.
2. The generator stops long unbroken tapping: stream-speed tapping and general tapping are capped, with sliders and buzz sliders as "breathers".
3. There are new tools to measure any map, written docs that explain each style with measured numbers and pictures, and a way to build a single `DarupiMapper.exe`.
4. Everything is on GitHub: repository `Darupia/OsuMapGen`, branch `claude/funny-faraday-xzz6cf`, latest commit `80effff` ("Style docs: final critic corrections"). That branch is the source of truth. If my local folder differs from it, the branch wins unless I tell you otherwise.

## First, check my local copy (do this before anything else)

My local folder should be named `OsuMapGen-claude-funny-faraday-xzz6cf` or similar. Another chat may have changed files by mistake. Please:

- If it is a git checkout: run `git status`, `git log -1`, and `git fetch`. It should be clean and at `80effff` (or newer). If it has changes I did not make, show them to me before you discard anything.
- If it is just a downloaded folder: compare it with the list below. Anything missing means I should download the branch again as a zip.
- Run `python -m pytest tests -q`. 70 tests passed in the cloud (the GUI tests could not run there because the cloud has no tkinter, so please run them here and tell me if they fail).

Files that should exist (all new or changed since the original version):

```
darupimapper.py                  launcher for the exe (GUI by default, CLI with arguments, hidden --selftest)
DarupiMapper.spec                PyInstaller recipe: one-file windowed exe called DarupiMapper.exe
Build DarupiMapper.bat           double-click build of dist\DarupiMapper.exe on Windows
.github/workflows/build-exe.yml  GitHub builds the exe on Windows and tests it on every push
osumapgen/params.py              style presets (heavily changed)
osumapgen/rhythm.py              rhythm planner (heavily changed)
osumapgen/placement.py           object placement (stacks, stream spacing)
osumapgen/deps.py                small change (repair hint inside the exe)
tests/test_styles.py             new tests for the styles
tools/analyze_maps.py            measures any .osu file
tools/style_profiles.py          per-style, per-star-band ranges from measurements
tools/compare_generated.py       scores generated maps against the human ranges
tools/pattern_svg.py             draws pattern excerpts as SVG
tools/svg_to_png.mjs             SVG to PNG (needs Chromium from Playwright; dev helper only)
docs/styles/Instruction.md       START HERE for the style docs
docs/styles/stream.md jump.md tech.md balanced.md   one guide per style
docs/styles/Generator_status.md  how close the generator is to the human maps, and what is still off
docs/styles/data/*.json          exact measured ranges per style and star band
docs/styles/img/*.png (+ .svg)   pattern pictures
README.md                        updated (exe section, style docs section)
.gitignore                       now ignores references/, output/, build/, dist/
```

## What was done and why (plain language)

### 1. Why I started
The styles in the app did nothing visible: choosing "Jump" or "Stream" gave nearly the same map. Cause: each style only nudged a few numbers, and the star-rating search then re-balanced everything back to the same difficulty. The fix was to make styles structurally different, then to measure real human maps and copy how they really behave.

### 2. Measuring human maps
I uploaded about 60 mapsets that I sorted by hand into four groups: stream, jump, tech, balanced. The cloud session put them in `references/<group>/<mapset>/*.osu`. This folder is deliberately NOT in git (it contains other people's maps), so it only exists in the cloud session. `docs/styles/data/*.json` holds the numbers that were measured from it.

- 179 `.osu` files, 7 of them taiko/catch (skipped), so 172 standard-mode difficulties were measured with `tools/analyze_maps.py`.
- Easy difficulties inside a mapset are not representative, so only 4.5 stars and above were used for the style ranges.
- An audit removed 11 mislabeled maps (for example a "stream" map that has no streams): stream 2, jump 3, tech 2, balanced 4.
- Measured per map: stream share and run lengths, jump distance, sharp-turn share, slider share (repeat, kick, buzz), stacks, odd rhythm (1/3, 1/6, dotted 3/4), longest tapping stretch, longest stream-speed stretch, repetition, and a 10-second timeline (S stream, J jump, L sliders, B bursts, m mixed, . rest).

### 3. What the human maps showed (the main findings)
- Below 7 stars the human maps have almost no streams: 4.5-6.5 star maps are jump or slider/flow maps. Streams only appear in stream-labelled maps and in tech/balanced maps in small bursts.
- Human jump maps (5.5-6.5 stars): about 38% sliders, hops of about 3 circle widths, no streams, about 85% sharp direction changes (back-and-forth), almost no buzz sliders.
- Human stream runs are usually whole beats (5, 9, 13, 17... notes), start after a short slider, end on a short slider (kick, 3-slide, short plain), and spacing steps up inside long runs. After a run the hop is wide.
- Tech maps: about half sliders, many kick sliders, buzz sliders in rows after bursts, stacks, and dotted 3/4-beat rhythm.
- Stacks (notes on the same spot) are common in human maps (2-8% of notes). The generator had none.

### 4. Generator changes (all in `osumapgen/`)
- New style parameters in `params.py` (`MapParams`): `quarter_bias`, `slider_min_gap`, `slider_force`, `slider_repeat`, `stream_fill`, `stack_rate`, `stream_step`, `run_slider_end`, `dotted_rate`, `kick_chance`, `max_tap_s`, `max_fast_tap_s`, `buzz_chance`. Each style (stream, jump, tech, balanced, simple, slider) sets them differently.
- `rhythm.py`:
  - stream presets keep every run the audio supports and cut runs on beat boundaries (5, 9, 13... notes, one beat apart), then end some runs on a short slider (`_aligned_chunks`, `_end_sliders`)
  - tech presets stretch some half-beat gaps to dotted 3/4 beats only where the audio has an onset (`_dotted`)
  - kick sliders (`kick_chance`) and a slider mix per style
  - pacing pass `enforce_pacing`: tracks time since the last rest and turns a good note (a bar start if possible) into a held slider or buzz slider, dropping the notes it covers. It has two limits: any tapping (`max_tap_s`, 10-15 s per style) and stream-speed tapping (`max_fast_tap_s`, 8-10 s, with a longer breather of 3-6 beats afterwards)
- `placement.py`: stacks (`_stacks_here`), stepped spacing inside long streams, wider hops out of a stream.
- Stream presets no longer reach the star target by turning every note into a stream: note density saturates early and spacing carries the rest.
- Jump has many short sliders and no buzz sliders; tech has more sliders and kicks.

My pacing rule (important, keep it): a player should not spam-tap for longer than about 10-15 seconds. Sliders and buzz sliders are the breaks, and they can bring a player back to life (like the map "Honesty").

### 5. Results
Measured with `tools/compare_generated.py` on 96 generated maps (4 styles x 8 songs x 4.5, 6.0 and 7.0 stars):
- all 96 reached their star target and validated
- metrics inside the human p10-p90 range: 40% before tuning, 55% after (jump is best: 16-17 of 18 in the two well-covered bands)
- longest tapping stretch: 10-15 s in every style, no map over 15 s
- longest stream-speed stretch: median 7 s for stream, 12 s at worst (it was 21 s)
- still off (see `docs/styles/Generator_status.md`): stream maps at 6.5+ stars are too dense and too smooth; slider share is low in stream and tech; Simple and Slider-focused were not tuned because I have no reference maps for them

### 6. The exe
- `DarupiMapper.exe` is built with PyInstaller (a build tool only, not a runtime dependency; pinned 6.22.3) from `darupimapper.py` and `DarupiMapper.spec`.
- GitHub Actions (`.github/workflows/build-exe.yml`) builds it on Windows for every push, runs the tests, runs `--selftest` (opens a window and checks dependencies) and generates a real map from audio. The last build passed. Get the exe from the repository's Actions tab, artifact `DarupiMapper-windows` (about 112 MB zip).
- You can also build it here by double-clicking `Build DarupiMapper.bat` (needs the environment made by `Setup or Repair.bat`).
- The window title and output folder inside the app still say "OsuMapGen"; only the exe file name is DarupiMapper. Ask me if I want those renamed.
- The exe is not code-signed, so Windows SmartScreen will warn.
- Nobody has clicked through the GUI of the exe yet.

### 7. Things that are NOT done / not verified
- No human has played any generated map yet. The numbers say they resemble human maps; they cannot say it feels good. I have been testing "test packs" of 5 maps (A stream, B jump, C tech, D balanced mix, E dense stream) on the songs Get Jinxed, This War Is Ours and Honesty at 6 stars, and will report back by map letter and rough place in the song.
- The human ranges come from small samples (3-5 maps in several bands).
- The measuring metrics are approximations (slider curves are approximate; "stream" is gaps of 0.3 beat or less, so very fast songs hide some streams).

## Rules to keep following (from my original brief)
- Treat osu! files as structured data; keep section order; keep timing points and hit objects sorted.
- Generated files go in `output/` (or the app's output folder); never overwrite source audio or existing maps.
- Validate before writing. Prefer readable, deterministic code (same inputs give the same output).
- ASK before adding dependencies or changing files outside the project.
- Never commit beatmaps or audio: `references/` and `output/` stay git-ignored. Never invent song metadata.

## What I want you to do now
1. Check my local copy against the list above and tell me if anything is missing or different (do not overwrite my own changes without asking).
2. If my copy is older than commit `80effff`, tell me the easiest safe way to update it (fresh zip from GitHub, or `git pull`), then run the tests.
3. Read `docs/styles/Instruction.md` and `docs/styles/Generator_status.md`.
4. Re-create the reference folder on my PC. My reference maps are in `C:\Users\jamie\Documents\References`. Sort them into `references\stream`, `references\jump`, `references\tech`, `references\balanced` (one folder per mapset inside each), then run `python tools/analyze_maps.py references -o references/_analysis/metrics.json` so the tools work locally.
5. Then continue with my next requests. The most useful next steps are: rename the app to DarupiMapper everywhere, tune stream maps at 6.5+ stars (angle variety, density), and tune from my playtest feedback.
