"""Continuous motion envelopes and a playback clock that absorbs polling jitter."""
import math


def smoothstep(value):
    t = max(0., min(1., value))
    return t*t*(3-2*t)


def word_motion(position, start, end, speed=1., amount=.35, motion=True):
    """No discontinuity at either edge of a word, including very short words."""
    duration = max(.02, end-start)
    attack = max(.015, min(.10/speed, duration*.3))
    release = .16/speed
    entered = smoothstep((position-start)/attack)
    highlight = entered*(1-smoothstep((position-end)/release))
    age = max(0., position-start)
    bump = math.exp(-age*7*speed)
    scale = 1 + (amount*highlight*(.14+.66*bump) if motion else 0)
    alpha = .45+.4*entered+.15*highlight
    return highlight, scale, alpha, entered


class PlaybackClock:
    """Keep the clock continuous across small samples, but snap on seek/pause/skip.

    Correction is spread over time, never by resetting a running visual anchor.
    The time constant also guarantees forward motion for accepted corrections.
    """
    def __init__(self):
        self.track = None
        self.base = 0.
        self.correction = 0.
        self.tau = .3

    def reset(self, track):
        self.track = track
        self.base = track.position
        self.correction = 0.

    def update(self, track):
        old = self.track
        if old and old.key == track.key and old.playing and track.playing and track.sampled_at >= old.sampled_at:
            predicted = self.position_at(track.sampled_at)
            error = track.position-predicted
            if abs(error) <= .55:
                self.base = predicted
                self.correction = error
                self.tau = max(.3, abs(error)*2)
                self.track = track
                return
        self.reset(track)

    def position_at(self, now):
        if self.track is None:
            return 0.
        elapsed = max(0., now-self.track.sampled_at) if self.track.playing else 0.
        value = self.base + elapsed + self.correction*(1-math.exp(-elapsed/self.tau))
        return max(0., min(self.track.duration or float('inf'), value))
