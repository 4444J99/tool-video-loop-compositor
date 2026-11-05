# the lab

A playable, modular-synth-style web instrument for the *simultaneous loops* project. N video loops play at once as
edge-to-edge strips, heavily cropped; the more strips, the less zoomed each one is. Every parameter of the engine,
layout, zoom, framing, audio and reveal is a knob, switch or selector with immediate effect. Tap a strip to see the original still.

Plain static ES modules: no build step, no dependencies, no CDN, no network beyond your own origin.

## Run it

Serve a folder that contains `app/` and your dataset folder(s) with any static server:

```sh
# from the repo root (this repo already has app/ and fixtures/):
python3 fixtures/make_fixtures.py          # synthetic test clips -> fixtures/generated/ (needs ffmpeg)
python3 -m http.server 8000
# then open
#   http://localhost:8000/app/?data=/fixtures/generated/
```

For your real data put (or symlink) a dataset folder next to `app/` and point at it:

```
site/
  app/            <- this repo's app/
  lab-data/
    data/clips.json
    media/<id>.mp4
    still/<id>.jpg
```

```sh
cd site && python3 -m http.server 8000      # open  http://localhost:8000/app/?data=/lab-data/
```

* `?data=<base>` is the dataset base (default `./`, i.e. `app/data/clips.json`). It must be **same-origin**; a
  cross-origin base is refused before any request is made.
* Audio is blocked by browsers until a gesture: press **Start sound** (or the *Sound* button in the PATCH module).
* Use a browser that plays H.264/AAC MP4 (Chrome, Safari, Edge, Firefox on most platforms). A plain `http.server` is
  enough (no range requests needed for small proxies).

### Keys and gestures

| | |
|---|---|
| tap / click / Enter on a panel | reveal the original (Esc, tap or the x closes) |
| Space | pause / resume everything (switches and buttons keep Space for themselves) |
| H | hide / show every bit of chrome (on touch a faint "Show" chip returns it) |
| knob: drag, wheel, arrows | Shift = fine (drag/wheel) or x10 (arrows); PageUp/Down = 10 %; Home/End = min/max |
| knob: double-click or Enter | type an exact value (Enter commits, Esc cancels) |
| MOD (floats) | assign an LFO: sine / triangle / random walk / square, rate (Hz), depth (fraction of the half range); the teal arc shows the live value |
| LOCK | exclude a control from RANDOMIZE |
| BYP / RST (module header) | bypass = module runs on its defaults; reset = defaults and no LFOs |

On a phone (<= 640 px wide) the panel becomes a bottom sheet toggled by the *Settings* button; on larger screens it docks
left, right or bottom and floats over the art (it never changes the full-bleed layout).

## How it plays: four dials

A preset is just data (`app/presets.js`) setting these dials; use the PATCH module's preset menu or set them by hand.

* **ORDER** ranks the pool: `none` (seeded shuffle), `captured_at`, `luma`, `saturation`, `hue`, `motion`, `duration`, and the
  tag ordinals `motion_level`, `shot`, `time_of_day`, `people`. Unknown values sort last.
* **PATH** is how each panel travels along that order: `random`, `sequential` (each panel from its own start, spread over the
  order), `converge` / `diverge` (the two ends walk together / apart, per group), `pingpong`, `round` (canon: panel *k* plays
  panel 0's sequence *k x delay* steps later; `voice=clips` plays the very same clips, `voice=tags` plays different clips that
  resemble the leader's), `playlist` (one shared queue dealt to whichever panel changes next; exhausts before repeating),
  `follow` (each panel stays beside its left neighbour). `on_meet` decides what happens at meetings and ends:
  bounce / restart / hold / stop. `window` lets RELATION choose among clips near the path target.
* **RELATION** is the signed pull between the panels that are on screen at the same time: strength -4 (repel) .. +4 (attract),
  temperature, independence, adjacency, signed weights per component (subjects, keywords, scene, mood, colour, tone, motion,
  framing) and per-attribute *contrast* switches (environment nature<->urban, shot near<->far, orientation, time of day, motion).
* **TIMING** holds, stagger, a shared beat grid, cooldown (hard), recency and novelty (soft), swap interval, speed.

No clip is ever on two panels at once (unless the filtered pool has fewer clips than panels). The engine samples a
bounded set of candidates per change, so 6,500 clips cost about a quarter of a millisecond per change.

## Layout and zoom

Panels are strips stacked along the viewport's long axis (columns on wide screens, rows on tall ones, or forced). Rect edges are
integer pixels, adjacent strips share edges (plus the optional few-pixel overlap) and the union covers the viewport at any
N (1..16) and any size or aspect. Each video is a natural-size element scaled by a CSS transform inside an
`overflow:hidden` cell: `scale = max(cover(cell + jitter overscan), cover(cell) x zoom)`, focal point clamped, so the cell is
never left empty. `zoom(N) = max(floor, Z1 / N^gamma)` (defaults Z1 = 8, gamma = 0.6, floor = 1 = plain cover). The ZOOM module
shows a live "zoom x, share of the clip visible %" readout. Zoom 1 means "just covers the strip", so strips get *less* cropped
(more recognisable) as panels are added.

## Framing: a new window for every appearance

The zoom module says *how much* of a clip a strip shows; FRAMING decides *which part*. Every time a panel gets a clip (and,
in `drift` mode, at every hold) `app/framing.js` derives a window `{cx, cy, zoom}` in normalised source coordinates. The
window keeps the strip's aspect ratio, never leaves the source and its zoom is never below cover (including the layout
jitter overscan), so a strip cannot show empty space. The zoom module's curve is the *baseline* (`zoom(N) = max(1, 8 / N^0.6)`
by default); `zoom_jitter` varies each window by +-% around it, live knob changes to the curve apply at once. The same clip
therefore looks different each time it appears, and (in `blend` / `contrast`) depends on what surrounds it. The result is a new
composite made from old footage; cropping also hides much of each photograph, but it is not anonymisation.

| mode | what it does |
|---|---|
| `center` | today's behaviour exactly: the zoom module's focal point (`zoom.focal_mode`) and curve, nothing derived. A test proves it is bit-for-bit the old transform. |
| `random` | a seeded window per appearance (seed + clip + appearance index). |
| `thirds` | a rule-of-thirds point of the clip is placed on a rule-of-thirds point of the window (16 combinations, seeded). |
| `detail` | among K candidates prefers windows with more local colour variance in `grid8`. |
| `blend` | among K candidates picks the window whose edge colours best match the facing edge of the neighbouring panel's current window (`grid8` sampled bilinearly along the edge, `edge_sample` wide). |
| `contrast` | the opposite: maximises the edge difference. |
| `drift` | a slow seeded pan/zoom path through the window range during the hold (Ken Burns); a new hold continues from where the window is; standing still under reduced motion. |

`spread` scales how far from the centre windows may go (0 = always centred). `temperature` 0 always takes the best candidate;
higher is more varied. `neighbour_influence` scales how much the neighbours steer `blend` / `contrast`; `match_on` compares
colour, brightness or hue (weighted by saturation). `vary_per_appearance` off gives a clip the same window every time.
`memory` M: any M consecutive appearances of a clip show M different windows (two windows closer than 8 % of their size count
as the same); it is best effort when the range holds fewer than M distinct windows (e.g. spread near 0). Modes that need colour
use `features.grid8`, else a flat colour from `features.palette`, `hue` or `luma`, else fall back to `random` for that clip.
Changing any FRAMING value re-derives the windows on screen immediately (same appearance, same clips); the other zoom
setting `zoom.focal_mode = drift` additionally wanders the chosen window (not in `drift` mode, which has its own path).
REVEAL > *Outline window* draws the panel's current window on the full still ("where this panel was looking").

## Audio

After Start, one Web Audio graph is built: `video -> MediaElementSource -> slot gain (loudness normalisation, cross-fade)
-> panel bus (size weighting, mute/solo) -> StereoPanner (from the strip's position along the strip axis) -> master (x 1/sqrt(N)
auto-trim) -> limiter -> destination`. Every panel plays at once. Normalisation uses `loudness_db` (missing = unity; boost
capped at +20 dB; `has_audio:false` = silent). Each strip has a VU bar, and M / S buttons on hover (also in the AUDIO module).

**Speech policy** (AUDIO). About one clip in three contains speech (`clip.audio` comes from a local speech screen; no transcript
is ever read or kept). `audio.speech_policy` applies to clips with `audio.speech === true` and to clips carrying any of the flags
`number_sequence`, `email_like`, `introduces_self`, `possible_name`, `long_speech`: `play` (sound as usual), `mute` (**default**: the
picture plays, the clip's gain is 0 and its element is muted), `exclude` (never shown: removed from the pool, replaced if already on
screen). `audio.mute_unscreened` (default on) also mutes clips whose `audio.screened` is not `true`, including clips with no
`audio` record. A malformed `speech` or `flags` value counts as speech. No preset, scene or RANDOMIZE changes either setting;
the tap-to-reveal still shows the original photo, and a muted clip's sound stays muted in the reveal video too.

## Data contract

`<base>data/clips.json`:

```json
{"version":1,"clips":[{
  "id":"UUID-or-opaque-id","video":"media/ID.mp4","still":"still/ID.jpg","duration":2.1,
  "width":540,"height":720,"orientation":"portrait|landscape","has_audio":true,"loudness_db":-37.6,
  "captured_at":"2019-08-17T18:02:11Z",
  "tags":{"subjects":["tree","sky"],"setting":"indoor|outdoor|mixed|unclear","environment":"nature|urban|domestic|workplace|transit|event|studio|unclear",
          "time_of_day":"day|golden_hour|dusk|night|artificial_light|unclear","camera":"locked|handheld|pan|tilt|zoom|tracking|unclear",
          "motion_level":"still|subtle|moderate|intense","shot":"close_up|medium|wide","palette":["blue","green"],"mood":["calm"],"keywords":["tree"],
          "people":{"count":"0|1|2-3|4+","faces_visible":false,"minors_apparent":false},
          "privacy":{"readable_text":false,"license_plate":false,"document_or_screen":false,"location_identifiable":false,"sharing_sensitivity":"low|moderate|high"},
          "safety":{"verdict":"clear"}},
  "features":{"luma":0.5,"luma_spread":0.1,"saturation":0.4,"hue":0.55,"motion":0.05,"palette":[{"hex":"#336699","share":0.4}],
              "grid8":"384 hex chars: 8x8 mean colours of the middle frame, row-major, rrggbb x 64"},
  "audio":{"screened":true,"speech":false,"words":0,"flags":[],"low_confidence":false}}]}
```

`features.grid8` and `audio` are optional; a `grid8` that is not exactly 384 hex characters is ignored. `video` and `still` resolve relative to `<base>`. Every field except `id` and `video` is optional; a missing value is
*unknown*. Records without a usable `id`/`video` are dropped; duplicate ids keep the first.

**Filtering semantics (SOURCE module).** Strings are trimmed and lower-cased before comparing. A *missing* value is
unknown and follows the *Untagged policy* (include by default). A *present but malformed* value (wrong type, unknown
word, e.g. `verdict: 1`, `sharing_sensitivity: "extreme"`, a privacy flag that is an object) is excluded whenever the
matching filter is active. Defaults are cautious: safety verdict `clear`, minors excluded, `license_plate` and
`document_or_screen` excluded; sharing sensitivity is not limited until you lower it. RANDOMIZE never touches SOURCE, the
master level or the limiter.

## Privacy

Everything is local: the page only talks to its own origin (no CDN, fonts, analytics or telemetry), patches live in your
browser's `localStorage`, and exported/imported patches are plain JSON files. The share URL carries only the
configuration (never clips or filenames) in the `#hash`, which browsers do not send to servers. The reveal shows the
original still, so treat the page like the private dataset it displays.

## Patches

PATCH module: save / load / delete named patches (`localStorage`, key `lab.patches.v1`), export / import JSON, copy a share URL
(whole configuration in the hash; opening it restores everything), RANDOMIZE (within each parameter's range, skipping locked
and SOURCE/limiter/speech-policy controls), reset all. Presets change ORDER, PATH, RELATION and TIMING only; *scenes* also set layout, zoom and framing. Nothing here touches the speech policy.

## Debug API (`window.__lab`)

`params()` (stored values), `effective()` (what the engine uses this frame, with LFOs/bypass applied), `set(id, value)`, `config()`,
`engine()` (clip id currently shown per panel), `scheduled()`, `layoutRects()`, `audio()` (per-panel gain, norm, pan, muted, solo, Web Audio
node values), `seed()`, `axis()`, `zoomInfo()`, `framing()` (per panel: clip, appearance index, mode, the derived `window` {cx, cy, zoom}, the `applied` window actually on screen with its corners, colour source, candidate info and the mean colour mismatch with the left/upper neighbour), `reveal()`, `paused()`, `pool()`, `store`, `player`.

## Tests

```sh
npm run test:unit                       # node --test tests/unit/  (engine, layout, framing, speech, params, presets; no dependencies)
python3 fixtures/make_fixtures.py       # once
python3 -m pytest                       # Playwright e2e in headless Chrome ($PORTVS_BROWSER_EXECUTABLE), serves the repo on a random port
npm run docs                            # regenerate the table below from app/params.js
node scripts/gen_config_reference.mjs --check
```

Headless tests cannot hear anything: audio is verified through the Web Audio graph (gain/pan node values, analyser levels,
element mute state), not through speakers.

## Configuration reference

Generated from the parameter registry (`app/params.js`) by `scripts/gen_config_reference.mjs`; the UI is built from the same registry.

<!-- BEGIN CONFIG REFERENCE (generated by scripts/gen_config_reference.mjs; do not edit) -->

_94 parameters._

### SOURCE

Which clips may play at all (privacy and pool filters).

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `source.safety` | Safety verdict | enum | clear / any | clear |  |  | clear: only clips whose safety.verdict is "clear" (missing = unknown, see Untagged; anything else is excluded). any: ignore the verdict. |
| `source.max_sensitivity` | Max sharing sensitivity | enum | low / moderate / high | high |  |  | Clips whose privacy.sharing_sensitivity is above this level are excluded. high = no limit. |
| `source.exclude_privacy` | Exclude privacy flags | multi | subset of readable_text, license_plate, document_or_screen, location_identifiable | [license_plate, document_or_screen] |  |  | Clips flagged with any ticked privacy flag are excluded. Malformed flag values count as flagged. |
| `source.exclude_minors` | Exclude minors | bool | on / off | true |  |  | Exclude clips where people.minors_apparent is true (or malformed). |
| `source.untagged` | Untagged policy | enum | include / exclude | include |  |  | What to do with clips that lack the information a filter needs (no tags, no safety verdict, no date...). Present-but-malformed values are always excluded when the filter is active. |
| `source.year_min` | Year from | int | 1990 to 2040 (step 1) | 1990 | year |  | Earliest capture year allowed. |
| `source.year_max` | Year to | int | 1990 to 2040 (step 1) | 2040 | year |  | Latest capture year allowed. |
| `source.tags_include` | Tags include | list | list of strings | [] |  |  | Comma-separated words; a clip must carry at least one (subjects, keywords, mood, palette, setting, environment, time of day, camera, shot, motion level). Empty = no constraint. |
| `source.tags_exclude` | Tags exclude | list | list of strings | [] |  |  | Comma-separated words; clips carrying any of them are excluded. |
| `source.seed` | Seed | int | 0 to 999999 (step 1) | 0 |  |  | Seed for every random decision. 0 = pick a new seed at each page load. |

### ORDER

What clips are ranked by.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `order.axis` | Axis | enum | none / captured_at / luma / saturation / hue / motion / duration / motion_level / shot / time_of_day / people | none |  |  | What clips are ranked by. none = a seeded shuffle. |
| `order.direction` | Direction | enum | asc / desc | asc |  |  | asc: low to high (oldest first for captured_at). desc: reversed. |

### PATH

How each panel travels along that order.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `path.shape` | Shape | enum | random / sequential / converge / diverge / pingpong / round / playlist / follow | random |  |  | random: any clip. sequential: each panel walks the order from its own start. converge: two ends walk toward the middle. diverge: from the middle outward. pingpong: back and forth. round: canon, every panel plays the same sequence, each later. playlist: one shared queue dealt to whichever panel changes next. follow: each panel stays beside its left neighbour in the order. |
| `path.step` | Step | int | 1 to 64 (step 1) | 1 | positions |  | Positions advanced along the order at each change. |
| `path.wrap` | Wrap | bool | on / off | true |  |  | Sequential: wrap around at the ends. Off: apply "On meet" at the ends. |
| `path.on_meet` | On meet / end | enum | bounce / restart / hold / stop | bounce |  |  | What happens when travellers meet (converge) or reach an end: bounce back, restart, hold the last clip, or stop (freeze the panel). |
| `path.groups` | Groups | int | 1 to 8 (step 1) | 1 |  |  | Converge/diverge: split the order into this many segments, each with its own pair of travellers. |
| `path.delay_beats` | Delay | int | 0 to 16 (step 1) | 2 | beats |  | Round: panel k starts k x delay steps later. Converge/diverge: spacing of panels travelling on the same side. |
| `path.voice` | Voice | enum | clips / tags | clips |  |  | Round: clips = every panel plays the very same clips. tags = later panels play different clips that resemble the leader's clip from k x delay steps ago. |
| `path.window` | Window | int | 0 to 500 (step 1) | 20 | positions |  | Candidates are drawn from this many positions either side of the path target; relation then chooses among them. 0 = exactly the path. |

### RELATION

How simultaneous panels relate: attract, ignore, repel.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `relation.strength` | Strength | float | -4 to 4 (step 0.05) | 0 |  | yes | Signed pull between simultaneous panels: positive attracts (similar clips together), 0 ignores, negative repels. |
| `relation.temperature` | Temperature | float | 0 to 2 (step 0.01) | 0.5 |  | yes | Randomness of the choice among candidates. 0 = always the best scoring; high = nearly uniform. |
| `relation.independence` | Independence | float | 0 to 1 (step 0.01) | 0 |  | yes | Probability that a panel ignores the others when it picks. |
| `relation.adjacency` | Adjacency | float | 0 to 1 (step 0.01) | 0 |  | yes | 0: every other panel counts equally. 1: only neighbouring panels count. |
| `relation.w_subjects` | Subjects | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of shared subjects. |
| `relation.w_keywords` | Keywords | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of shared keywords. |
| `relation.w_scene` | Scene | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of matching setting, environment and time of day. |
| `relation.w_mood` | Mood | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of shared mood. |
| `relation.w_colour` | Colour | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of similar hue. |
| `relation.w_tone` | Tone | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of similar brightness and saturation. |
| `relation.w_motion` | Motion | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of similar amount of motion. |
| `relation.w_framing` | Framing | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of similar shot size and camera movement. |
| `relation.contrast_environment` | Contrast environment | bool | on / off | false |  |  | Prefer clips whose environment differs from the other panels (nature against urban). |
| `relation.contrast_shot` | Contrast shot | bool | on / off | false |  |  | Prefer clips whose shot size differs (near against far). |
| `relation.contrast_orientation` | Contrast orientation | bool | on / off | false |  |  | Prefer clips whose orientation differs (portrait against landscape). |
| `relation.contrast_time` | Contrast time of day | bool | on / off | false |  |  | Prefer clips whose time of day differs (night against day). |
| `relation.contrast_motion` | Contrast motion | bool | on / off | false |  |  | Prefer clips whose motion level differs (still against intense). |

### TIMING

When clips change and how fresh the picks are.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `timing.hold_min` | Hold min | float | 0.5 to 60 (step 0.1) | 4 | s | yes | Shortest time a clip stays in a panel. If min > max the two are swapped. |
| `timing.hold_max` | Hold max | float | 0.5 to 120 (step 0.1) | 10 | s | yes | Longest time a clip stays in a panel. |
| `timing.stagger` | Stagger | float | 0 to 1 (step 0.01) | 0.6 |  | yes | How far apart the panels' first changes are spread. 0 = all together. |
| `timing.synchronized` | Synchronized | bool | on / off | false |  |  | All panels change together on the beat grid. |
| `timing.beat` | Beat length | float | 0.25 to 8 (step 0.05) | 2 | s | yes | Length of one beat; synchronized holds are rounded up to whole beats. |
| `timing.cooldown` | Cooldown | float | 0 to 300 (step 1) | 20 | s | yes | A clip cannot return to any panel for this long after it was shown. Relaxed automatically if the pool is too small. |
| `timing.recency` | Recency | float | 0 to 1 (step 0.01) | 0.5 |  | yes | Soft penalty for clips shown recently. |
| `timing.recency_window` | Recency window | int | 0 to 500 (step 1) | 50 | clips |  | How many recent clips the recency penalty remembers. |
| `timing.novelty` | Novelty | float | 0 to 1 (step 0.01) | 0.3 |  | yes | Bonus for clips not shown yet. |
| `timing.swap_interval` | Swap interval | float | 0 to 60 (step 0.1) | 0 | s | yes | If above 0, a single panel (the one on screen longest) changes every interval instead of independent holds. |
| `timing.speed` | Speed | float | 0.25 to 2 (step 0.01) | 1 | x | yes | Playback rate of every video. |

### LAYOUT

Edge-to-edge strips: count, direction, split, overlap.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `layout.panels` | Panels | int | 1 to 16 (step 1) | 4 |  |  | Number of simultaneous panels (N). |
| `layout.direction` | Strip direction | enum | auto / rows / columns | auto |  |  | auto: strips are stacked along the screen's long axis (columns on wide screens, rows on tall ones). |
| `layout.split` | Split weights | enum | equal / random / golden / custom | equal |  |  | How the screen is divided among the strips. |
| `layout.split_custom` | Custom weights | list | list of numbers | [3, 2, 1] |  |  | Comma-separated relative widths, cycled over the panels (used when split = custom). |
| `layout.overlap` | Overlap | float | 0 to 40 (step 1) | 3 | px | yes | Neighbouring strips overlap by this many pixels. |
| `layout.radius` | Corner radius | float | 0 to 80 (step 1) | 0 | px | yes | Rounded corners (0 keeps the screen perfectly filled). |
| `layout.jitter` | Sideways jitter | float | 0 to 80 (step 1) | 0 | px | yes | Strips sway sideways by up to this much; the video is over-scanned so nothing is left empty. |
| `layout.jitter_rate` | Jitter rate | float | 0.02 to 2 (step 0.01) | 0.2 | Hz | yes | Speed of the sideways sway. |

### ZOOM

How hard each strip is cropped in.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `zoom.z1` | Z1 (zoom at one panel) | float | 1 to 40 (step 0.1) | 8 | x | yes | zoom(N) = max(floor, Z1 / N^gamma). |
| `zoom.gamma` | Gamma | float | 0 to 2 (step 0.01) | 0.6 |  | yes | How quickly the zoom relaxes as panels are added. |
| `zoom.floor` | Floor (1 = cover) | float | 1 to 4 (step 0.01) | 1 | x | yes | Minimum zoom. 1 is plain cover: the crop never gets looser than just filling the strip. |
| `zoom.manual` | Manual override | float | 0 to 60 (step 0.1) | 0 | x | yes | If above 0, use this zoom for every N instead of the curve. |
| `zoom.focal_mode` | Focal point | enum | static / drift | static |  |  | static: each strip looks at a fixed spot of its clip. drift: the spot wanders slowly. |
| `zoom.drift_speed` | Drift speed | float | 0 to 30 (step 0.1) | 3 | cycles/min | yes | Speed of the wandering focal point. |

### FRAMING

Which part of each clip a strip shows: a window derived anew for every appearance.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `framing.mode` | Mode | enum | center / random / thirds / detail / blend / contrast / drift | blend |  |  | center: today's behaviour (the zoom module's focal point). random: a seeded window per appearance. thirds: snap to rule-of-thirds points. detail: prefer windows with more local colour variance (grid8). blend: choose the window whose edge colours best match the facing edge of the neighbouring panel. contrast: the opposite, maximise the edge difference. drift: a slow seeded pan/zoom path through the window range during the hold (Ken Burns style; still under reduced motion). Modes that need colour data fall back to random for clips without any. |
| `framing.spread` | Spread | float | 0 to 1 (step 0.01) | 0.85 |  | yes | How far the window may move from the centre of the clip. 0 = always centred, 1 = anywhere inside the clip. |
| `framing.zoom_jitter` | Zoom jitter | float | 0 to 50 (step 1) | 15 | % | yes | Each window's zoom varies by up to this many percent either side of the zoom module's baseline (never below cover). |
| `framing.candidates` | Candidates (K) | int | 1 to 256 (step 1) | 48 |  |  | How many candidate windows detail, blend and contrast compare (random modes draw until one is allowed by Memory). |
| `framing.temperature` | Temperature | float | 0 to 2 (step 0.01) | 0.2 |  | yes | Randomness of the pick among candidates. 0 = always the best candidate; higher = more varied; about 2 = nearly uniform. |
| `framing.neighbour_influence` | Neighbour influence | float | 0 to 1 (step 0.01) | 0.8 |  | yes | How much the neighbouring panels' windows steer blend and contrast. 0 = ignore them. |
| `framing.edge_sample` | Edge sample width | float | 0.01 to 0.5 (step 0.01) | 0.1 | of window | yes | Width of the band along a window edge whose colours are compared (fraction of the window size across the edge). |
| `framing.match_on` | Match on | enum | colour / luma / hue | colour |  |  | What blend and contrast compare along facing edges: full colour, brightness only, or hue only (weighted by saturation). |
| `framing.vary_per_appearance` | Vary per appearance | bool | on / off | true |  |  | On: every time a clip appears it gets a different window. Off: a clip always gets the same window. |
| `framing.memory` | Memory (M) | int | 1 to 32 (step 1) | 6 | windows |  | A clip must show M different windows before a window repeats (per-clip history). 1 = no restriction. Best effort when the window range holds fewer than M distinct windows. |
| `framing.drift_speed` | Drift speed | float | 0.1 to 30 (step 0.1) | 2 | cycles/min | yes | Drift mode: one cycle is a pan/zoom out and back; a leg lasts 30 / speed seconds. |

### AUDIO

Every panel plays its own sound, simultaneously.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `audio.speech_policy` | Speech policy | enum | play / mute / exclude | mute |  |  | For clips whose audio screen found speech (audio.speech, or the flags number_sequence, email_like, introduces_self, possible_name, long_speech). play: sound as usual. mute: the picture plays, the sound does not (also in the reveal). exclude: such clips are never shown. Never randomized. |
| `audio.mute_unscreened` | Mute unscreened | bool | on / off | true |  |  | Mute clips whose audio.screened is not true (including clips with no audio record at all). |
| `audio.master` | Master | float | 0 to 1.5 (step 0.01) | 0.8 |  | yes | Master gain. |
| `audio.pan` | Spatial pan | bool | on / off | true |  |  | Pan each panel by its position on screen (along the strip direction). |
| `audio.pan_width` | Pan width | float | 0 to 1 (step 0.01) | 0.8 |  | yes | 1 = outermost panels fully left/right. |
| `audio.normalize` | Loudness normalise | bool | on / off | true |  |  | Gain each clip toward the target using its loudness_db (unknown loudness stays at unity). |
| `audio.norm_target_db` | Normalise target | float | -60 to -6 (step 0.5) | -30 | dB | yes | Target loudness for normalisation. Boost is capped at +20 dB. |
| `audio.size_gain` | Size to gain | float | 0 to 1 (step 0.01) | 0.5 |  | yes | Bigger panels are louder: gain = (panel share / mean share)^amount. |
| `audio.auto_trim` | Auto trim | bool | on / off | true |  |  | Scale the master by 1/sqrt(N) so many panels do not clip. |
| `audio.muted_panels` | Muted panels | multi | subset of 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16 | [] |  |  | Panels (1-based) that are silent. |
| `audio.solo_panels` | Solo panels | multi | subset of 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16 | [] |  |  | If any panel is soloed only soloed panels sound. |
| `audio.fade` | Fade length | float | 0 to 3 (step 0.01) | 0.4 | s | yes | Cross-fade when a panel changes clip (avoids clicks). |
| `audio.limiter` | Limiter | bool | on / off | true |  |  | Compressor/limiter before the output. |
| `audio.limiter_ceiling` | Limiter ceiling | float | -24 to 0 (step 0.5) | -3 | dB | yes | Threshold of the limiter. |

### REVEAL

What tapping a panel shows.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `reveal.action` | Tap action | enum | still / video / both | still |  |  | What tapping a panel shows: the original still, the full-frame video, or the still with the video inset. |
| `reveal.show_date` | Show date | bool | on / off | true |  |  | Show the capture date. |
| `reveal.show_tags` | Show tags | bool | on / off | true |  |  | Show tag chips on the reveal. |
| `reveal.show_window` | Outline window | bool | on / off | false |  |  | Outline, on the full still, the window the panel was showing ("where this panel was looking"). |
| `reveal.pause_others` | Pause others | bool | on / off | false |  |  | Pause the other panels while a reveal is open. |
| `reveal.animation` | Animation | enum | none / zoom / fade | zoom |  |  | zoom: expands from the panel's rectangle. |
| `reveal.anim_ms` | Animation time | float | 0 to 1500 (step 10) | 350 | ms | yes | Duration of the reveal animation. |

<!-- END CONFIG REFERENCE -->
