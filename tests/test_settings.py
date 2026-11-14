import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cadence.settings import Settings

class SettingsMigrationTests(unittest.TestCase):
    def test_upgrade_adds_lead_without_resetting_user_choices(self):
        with tempfile.TemporaryDirectory() as folder, patch('cadence.settings.SUPPORT', Path(folder)):
            path = Path(folder)/'settings.json'
            for old, expected in [(0, .22), (.6, .6), (-.2, -.2)]:
                path.write_text(json.dumps({'offset': old, 'x': 51, 'y': 70, 'font_size': 42}))
                settings = Settings()
                self.assertEqual(settings['offset'], expected)
                self.assertEqual(settings['x'], 51)
                self.assertEqual(settings['font_size'], 42)
                self.assertEqual(settings['lyric_style'], 'Kinetic Word')
                settings['show_progress'] = False
                settings['layout'] = 'Lyrics only'
                settings.save()
                loaded = Settings()
                self.assertFalse(loaded['show_progress'])
                self.assertEqual(loaded['layout'], 'Lyrics only')
                self.assertEqual(loaded['offset'], expected)

    def test_explicit_zero_survives_v2_relaunch(self):
        with tempfile.TemporaryDirectory() as folder, patch('cadence.settings.SUPPORT', Path(folder)):
            settings = Settings()
            settings['offset'] = 0.
            settings.save()
            self.assertEqual(Settings()['offset'], 0.)
