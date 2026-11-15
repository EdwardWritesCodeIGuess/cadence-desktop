import unittest
from cadence.motion import word_motion, spring, kinetic_pose, kinetic_peak, settle, approach, PlaybackClock
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

    def test_small_poll_jitter_is_only_half_followed(self):
        clock = PlaybackClock()
        clock.update(Track(title='Song', position=10, playing=True, sampled_at=0))
        clock.update(Track(title='Song', position=10.37, playing=True, sampled_at=.35))
        self.assertAlmostEqual(clock.position_at(5), 15.01, delta=.001)
        clock.update(Track(title='Song', position=15.25, playing=True, sampled_at=5))
        self.assertAlmostEqual(clock.position_at(9), 19.25, delta=.001)

    def test_spring_overshoots_once_then_rests(self):
        self.assertEqual(spring(0), (0., 0.))
        values = [spring(i/240)[0] for i in range(240)]
        self.assertGreater(max(values), 1.15)
        self.assertLess(max(values), 1.3)
        self.assertAlmostEqual(values[-1], 1, delta=.001)
        self.assertAlmostEqual(spring(1)[1], 0, delta=.001)

    def test_kinetic_word_enters_smoothly_and_settles(self):
        for amount in (0., .35, .8):
            frames = [kinetic_pose(i/600, .4, 1., amount) for i in range(600)]
            for before, after in zip(frames, frames[1:]):
                self.assertLess(max(abs(a-b) for a, b in zip(before, after)), .06)
            self.assertEqual(frames[0][0], 0)
            self.assertLessEqual(max(frame[1] for frame in frames), kinetic_peak(amount)+1e-9)
            for value, rest in zip(frames[-1], (1, 1, 0, 0, 0)):
                self.assertAlmostEqual(value, rest, delta=.002)
        self.assertEqual(kinetic_pose(.01, .4, motion=False), (1., 1., 0., 0., 0.))
        self.assertEqual(kinetic_peak(0), 1)

    def test_sung_words_relax_and_colours_ease(self):
        self.assertEqual(settle(1, 2), 1)
        self.assertAlmostEqual(settle(3, 2), .62)
        colour = (0., 0., 0.)
        for _ in range(120):
            colour = approach(colour, (1., .5, 0.), 1/60)
        for value, goal in zip(colour, (1., .5, 0.)):
            self.assertAlmostEqual(value, goal, delta=.001)
        self.assertEqual(approach((0., 0.), (1., 1.), 0), (0., 0.))
