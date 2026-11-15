# Cadence

A movable Apple Music lyric widget that lives **above your wallpaper and below your app windows**. Python with native AppKit rendering through PyObjC; a small Swift helper provides optional on-device Apple Intelligence.

## Download & install

### [⬇ Download Cadence for Mac — Apple silicon](https://github.com/EdwardWritesCodeIGuess/cadence-desktop/releases/latest/download/Cadence-Apple-Silicon.dmg)

1. Open the downloaded DMG and drag **Cadence** to **Applications**.
2. Open **Cadence**, allow access to **Music**, and play a song.

No Python or developer tools needed. Requires an M1-or-newer Mac and macOS 14+; tested on macOS 27.3. Optional Apple Intelligence needs macOS 26+.

**First launch:** this personal build is not notarized. If blocked, approve Cadence under **System Settings → Privacy & Security → Open Anyway**, as described in [Apple's guide](https://support.apple.com/en-us/102445).

[Full install guide](INSTALL.md) · [ZIP download](https://github.com/EdwardWritesCodeIGuess/cadence-desktop/releases/latest/download/Cadence-Apple-Silicon.zip) · [Latest release](https://github.com/EdwardWritesCodeIGuess/cadence-desktop/releases/latest)

If this repo is private, your friend needs GitHub access to download. Alternatively, send them the DMG directly.

## New in v3.1

- **More pop:** Kinetic Word now springs in. Each word grows past its size and settles, stretches while it moves, leans slightly in alternating directions, and the outgoing word puffs away as it fades. A new **Glow** slider adds soft light around the word being sung, and **Sparks** throws a short burst from each new word. Both scale with **Pop strength** and can be turned off. The other styles get a livelier bounce and a small hop on the active word.
- **Feels alive:** the Aurora backdrop brightens with every sung word. Colours come from the dominant hues of the album artwork (an accent and a second backdrop colour) and glide from one song to the next instead of snapping. Artwork and titles fade in, small equaliser bars move while music plays, and three dots fill up during instrumental breaks.
- **Tighter timing:** Cadence reacts to Music's own play, pause and track-change announcements instead of waiting for the next poll, and applies every update on the next frame. Word-synced lyrics hold a finished line through short breaths instead of flashing a note between lines. When a song only has line timestamps, words are now spaced by syllables, with pauses at punctuation, a held last word, and a breath before the next line. This is still an estimate. Enhanced LRC files with per-word tags are read as real word timestamps.
- **More songs matched:** labels that do not change a recording, such as *Remastered 2011*, *Explicit* or *Deluxe Edition*, are ignored when matching lyrics. Live, remix and edit versions are still kept apart. The word-timing search retries with the lead artist when collaborators are listed differently.
- **Live preview:** with Customize open and nothing playing, the widget loops a few sample words so every control can be judged immediately.
- **Menus:** the menu-bar menu shows checkmarks for Lock position, Show widget and Lyrics only, has **Lyric style** and **Widget layout** submenus, and shows the current timing offset. Right-click the widget for the same menu.
- **Snapping:** a dragged widget snaps to the screen edges and centre lines. Hold Option to place it freely.

## New in v3

- **Kinetic Word:** one large word at a time, with smooth crossfades and a squash/stretch pop inspired by the supplied video. **Stretch to fill** controls how much words expand independently across the widget's width and height. Turn **Neighboring words / lines** on for smaller surrounding words.
- Continuous word highlights and a smoothed playback clock avoid resetting animation at every Music poll. Rendering follows the display at up to 60 fps. Ransom Note measures layouts separately from rasterization and prewarms upcoming cutouts.
- **Widgets:** Wide lyrics, Square lyrics, Compact strip, Album card, and Clock + lyrics. These are movable layouts for the single Cadence desktop widget, not Apple WidgetKit extensions or multiple simultaneous widgets.
- **Out of view:** when macOS reports the widget fully covered, it is hidden, or the display sleeps, Cadence pauses the display link and control timer and blocks its Music polling thread. It starts no new lyric/art requests while hidden. An existing network request can finish and cache its result; an active AI helper is cancelled. The app remains resident so it can resume on visibility changes.
- **Better lyric sources:** read-only lookup of Apple Music's local syllable-lyrics cache, including exact word timestamps when present. Third-party providers remain fallbacks, and less precise late results cannot replace exact timing.
- **Apple Intelligence:** an optional Timing-tab action cleans promotional decorations from song metadata to retry the catalogue lookup. Suggestions that change the artist, song, or version are rejected. It does not invent lyric text or word timestamps, and is not a Siri transcription integration.
- **Lock screen:** a separate click-through panel can display lyrics near the bottom of the lock screen. The desktop window stays below app windows. Disable it under Layout if desired. This uses private SkyLight APIs adapted from Maestro, so macOS updates may affect compatibility.

## Styles and customization

| Effect | Motion |
| --- | --- |
| Kinetic Word | One large word, elastic fit, pop and crossfade |
| Ransom Note | Cached, locally drawn letter cutouts on textured paper |
| Pop | Smooth word highlights and capsules |
| Spotlight | One large word with nearby words above and below |
| Ribbon | A horizontal strip that follows each word |
| Scroll | A vertical stack of lyric lines |
| Typewriter | Reveals the phrase word by word |
| Neon | Glowing active words |
| Wave | Gently undulating words |

All effects work with Aurora, Glass, or transparent Typography backdrops. Controls include font, size, widget dimensions, colors, opacity, pop strength, glow, sparks, speed, stretch, paper variation, line spacing, neighbors, alignment and timing offset. **Layout → Lyrics only** removes the backdrop and all other UI. Full widget mode has separate switches for title, art, progress, elapsed time and source. Settings and position persist.

Positive timing offsets show lyrics earlier. The default is +0.22 seconds; Earlier/Later actions nudge by 100 ms. Existing custom offsets are preserved. An offset can correct constant latency, but cannot make estimated word timing exact.

## Use

Launch **Cadence.app**, allow it to control **Music**, then play a song in the native Apple Music app. The waveform menu-bar icon opens Customize, lyric styles, widget layouts, Refresh lyrics, timing nudges and placement controls. Show the desktop to see the widget; drag it to move it and right-click it for the same menu. Lock its position for click-through behavior; the menu-bar icon still works while it is locked.

For the video-inspired look, select **Effects → Kinetic Word**, turn neighboring words off, and adjust **Stretch to fill**. Choose **Layout → Lyrics only** for text directly over the wallpaper. Widget layouts are in the **Widgets** tab.

Apple Music's lyrics cache must already contain the song. Opening that song's lyrics in Music may populate it; then use **Refresh lyrics** in Cadence. Otherwise Cadence uses LRCLIB and NetEase, identifying real versus estimated timestamps in Timing. Missing or instrumental lyrics get an explicit state, and stale results from previous songs are discarded.

If Automation was denied: System Settings → Privacy & Security → Automation → Cadence → Music. The preferences window shows connection status. Cadence never launches Music merely to poll it.

## Build from source

Developed on Apple silicon, Python 3.14, macOS 27.3, and the macOS 27.2 SDK. The main app targets macOS 14+, but older releases have not been verified. Building the optional Apple Intelligence helper requires Xcode Command Line Tools with FoundationModels/Swift support; the bundled helper targets Apple silicon/macOS 26+. It requires Apple Intelligence enabled and its on-device model available.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python setup.py py2app
codesign --force --deep --sign - dist/Cadence.app
open dist/Cadence.app
```

Copy `dist/Cadence.app` to Applications to install. Python and dependencies are bundled; the app does not need the source checkout or venv. The local build is ad-hoc signed, not notarized. For development, run `.venv/bin/python main.py` after building the helper; Automation may then belong to Python or the terminal.

## Performance and privacy

AppKit draws text and gradients without a web view. Visible playback is sampled on a background thread about every 350 ms, and at once when Music announces a play, pause or track change. Samples are applied on the next frame and interpolated using a monotonic clock that absorbs small sample corrections. Real seeks, pauses, and track changes apply immediately. A paused widget redraws only briefly after something changes. Network requests use a bounded worker pool. Positive third-party lyric results are cached for seven days. No background service or login item is installed.

The hidden widget's timers and polling stop, but its Python process retains memory. Visible animation still uses CPU/GPU; Python has a larger baseline than Maestro's Swift app. Disable motion or select Typography to reduce drawing work further.

The Music cache is read locally, without modifying Music's database. Fallback lookups send song metadata to LRCLIB/NetEase; artwork uses Apple's iTunes Search API. The optional Apple Intelligence helper processes metadata on-device only when requested and exits afterward. No Apple account credentials, API keys, or telemetry are collected. Settings and rotating logs are in `~/Library/Application Support/Cadence`; the lyric cache is in `~/Library/Caches/Cadence`. Those files and the reference video are not included in the repo.

## Validation

`python -m unittest discover -s tests -v` covers playback timing, word-animation and spring continuity, jitter correction, seek/pause/song changes, stale results, LRC/enhanced LRC/YRC/TTML parsing, syllable-based word estimates, held lines and instrumental gaps, version-label matching, album palette selection, widget snapping, provider priority, settings migration and invalid AI query rejection.

On macOS, `python tests/ui_smoke.py /absolute/scratch/folder` renders original synthetic lyrics across all nine styles and five presets. It checks the live preview, transparency, hidden controls, offset nudges, sizing, position, snapping, menu state, desktop window level, click-through, actual window occlusion, hidden timer/poll suspension, and lock-space creation/teardown. It does not control Music, change saved settings, or actually lock the computer. A real lock/unlock remains a manual visual check.

## Credits and license

MIT. The Apple Music bridge, song-derived word timing, and lock-screen space approach were adapted from [Maestro](https://github.com/Maestro2903/maestro-lyrics) by Shreeshanth R; see [MAESTRO-LICENSE](MAESTRO-LICENSE) and [NOTICE.md](NOTICE.md).

The Music cache lookup and TTML approach were adapted from [Apple Music Lyrics](https://github.com/Takpap/apple-music-lyrics); its MIT notice is in [APPLE-MUSIC-LYRICS-LICENSE](APPLE-MUSIC-LYRICS-LICENSE).

[Verso](https://github.com/AkkiCode06/verso) inspired the typography and album-colored atmosphere. No Verso code or assets are included. Lyrics and artwork retain their respective owners' rights.
