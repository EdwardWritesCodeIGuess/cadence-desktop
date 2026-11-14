from setuptools import setup

setup(
    name='Cadence', version='2.0.0', app=['main.py'],
    data_files=['LICENSE', 'NOTICE.md', 'MAESTRO-LICENSE'],
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
