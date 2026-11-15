import colorsys
import unittest
from cadence.palette import album_palette, from_hex, to_hex, DEFAULT_ACCENT, DEFAULT_SECONDARY


def hue(value):
    return colorsys.rgb_to_hsv(*from_hex(value))[0]


def luminance(value):
    red, green, blue = from_hex(value)
    return .2126*red+.7152*green+.0722*blue


class PaletteTests(unittest.TestCase):
    def test_dominant_vivid_hue_beats_one_bright_pixel(self):
        samples = [(.85, .15, .1)]*60+[(.2, .2, .22)]*35+[(.1, .9, .2)]*2
        accent, secondary = album_palette(samples)
        self.assertLess(min(hue(accent), 1-hue(accent)), .05)
        self.assertNotEqual(accent, secondary)

    def test_greyscale_or_missing_artwork_keeps_defaults(self):
        self.assertEqual(album_palette([(.5, .5, .5)]*50), (DEFAULT_ACCENT, DEFAULT_SECONDARY))
        self.assertEqual(album_palette([]), (DEFAULT_ACCENT, DEFAULT_SECONDARY))

    def test_dark_hues_are_lifted_until_readable(self):
        for sample in ((.02, .02, .6), (.3, 0., .4), (.5, .05, .05)):
            accent, _ = album_palette([sample]*40)
            self.assertGreaterEqual(luminance(accent), .49)

    def test_second_colour_comes_from_the_artwork_when_it_has_one(self):
        accent, secondary = album_palette([(.9, .2, .1)]*50+[(.1, .3, .9)]*30)
        self.assertAlmostEqual(hue(secondary), 2/3, delta=.06)

    def test_hex_round_trip_and_bad_input(self):
        self.assertEqual(to_hex(from_hex('#12AB9F')), '#12AB9F')
        self.assertEqual(from_hex('nonsense'), from_hex(DEFAULT_ACCENT))
