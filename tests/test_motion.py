import unittest
from cadence.motion import word_motion, PlaybackClock
from cadence.core import Track

class MotionTests(unittest.TestCase):
    def test_word_start_and_end_are_continuous(self):
        for duration in (.04, .1, .3, 2):
            for edge in (1., 1+duration, 1+duration+.16):
                before = word_motion(edge-1e-6, 1, 1+duration)
                after = word_motion(edge+1e-6, 1, 1+duration)
                self.assertLess(max(abs(a-b) for a, b in zip(before, after)), .001)
        self.assertEqual(word_motion(.9, 1, 2)[1], 1)
        self.assertEqual(word_motion(2.3, 1, 2)[1], 1)

    def test_poll_correction_never_resets_or_reverses_clock(self):
        clock = PlaybackClock()
        clock.update(Track(title='Song', position=10, playing=True, sampled_at=0))
        before = clock.position_at(.35)
        clock.update(Track(title='Song', position=10.1, playing=True, sampled_at=.35))
        self.assertAlmostEqual(clock.position_at(.35), before)
        values = [clock.position_at(.35+i/120) for i in range(240)]
        self.assertEqual(values, sorted(values))
        self.assertAlmostEqual(clock.position_at(3), 12.75, delta=.01)

    def test_seek_pause_and_new_track_snap(self):
        clock = PlaybackClock()
        clock.update(Track(title='One', position=10, playing=True, sampled_at=0))
        clock.update(Track(title='One', position=2, playing=True, sampled_at=.35))
        self.assertEqual(clock.position_at(.35), 2)
        clock.update(Track(title='One', position=3, playing=False, sampled_at=1.35))
        self.assertEqual(clock.position_at(10), 3)
        clock.update(Track(title='Two', position=0, playing=True, sampled_at=10))
        self.assertEqual(clock.position_at(10), 0)
