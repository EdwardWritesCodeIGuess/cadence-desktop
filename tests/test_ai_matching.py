import unittest
from cadence.ai_matching import validated_query
from cadence.core import Track

class AIMatchingTests(unittest.TestCase):
    def test_removes_promotional_decoration_only(self):
        original=Track(title='Example (Official Audio)', artist='Artist', duration=200)
        match=validated_query(original, {'title':'Example','artist':'Artist'})
        self.assertEqual(match.title,'Example')
        self.assertEqual(match.duration,200)

    def test_refuses_different_artist_song_or_version(self):
        original=Track(title='Example (Live)',artist='Artist')
        for response in ({'title':'Example','artist':'Artist'}, {'title':'Other','artist':'Artist'}, {'title':'Example (Live)','artist':'Cover Artist'}):
            with self.assertRaises(RuntimeError): validated_query(original,response)
