from setuptools import setup
from pathlib import Path
import subprocess

helper = Path('native/build/CadenceAI')
helper.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(['xcrun', 'swiftc', '-parse-as-library', '-O', '-target',
                'arm64-apple-macos26.0', 'native/LyricAssistant.swift', '-o', str(helper)], check=True)

setup(
    name='Cadence', version='3.1.0', app=['main.py'],
    data_files=['LICENSE', 'NOTICE.md', 'MAESTRO-LICENSE', 'APPLE-MUSIC-LYRICS-LICENSE', ('', [str(helper)])],
    options={'py2app': {
        'argv_emulation': False,
        'packages': ['cadence', 'certifi'],
        'plist': {
            'CFBundleIdentifier': 'com.edwardlink.cadence',
            'CFBundleDisplayName': 'Cadence',
            'CFBundleName': 'Cadence',
            'LSUIElement': True,
            'LSMinimumSystemVersion': '14.0',
            'NSHighResolutionCapable': True,
            'NSAppleEventsUsageDescription': 'Cadence reads the song and playback position from Apple Music to display synced lyrics on your desktop.',
        },
    }},
)
