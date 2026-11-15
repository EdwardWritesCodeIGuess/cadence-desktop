"""Portable timing and lyric parsing. Interpolation adapted from Maestro (MIT)."""
from dataclasses import dataclass, field
from bisect import bisect_right
import re
import unicodedata
from .motion import PlaybackClock

@dataclass(frozen=True)
class Track:
    title: str = ''
    artist: str = ''
    album: str = ''
    identifier: str = ''
    duration: float = 0
    position: float = 0
    playing: bool = False
    sampled_at: float = 0

    @property
    def key(self):
        return (self.identifier, self.title, self.artist, self.album) if self.title else None

    def position_at(self, now):
        elapsed = max(0, now - self.sampled_at) if self.playing else 0
        return max(0, min(self.duration or float('inf'), self.position + elapsed))

@dataclass
class Word:
    text: str
    start: float
    end: float

@dataclass
class Line:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


CJK = '぀-ヿ㐀-鿿'
WORD_TAG = re.compile(r'<(\d+):(\d+(?:\.\d+)?)>')
VOWELS = re.compile('[aeiouyаеёиоуыэюяαεηιουω]+')


def syllables(token):
    """Rough syllable count. Sung rhythm follows syllables far more than letters."""
    hangul = sum('가' <= c <= '힣' for c in token)
    if hangul:
        return float(hangul)
    letters = ''.join(c for c in unicodedata.normalize('NFKD', token.casefold()) if c.isalpha())
    if not letters:
        return 0.
    groups = float(len(VOWELS.findall(letters)))
    if not groups:
        return max(1., len(letters)/3)
    if groups > 1 and letters.isascii():
        # Usually-silent English endings; half a syllable keeps other languages reasonable.
        silent_e = letters.endswith('e') and not letters.endswith(('le', 'ee', 'ye'))
        silent_ed = letters.endswith(('ed', 'es')) and not letters.endswith(('ted', 'ded', 'ses', 'xes', 'zes', 'ches', 'shes'))
        if silent_e or silent_ed:
            groups -= .5
    return groups


def sung_weights(tokens):
    """Relative time each token takes when a line has no word timestamps."""
    weights = []
    for index, token in enumerate(tokens):
        bare = token.strip()
        if len(bare) == 1 and re.match('[%s]' % CJK, bare):
            weight = 1.
        else:
            count = syllables(bare)
            weight = count+.08*len(bare) if count else max(1., .6*len(bare))
        if index < len(tokens)-1:
            # A comma or full stop inside a line is a short breath.
            weight += .5 if bare[-1:] in ',;:' else .8 if bare[-1:] in '.!?…' else 0
        weights.append(weight)
    if len(weights) >= 3:
        weights[-1] *= 1.35  # The last word of a phrase is usually held.
    return weights


def parse_lrc(raw, duration=0):
    offset = re.search(r'\[offset:([+-]?\d+)\]', raw, re.I)
    shift = int(offset[1]) / 1000 if offset else 0
    entries = []
    for row in raw.splitlines():
        stamps = list(re.finditer(r'\[(\d+):(\d+(?:\.\d+)?)\]', row))
        if not stamps:
            continue
        text = row[stamps[-1].end():].strip()
        if len(stamps) > 1:
            text = WORD_TAG.sub('', text)
        for stamp in stamps:
            entries.append((max(0, int(stamp[1]) * 60 + float(stamp[2]) + shift), text))
    entries = sorted(set(entries))
    lines = []
    for i, (t, text) in enumerate(entries):
        end = entries[i+1][0] if i+1 < len(entries) else max(t+4, duration)
        parts = WORD_TAG.split(text)
        line = Line(t, end, ''.join(parts[::3]).strip())
        # Enhanced LRC: <mm:ss.xx> before each word is a real word timestamp.
        times = [max(0, int(parts[k])*60+float(parts[k+1])+shift) for k in range(1, len(parts), 3)]
        if parts[0].strip() and times:
            line.words.append(Word(parts[0], t, max(t+.01, times[0])))
        for n, start in enumerate(times):
            value = parts[3*n+3]
            if value.strip():
                stop = times[n+1] if n+1 < len(times) else min(end, start+1.5)
                line.words.append(Word(value, start, max(start+.01, stop)))
        lines.append(line)
    tokens = [re.findall(r'[%s][^\S\n]*|[^\s%s]+\s*' % (CJK, CJK), ln.text) for ln in lines]
    weights = [sung_weights(row) for row in tokens]
    rates = sorted((ln.end-ln.start)/sum(row) for ln, row in zip(lines, weights)
                   if sum(row) > 2 and .3 < ln.end-ln.start < 20)
    ceiling = rates[round((len(rates)-1)*.75)] if len(rates) >= 5 else .6
    for ln, row, weight in zip(lines, tokens, weights):
        if ln.words or not row:
            continue
        # Preserve separators; unspaced CJK was split into displayable glyphs.
        gap = ln.end-ln.start
        # Leave a breath before the next line instead of stretching words into it.
        span = min(max(.05, gap-min(.25, gap*.1)), max(.6, sum(weight)*ceiling))
        cursor = ln.start
        for token, share in zip(row, weight):
            end = cursor + span * share / sum(weight)
            ln.words.append(Word(token, cursor, end))
            cursor = end
    return lines


def parse_yrc(raw):
    lines = []
    for row in raw.splitlines():
        match = re.match(r'\[(\d+),(\d+)\]', row)
        if not match:
            continue
        words = [Word(text, int(t)/1000, (int(t)+int(d))/1000)
                 for t, d, text in re.findall(r'\((\d+),(\d+),\d+\)([^\(]*)', row[match.end():])]
        if words:
            lines.append(Line(int(match[1])/1000, (int(match[1])+int(match[2]))/1000,
                              ''.join(w.text for w in words), words))
    return sorted(lines, key=lambda ln: ln.start)


def active_line(lines, position, starts=None):
    index = bisect_right(starts if starts is not None else [ln.start for ln in lines], position) - 1
    return index if index >= 0 and position < lines[index].end else -1


def display_line(lines, position, starts=None, hold=2.):
    """(index, gap) of the line to show.

    Word-synced sources end a line when its last word ends, so every breath
    between lines used to blank the display. A finished line is now held across
    gaps up to `hold` seconds. Otherwise index is -1 and gap is the (start, end)
    of the pause; end is None after the last line.
    """
    if starts is None:
        starts = [ln.start for ln in lines]
    index = bisect_right(starts, position) - 1
    if index < 0:
        return -1, (0., starts[0] if starts else None)
    if lines[index].text and position < lines[index].end:
        return index, None
    previous, begin = (index, lines[index].end) if lines[index].text else (index-1, lines[index].start)
    finish = starts[index+1] if index+1 < len(lines) else None
    if previous >= 0 and lines[previous].text and finish is not None and finish-begin <= hold:
        return previous, None
    return -1, (begin, finish)


def demo_lines():
    """Original placeholder words for the live preview; never real lyrics."""
    return parse_lrc('[00:00.60]Give every word a little life\n[00:04.20]Watch the letters catch the light\n'
                     '[00:07.80]Pick a style and make it yours\n[00:11.20]Then press play\n[00:13.60]', DEMO_LENGTH)


DEMO_LENGTH = 15.
DEMO_TRACK = Track(title='Cadence preview', artist='Play a song in Apple Music to see your lyrics',
                   identifier='cadence-preview', duration=DEMO_LENGTH, playing=True)


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if c.isalnum())


# Labels that never change a recording's timing. Live, remix, edit and
# "version" qualifiers are kept so a different recording is still rejected.
DECORATION = (r'explicit|clean|(?:\d{4}\s+)?remaster(?:ed)?(?:\s+\d{4})?(?:\s+version)?'
              r'|deluxe(?:\s+(?:edition|version))?|bonus\s+track|album\s+version|(?:mono|stereo)(?:\s+(?:version|mix))?')


def clean_title(value):
    value = re.sub(r'\s*[\(\[][^)\]]*\b(?:feat\.?|ft\.?|with)\b[^)\]]*[\)\]]', '', value, flags=re.I)
    value = re.sub(r'\s*[\(\[]\s*(?:%s)\s*[\)\]]' % DECORATION, '', value, flags=re.I)
    return re.sub(r'\s+[-–—]\s+(?:%s)\s*$' % DECORATION, '', value, flags=re.I).strip()


def match_candidate(track, title, artist, duration):
    # Reject same-title covers and different live/edit versions.
    return (normalize(clean_title(track.title)) == normalize(clean_title(title))
            and bool(normalize(artist))
            and (normalize(track.artist) in normalize(artist) or normalize(artist) in normalize(track.artist))
            and (not track.duration or abs(float(duration or 0)-track.duration) <= 10))


class Playback:
    """A generation key prevents slow requests from repainting a newer song."""
    def __init__(self):
        self.track = Track()
        self.lines = []
        self.source = ''
        self.generation = 0
        self.clock = PlaybackClock()

    @property
    def lines(self):
        return self._lines

    @lines.setter
    def lines(self, value):
        # Line starts are cached here so drawing never rebuilds them per frame.
        self._lines = value
        self.starts = [ln.start for ln in value]

    def update(self, track):
        changed = track.key != self.track.key
        self.clock.update(track)
        self.track = track
        if changed:
            self.generation += 1
            self.lines = []
            self.source = ''
        return changed

    def position_at(self, now):
        return self.clock.position_at(now)

    def accept(self, generation, lines, source):
        if generation != self.generation:
            return False
        def quality(label):
            return 4 if 'exact word' in label else 3 if label == 'Word-synced lyrics' else 2 if label.startswith('Apple Music') else 0 if label.startswith('NetEase') else 1
        if self.lines and (not lines or quality(self.source) > quality(source)):
            return False
        self.lines, self.source = lines, source
        return True
