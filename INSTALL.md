# Install Cadence

**[Download Cadence for Apple silicon Macs](https://github.com/EdwardWritesCodeIGuess/cadence-desktop/releases/latest/download/Cadence-Apple-Silicon.dmg)**

1. Open the downloaded `.dmg`, then drag **Cadence** onto **Applications**.
2. Open **Cadence** from Applications and allow it to control **Music**.

Play a song in the Mac Music app and show your desktop. Use the waveform icon in the menu bar to customize Cadence. No Python, Terminal, developer tools, subscription to Cadence, or API keys are needed.

## First-launch approval

This personal build is ad-hoc signed and **not notarized by Apple**. The first launch may require an extra approval: after trying to open it, go to **System Settings → Privacy & Security → Open Anyway** for Cadence, if you trust this download. See [Apple's instructions](https://support.apple.com/en-us/102445). This download cannot promise a completely prompt-free two-click first launch.

## Compatibility

- **Apple silicon Mac:** M1 or newer; macOS 14+. Tested on macOS 27.3; older versions have not been verified.
- The optional Apple Intelligence action needs macOS 26+, Apple Intelligence enabled, and the on-device model downloaded. Ordinary lyric display does not require Apple Intelligence.
- Uses playback in the native Mac **Music** app. This download is not for Windows, iPhone, or Android. Intel Macs have not been validated.
- Lyrics depend on song coverage; lock-screen rendering uses private macOS APIs and can be affected by OS updates.

## Downloads and sharing

- [Recommended DMG](https://github.com/EdwardWritesCodeIGuess/cadence-desktop/releases/latest/download/Cadence-Apple-Silicon.dmg): app, Applications shortcut, and install instructions.
- [ZIP alternative](https://github.com/EdwardWritesCodeIGuess/cadence-desktop/releases/latest/download/Cadence-Apple-Silicon.zip): unzip, then move Cadence.app to Applications.
- [Latest release](https://github.com/EdwardWritesCodeIGuess/cadence-desktop/releases/latest): version details and SHA-256 checksums.

Download one of these app assets, not GitHub's automatic “Source code” archives. While this repository is private, your friend must have repository access and be signed in to download. You can also send the downloaded DMG directly. [GitHub explains release access here](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

## Update or remove

Quit Cadence from its menu-bar icon before replacing it with a new version. Settings and placement are kept separately and survive updates. To uninstall, quit Cadence and move the app from Applications to Trash.

## Maintainer: package a release

After building with `python setup.py py2app`, run `python scripts/package_release.py`. It packages a clean copy of the standalone app as a verified DMG and ZIP, with checksums, under `dist/release/`. It does not modify the installed app or include user settings, cached lyrics, or logs. Reuse the asset filenames above so the README's latest-download links continue working. Notarization requires a Developer ID certificate and a separate Apple notarization step; this packaging command does not notarize.
