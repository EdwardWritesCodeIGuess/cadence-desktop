# Cadence

A movable Apple Music lyric widget that lives **above your wallpaper and below your app windows**. Written in Python with native AppKit rendering through PyObjC.

## What it does

- Reads the current song, artist, album, playback state and position directly from Apple Music via Apple Events.
- Follows song changes, pauses and seeks. Old lyrics disappear on a track change; generation checks discard late responses for previous tracks.
- Displays synced lyrics with word highlighting, neighboring lines, album artwork and progress.
- Offers Aurora, Glass and transparent Typography looks; adjustable typeface, lyric size, width, height, backdrop opacity, accent color and timing offset.
- Samples colors from album artwork. Optional gently moving aurora background.
- Drag to move, right-click to customize, and lock the position for click-through behavior. Placement and appearance survive relaunches.
- Uses one desktop-level window across Spaces. Does not cover normal app windows or the lock screen.

## Kinetic lyrics (v2)

Eight independent lyric effects work with any backdrop:

| Effect | Motion |
| --- | --- |
| Ransom Note | Mixed letter cutouts on textured paper, with active-word pops |
| Pop | Springy word highlights and capsules |
| Spotlight | One large active word with nearby words above and below |
| Ribbon | A horizontal strip that follows each word |
| Scroll | A vertical stack of lyric lines with a highlighted active phrase |
| Typewriter | Reveals the phrase word by word |
| Neon | Glowing active words |
| Wave | Gently undulating words with active-word emphasis |

Ransom Note is drawn locally and cached; it does not need external letter images.
Effects controls include pop strength, animation speed, cutout variation, line spacing,
neighbor visibility, typeface, alignment, and lyric size. **Layout → Lyrics only**
removes the backdrop and all song/time/progress UI without losing individual choices.
Full widget mode has separate switches for title, art, progress, elapsed time and the
source label. Colors controls adjust text/accent colors and independent opacities.

**Timing:** the default is +0.22 seconds (positive shows lyrics earlier). Existing
custom nonzero offsets are retained. Earlier/Later buttons and menu actions nudge
by 100 ms; Reset restores +0.22 seconds. The Timing tab identifies whether timestamps
are real or estimated. A constant offset can address consistent latency, but cannot
make estimated word timings exact. Both lyric providers still depend on coverage.

## Use

Launch **Cadence.app**, allow it to control **Music** when macOS asks, then play a song in the native Apple Music app. The waveform menu-bar icon opens Customize, Refresh lyrics and position controls.

Show your desktop to see the widget. Drag anywhere on the widget to move it. If locked, unlock it from the menu bar or Customize window. Choose **Typography** for lyrics directly over your wallpaper, or lower **Backdrop opacity**. Close Customize when finished; Cadence stays in the menu bar.

If Automation was denied: System Settings → Privacy & Security → Automation → Cadence → Music. The settings window shows the current connection status. Open Apple Music from the menu if it isn't running.

## Build from source

Requires macOS 14+ and Python 3.14. Developed and tested on Apple silicon with macOS 27.3; older supported versions have not been verified.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python setup.py py2app
codesign --force --deep --sign - dist/Cadence.app
open dist/Cadence.app
```

The built app bundles Python and dependencies; it does not need the source directory or virtual environment to run. To install, copy `dist/Cadence.app` to Applications. This local build is ad-hoc signed, not notarized.

For a developer preview: `.venv/bin/python main.py` (Automation may then belong to Python or your terminal).

## Performance and behavior

Native AppKit draws text and gradients without a web view. Playback is sampled on a background thread about every 350 ms and interpolated with a monotonic clock. Network requests run in a bounded worker pool, never on the UI thread. Positive lyric results are cached for seven days. The renderer is capped at 30 fps while playing; idle/paused states redraw on updates, and drawing is skipped when macOS reports the window occluded or the screen is locked. Disable animation or use Typography to reduce drawing work.

Python has a higher baseline memory cost than Maestro's Swift app. There is no claim of identical resource usage. Cadence does not install a background service or start itself at login.

## Lyrics and privacy

Apple Music supplies playback metadata, **not its internal lyrics**. Cadence looks up LRCLIB and NetEase in parallel and upgrades to real word timestamps when available; late line-only results cannot downgrade them. Lyrics depend on catalogue availability. LRC supplies line timestamps; word timing is estimated using a song-derived pace adapted from Maestro. NetEase YRC, when used, supplies actual word timings. A timing offset slider helps with different masters. Missing/instrumental lyrics get an explicit status rather than a previous song's words.

Song metadata is sent to LRCLIB/NetEase for lyrics and Apple's iTunes Search API for artwork. No Apple account credentials, API keys or telemetry. Settings and a rotating diagnostic log live in `~/Library/Application Support/Cadence`; lyrics cache lives in `~/Library/Caches/Cadence`. The repo does not contain those files.

## Tests

`python -m unittest discover -s tests -v` checks pause/seek extrapolation, rapid song changes and stale results, repeated LRC timestamps, offsets, instrumental gaps, YRC timing and wrong-artist/version rejection.

On macOS, `python tests/ui_smoke.py /absolute/scratch/folder` renders synthetic preview lyrics and checks all eight renderers, several animation frames, lyrics-only transparency, no-progress rendering, timing nudges, native window level, resizing, position storage, click-through and lock/unlock visibility. It does not control Apple Music or change saved settings. Preview lyrics are original sample text, not a live song.

## Credits and license

MIT. The Apple Music bridge and interpolation approach were adapted from [Maestro](https://github.com/Maestro2903/maestro-lyrics) by Shreeshanth R; see [MAESTRO-LICENSE](MAESTRO-LICENSE) and [NOTICE.md](NOTICE.md).

[Verso](https://github.com/AkkiCode06/verso) inspired the desktop typography and album-colored atmosphere. No Verso code or assets are included. Lyrics and artwork retain their respective owners' rights.
