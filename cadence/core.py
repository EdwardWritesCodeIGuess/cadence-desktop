"""Portable timing and lyric parsing. Interpolation adapted from Maestro (MIT)."""
from dataclasses import dataclass, field
from bisect import bisect_right
import re
import unicodedata

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


def parse_lrc(raw, duration=0):
    offset = re.search(r'\[offset:([+-]?\d+)\]', raw, re.I)
    shift = int(offset[1]) / 1000 if offset else 0
    entries = []
    for row in raw.splitlines():
        stamps = list(re.finditer(r'\[(\d+):(\d+(?:\.\d+)?)\]', row))
        if not stamps:
            continue
        text = row[stamps[-1].end():].strip()
        for stamp in stamps:
            entries.append((max(0, int(stamp[1]) * 60 + float(stamp[2]) + shift), text))
    entries = sorted(set(entries))
    lines = [Line(t, entries[i+1][0] if i+1 < len(entries) else max(t+4, duration), text)
             for i, (t, text) in enumerate(entries)]
    rates = sorted((ln.end-ln.start)/len(re.sub(r'\s', '', ln.text))
                   for ln in lines if len(re.sub(r'\s', '', ln.text)) > 2 and .3 < ln.end-ln.start < 20)
    ceiling = rates[round((len(rates)-1)*.75)] if len(rates) >= 5 else .23
    for ln in lines:
        # Preserve separators; split unspaced CJK into displayable glyphs.
        tokens = re.findall(r'[\u3040-\u30ff\u3400-\u9fff][^\S\n]*|[^\s\u3040-\u30ff\u3400-\u9fff]+\s*', ln.text)
        weights = [max(1, len(t.strip())) for t in tokens]
        span = min(max(.05, ln.end-ln.start), max(.6, sum(weights)*ceiling))
        cursor = ln.start
        for token, weight in zip(tokens, weights):
            end = cursor + span * weight / sum(weights)
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


def active_line(lines, position):
    index = bisect_right([ln.start for ln in lines], position) - 1
    return index if index >= 0 and position < lines[index].end else -1


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if c.isalnum())


def clean_title(value):
    return re.sub(r'\s*[\(\[][^)\]]*\b(?:feat\.?|ft\.?|with)\b[^)\]]*[\)\]]', '', value, flags=re.I).strip()


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

    def update(self, track):
        changed = track.key != self.track.key
        self.track = track
        if changed:
            self.generation += 1
            self.lines = []
            self.source = ''
        return changed

    def accept(self, generation, lines, source):
        if generation != self.generation:
            return False
        def quality(label):
            return 2 if label == 'Word-synced lyrics' else 0 if label.startswith('NetEase') else 1
        if self.lines and (not lines or quality(self.source) > quality(source)):
            return False
        self.lines, self.source = lines, source
        return True
