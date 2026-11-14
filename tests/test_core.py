import unittest
from cadence.core import Track, Playback, active_line, parse_lrc, parse_yrc, match_candidate


class TimingTests(unittest.TestCase):
    def test_play_pause_seek(self):
        track = Track(title='One', duration=100, position=20, playing=True, sampled_at=10)
        self.assertEqual(track.position_at(13), 23)
        paused = Track(title='One', duration=100, position=23, playing=False, sampled_at=13)
        self.assertEqual(paused.position_at(30), 23)
        seek = Track(title='One', duration=100, position=80, playing=True, sampled_at=30)
        self.assertEqual(seek.position_at(31), 81)
        self.assertEqual(seek.position_at(90), 100)

    def test_skip_clears_and_rejects_stale_lyrics(self):
        state = Playback()
        state.update(Track(title='One', identifier='1'))
        first = state.generation
        state.accept(first, parse_lrc('[00:01]First song'), 'test')
        state.update(Track(title='Two', identifier='2'))
        self.assertEqual(state.lines, [])
        self.assertFalse(state.accept(first, parse_lrc('[00:01]Wrong song'), 'late'))
        self.assertTrue(state.accept(state.generation, parse_lrc('[00:01]Second song'), 'new'))
        self.assertEqual(state.lines[0].text, 'Second song')
        state.update(Track())
        self.assertEqual(state.lines, [])

    def test_real_word_timestamps_win_in_either_response_order(self):
        for first in ('line', 'word'):
            state = Playback()
            state.update(Track(title='Example'))
            lrc = parse_lrc('[00:01]One two')
            yrc = parse_yrc('[1000,2000](1000,600,0)One (1600,1400,0)two')
            if first == 'line':
                state.accept(state.generation, lrc, 'Estimated')
                self.assertTrue(state.accept(state.generation, yrc, 'Word-synced lyrics'))
            else:
                state.accept(state.generation, yrc, 'Word-synced lyrics')
                self.assertFalse(state.accept(state.generation, lrc, 'Estimated'))
            self.assertFalse(state.accept(state.generation, [], 'No result'))
            self.assertEqual(state.lines[0].words[1].start, 1.6)
            self.assertEqual(state.source, 'Word-synced lyrics')
        state = Playback()
        state.update(Track(title='Example'))
        state.accept(state.generation, lrc, 'Synced lines')
        self.assertFalse(state.accept(state.generation, lrc, 'NetEase lines · estimated word timing'))

    def test_lrc_offsets_repeated_timestamps_and_gaps(self):
        lines = parse_lrc('[offset:-500]\n[00:02.00][00:12.00]Hello world\n[00:05.00]\n[00:16.00]End', 20)
        self.assertEqual([ln.start for ln in lines], [1.5, 4.5, 11.5, 15.5])
        self.assertEqual(active_line(lines, 1), -1)
        self.assertEqual(active_line(lines, 12), 2)
        self.assertEqual(lines[1].text, '')
        self.assertEqual(''.join(word.text for word in lines[0].words), 'Hello world')
        self.assertLessEqual(lines[0].words[-1].end, lines[0].end)

    def test_yrc_keeps_real_word_timing(self):
        lines = parse_yrc('[1000,2400](1000,800,0)Hello (1800,1600,0)world')
        self.assertEqual(lines[0].words[1].start, 1.8)
        self.assertEqual(lines[0].end, 3.4)
        self.assertEqual(active_line(lines, 4), -1)

    def test_same_title_wrong_artist_or_version_rejected(self):
        track = Track(title='Home', artist='Original Artist', duration=200)
        self.assertFalse(match_candidate(track, 'Home', 'Cover Band', 200))
        self.assertFalse(match_candidate(track, 'Home', 'Original Artist', 250))
        self.assertTrue(match_candidate(track, 'Home', 'Original Artist', 202))

if __name__ == '__main__':
    unittest.main()
