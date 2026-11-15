import unittest
from cadence.core import (Track, Playback, active_line, display_line, demo_lines, parse_lrc, parse_yrc,
                          match_candidate, clean_title, syllables, DEMO_LENGTH)


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

    def test_packaging_labels_ignored_but_other_recordings_still_rejected(self):
        track = Track(title='Home (Remastered 2011)', artist='Original Artist', duration=200)
        self.assertTrue(match_candidate(track, 'Home', 'Original Artist', 201))
        self.assertTrue(match_candidate(track, 'Home [Explicit]', 'Original Artist', 201))
        self.assertTrue(match_candidate(track, 'Home - 2011 Remaster', 'Original Artist', 201))
        for other in ('Home (Live)', 'Home (Acoustic Version)', 'Home - Radio Edit', 'Home (Remix)'):
            self.assertFalse(match_candidate(track, other, 'Original Artist', 201))
        self.assertEqual(clean_title('Clean'), 'Clean')
        self.assertEqual(clean_title('Stereo Hearts (feat. Someone)'), 'Stereo Hearts')

    def test_estimated_words_follow_syllables_and_leave_a_breath(self):
        self.assertGreater(syllables('beautiful'), syllables('strength'))
        self.assertEqual(syllables('time'), 1.5)
        line = parse_lrc('[00:10.00]Strength is beautiful, always\n[00:14.00]Next', 20)[0]
        lengths = {word.text.strip(): word.end-word.start for word in line.words}
        self.assertGreater(lengths['beautiful,'], lengths['Strength'])
        self.assertEqual(''.join(word.text for word in line.words), 'Strength is beautiful, always')
        self.assertAlmostEqual(line.words[0].start, 10)
        # The last word is held, yet singing stops before the next line begins.
        self.assertGreater(lengths['always'], lengths['Strength'])
        self.assertLessEqual(line.words[-1].end, 13.75+1e-9)
        for before, after in zip(line.words, line.words[1:]):
            self.assertAlmostEqual(before.end, after.start)

    def test_enhanced_lrc_word_tags_are_real_timestamps(self):
        lines = parse_lrc('[offset:-500]\n[00:10.00]<00:10.00>Hello <00:10.80>bright <00:11.50>world<00:12.40>\n[00:14.00]Plain line', 20)
        self.assertEqual(lines[0].text, 'Hello bright world')
        self.assertEqual([word.text for word in lines[0].words], ['Hello ', 'bright ', 'world'])
        self.assertEqual([(word.start, word.end) for word in lines[0].words], [(9.5, 10.3), (10.3, 11.0), (11.0, 11.9)])
        self.assertEqual(lines[1].text, 'Plain line')
        self.assertEqual(len(lines[1].words), 2)

    def test_short_gaps_hold_the_line_and_long_gaps_report_the_pause(self):
        lines = parse_yrc('[1000,1000](1000,1000,0)One\n[2600,1000](2600,1000,0)Two\n[9000,1000](9000,1000,0)Three')
        self.assertEqual(display_line(lines, .5), (-1, (0., 1.)))
        self.assertEqual(display_line(lines, 1.5), (0, None))
        self.assertEqual(active_line(lines, 2.3), -1)
        self.assertEqual(display_line(lines, 2.3), (0, None))      # a breath: keep showing "One"
        self.assertEqual(display_line(lines, 2.7), (1, None))
        self.assertEqual(display_line(lines, 5), (-1, (3.6, 9.)))  # an instrumental break
        self.assertEqual(display_line(lines, 11), (-1, (10., None)))
        marked = parse_lrc('[00:01]One\n[00:03]\n[00:04]Two\n[00:06]\n[00:20]Three', 30)
        self.assertEqual(display_line(marked, 3.5)[0], 0)
        self.assertEqual(display_line(marked, 10), (-1, (6., 20.)))

    def test_line_starts_follow_every_change_of_lines(self):
        state = Playback()
        state.update(Track(title='One'))
        state.accept(state.generation, parse_lrc('[00:01]First\n[00:05]Second'), 'test')
        self.assertEqual(state.starts, [1, 5])
        state.lines = []
        self.assertEqual(state.starts, [])

    def test_preview_words_fit_their_loop(self):
        lines = demo_lines()
        self.assertTrue(all(line.words for line in lines if line.text))
        self.assertLessEqual(max(line.start for line in lines), DEMO_LENGTH)

if __name__ == '__main__':
    unittest.main()
