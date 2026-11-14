#!/usr/bin/env python3
"""Package an existing standalone Cadence build; no runtime/install scripts needed."""
import argparse
import hashlib
import os
import plistlib
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, default=ROOT/'dist/Cadence.app')
    parser.add_argument('--output', type=Path, default=ROOT/'dist/release')
    args = parser.parse_args()
    source, output = args.app.resolve(), args.output.resolve()
    with (source/'Contents/Info.plist').open('rb') as stream:
        info = plistlib.load(stream)
    if info.get('CFBundleIdentifier') != 'com.edwardlink.cadence':
        raise SystemExit('Expected a standalone Cadence.app build')
    version = info['CFBundleShortVersionString']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise SystemExit('Expected a numeric major.minor.patch version')
    # Refuse an alias-mode build that depends on the developer machine.
    for path in source.rglob('*'):
        if path.is_symlink() and not path.resolve().is_relative_to(source):
            raise SystemExit(f'External symlink in app: {path.relative_to(source)}')
    output.mkdir(parents=True, exist_ok=True)
    artifacts = [output/'Cadence-Apple-Silicon.dmg', output/'Cadence-Apple-Silicon.zip']
    if any(path.exists() for path in artifacts):
        raise SystemExit('Release assets already exist; use a fresh --output directory')
    with tempfile.TemporaryDirectory(prefix='cadence-release-') as temporary:
        staging = Path(temporary)/'volume'
        staging.mkdir()
        app = staging/'Cadence.app'
        run('ditto', '--norsrc', source, app)
        # Remove build-machine Finder metadata before signing this fresh copy.
        run('xattr', '-cr', app)
        run('codesign', '--force', '--deep', '--sign', '-', app)
        run('codesign', '--verify', '--deep', '--strict', app)
        os.symlink('/Applications', staging/'Applications')
        (staging/'How to Install.txt').write_text(
            f'CADENCE {version}\n\n'
            '1. Drag Cadence.app onto Applications.\n'
            '2. Open Cadence from Applications and allow access to Music.\n\n'
            'Play a song in the Mac Music app, then show your desktop.\n'
            'The waveform icon in the menu bar opens customization.\n\n'
            'FIRST OPEN\n'
            'This personal build is not notarized by Apple. If macOS blocks it,\n'
            'try opening it once, then choose System Settings > Privacy & Security\n'
            '> Open Anyway for Cadence, if you trust this download.\n'
            'Apple instructions: https://support.apple.com/en-us/102445\n\n'
            'REQUIREMENTS\n'
            'Apple silicon Mac (M1 or newer), macOS 14 or later.\n'
            'Tested on macOS 27.3; older versions have not been verified.\n'
            'Optional Apple Intelligence matching requires macOS 26+,\n'
            'Apple Intelligence enabled, and the on-device model downloaded.\n'
            'Python, Terminal, developer tools and API keys are not needed.\n\n'
            'UPDATES / REMOVE\n'
            'Quit Cadence before replacing an older copy.\n'
            'To uninstall, quit Cadence and move it from Applications to Trash.\n\n'
            'PROJECT\nhttps://github.com/EdwardWritesCodeIGuess/cadence-desktop\n',
            encoding='utf-8')
        run('hdiutil', 'create', '-volname', f'Cadence {version}', '-srcfolder', staging,
            '-fs', 'HFS+', '-format', 'UDZO', '-imagekey', 'zlib-level=9',
            artifacts[0])
        run('hdiutil', 'verify', artifacts[0])
        run('ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, artifacts[1])
    checksums = output/'SHA256SUMS.txt'
    entries = []
    for path in artifacts:
        with path.open('rb') as stream:
            entries.append(f'{hashlib.file_digest(stream, "sha256").hexdigest()}  {path.name}\n')
    checksums.write_text(''.join(entries), encoding='utf-8')
    print(f'Cadence {version} packaged in {output}')
    for path in [*artifacts, checksums]:
        print(f'  {path.name}: {path.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
