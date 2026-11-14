import unittest
from cadence.apple_lyrics import parse_ttml

class AppleLyricsTests(unittest.TestCase):
    def test_syllables_join_into_words_and_keep_exact_times(self):
        raw = '''<tt xmlns="http://www.w3.org/ns/ttml"><body><p begin="00:01.000" end="00:03.000"><span begin="1s" end="1.3s">Hel</span><span begin="1.3s" end="1.7s">lo</span> <span begin="2s" end="3s">world</span></p></body></tt>'''
        lines, exact = parse_ttml(raw)
        self.assertTrue(exact)
        self.assertEqual([w.text for w in lines[0].words], ['Hello ', 'world'])
        self.assertEqual([(w.start, w.end) for w in lines[0].words], [(1, 1.7), (2, 3)])

    def test_untrusted_entities_not_loaded(self):
        self.assertEqual(parse_ttml('<!DOCTYPE tt [<!ENTITY x SYSTEM "file:///private/foo">]><tt/>'), ([], False))
