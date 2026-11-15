"""Continuous motion envelopes and a playback clock that absorbs polling jitter."""
import math


def smoothstep(value):
    t = max(0., min(1., value))
    return t*t*(3-2*t)


def spring(t, omega=26., zeta=.42):
    """Step response of an underdamped spring: (value, velocity/omega).

    Starts at rest on 0, overshoots once, and settles on 1. The normalized
    velocity drives squash and stretch so the shape follows the movement.
    """
    if t <= 0:
        return 0., 0.
    root = math.sqrt(1-zeta*zeta)
    damped = omega*root
    decay = math.exp(-zeta*omega*t)
    value = 1-decay*(math.cos(damped*t)+zeta/root*math.sin(damped*t))
    return value, decay*math.sin(damped*t)/root


def word_motion(position, start, end, speed=1., amount=.35, motion=True):
    """No discontinuity at either edge of a word, including very short words.

    Returns highlight, scale, alpha, entered and a lift (fraction of the font
    size) so the word being sung hops slightly above its neighbours.
    """
    duration = max(.02, end-start)
    attack = max(.015, min(.08/speed, duration*.3))
    release = .16/speed
    entered = smoothstep((position-start)/attack)
    highlight = entered*(1-smoothstep((position-end)/release))
    age = max(0., position-start)
    # A damped wobble: a quick overshoot, one small settle, then a steady lift.
    bump = math.exp(-age*7*speed)*math.cos(age*15*speed)
    scale = 1 + (amount*highlight*(.2+1.1*bump) if motion else 0)
    lift = amount*highlight*(.12+.6*max(0., bump)) if motion else 0.
    alpha = .45+.4*entered+.15*highlight
    return highlight, scale, alpha, entered, lift


def kinetic_pose(age, duration, speed=1., amount=.35, motion=True):
    """Entrance of one large word: (alpha, scale, stretch, tilt, rise).

    scale springs from a smaller size past 1 and settles; stretch is the
    signed squash/stretch to apply (taller and narrower while growing); tilt
    and rise run from 1 to 0 and scale a rotation and a vertical offset.
    """
    if not motion:
        return 1., 1., 0., 0., 0.
    fade = max(.02, min(.09/speed, duration*.4))
    value, velocity = spring(age*speed)
    return (smoothstep(age/fade), 1-.9*amount*(1-value), .5*amount*velocity,
            1-spring(age*speed, 20., .5)[0], 1-value)


def kinetic_peak(amount):
    """Largest scale kinetic_pose reaches, so layouts can leave headroom."""
    return 1+.9*amount*math.exp(-math.pi*.42/math.sqrt(1-.42*.42))


def settle(position, end, floor=.62):
    """A word that has been sung relaxes instead of staying at full strength."""
    return 1-(1-floor)*smoothstep((position-end)/.5)


def approach(current, target, dt, rate=5.):
    """Frame-rate independent easing of a tuple of numbers towards a target."""
    blend = 1-math.exp(-max(0., dt)*rate)
    return tuple(a+(b-a)*blend for a, b in zip(current, target))


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
                # Errors of a few hundredths are mostly Apple Event latency, not
                # real drift, so follow them half-way instead of chasing each one.
                gain = .5+.5*smoothstep((abs(error)-.03)/.07)
                self.base = predicted
                self.correction = error*gain
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
