"""Bounded network lookups and on-disk caching. No account or API key needed."""
import hashlib
import json
import logging
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path
import certifi
from .core import parse_lrc, parse_yrc, match_candidate, clean_title

CACHE = Path.home() / 'Library/Caches/Cadence'
CONTEXT = ssl.create_default_context(cafile=certifi.where())


def fetch(url, params=None, binary=False):
    if params:
        url += '?' + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={'User-Agent': 'Cadence/1.0 (macOS desktop lyrics)',
                                                 'Referer': 'https://music.163.com'})
    with urllib.request.urlopen(request, timeout=6, context=CONTEXT) as response:
        raw = response.read(5_000_000)
    return raw if binary else json.loads(raw)


def lyrics(track):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha256(repr(track.key).encode()).hexdigest() + '.json')
    try:
        cached = json.loads(path.read_text())
        if time.time()-cached['time'] < 7*86400:
            parser = parse_yrc if cached['kind'] == 'yrc' else lambda text: parse_lrc(text, track.duration)
            return parser(cached['raw']), cached['source']
    except (OSError, ValueError, KeyError):
        pass

    def result(raw, kind, source):
        lines = parse_yrc(raw) if kind == 'yrc' else parse_lrc(raw, track.duration)
        if lines:
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(dict(time=time.time(), raw=raw, kind=kind, source=source)))
            temp.replace(path)
        return lines, source

    exact = {'track_name': track.title, 'artist_name': track.artist, 'album_name': track.album}
    if track.duration:
        exact['duration'] = round(track.duration)
    had_response = False
    for endpoint, params in [('get', exact), ('search', {'track_name': clean_title(track.title), 'artist_name': track.artist})]:
        try:
            data = fetch('https://lrclib.net/api/' + endpoint, params)
            had_response = True
            candidates = data if isinstance(data, list) else [data]
            candidates = [c for c in candidates if match_candidate(track, c.get('trackName', ''), c.get('artistName', ''), c.get('duration', 0))]
            candidates.sort(key=lambda c: abs(c.get('duration', 0)-track.duration))
            for item in candidates:
                if item.get('syncedLyrics'):
                    return result(item['syncedLyrics'], 'lrc', 'Synced lines · estimated word timing')
                if item.get('instrumental'):
                    return [], 'Instrumental'
        except Exception as exc:
            logging.info('LRCLIB %s: %s', endpoint, type(exc).__name__)
    return [], 'No synced lyrics found' if had_response else 'Lyrics unavailable · check connection'


def word_lyrics(track):
    """Run alongside LRCLIB; true word timestamps upgrade the display on arrival."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha256(repr(track.key).encode()).hexdigest()+'.words.json')
    try:
        cached = json.loads(path.read_text(encoding='utf-8'))
        if time.time()-cached['time'] < 7*86400:
            return parse_yrc(cached['raw']), 'Word-synced lyrics'
    except (OSError, ValueError, KeyError):
        pass
    try:
        data = fetch('https://music.163.com/api/search/get', {'type': 1, 'limit': 10, 's': clean_title(track.title)+' '+track.artist})
        candidates = data.get('result', {}).get('songs', [])
        candidates.sort(key=lambda c: abs(c.get('duration', 0)/1000-track.duration))
        for candidate in candidates:
            artist = ', '.join(a['name'] for a in candidate.get('artists', []))
            if not match_candidate(track, candidate['name'], artist, candidate.get('duration', 0)/1000):
                continue
            data = fetch('https://music.163.com/api/song/lyric/v1', {'id': candidate['id'], 'lv': 1, 'yv': 1, 'tv': 1})
            raw = data.get('yrc', {}).get('lyric', '')
            lines = parse_yrc(raw)
            if lines:
                try:
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', dir=CACHE, delete=False, encoding='utf-8') as output:
                        json.dump(dict(time=time.time(), raw=raw), output)
                        temp = Path(output.name)
                    temp.replace(path)
                except OSError:
                    logging.info('Could not cache word timestamps')
                return lines, 'Word-synced lyrics'
            lrc = data.get('lrc', {}).get('lyric', '')
            if lrc:
                return parse_lrc(lrc, track.duration), 'NetEase lines · estimated word timing'
            break
    except Exception as exc:
        logging.info('Word timing lookup: %s', type(exc).__name__)
    return [], 'No word timestamps available'


def artwork(track):
    try:
        data = fetch('https://itunes.apple.com/search', {'term': track.title+' '+track.artist, 'entity': 'song', 'limit': 8})
        for item in data.get('results', []):
            if match_candidate(track, item.get('trackName', ''), item.get('artistName', ''), item.get('trackTimeMillis', 0)/1000):
                url = item.get('artworkUrl100', '').replace('100x100bb', '300x300bb')
                if url.startswith('https://'):
                    return fetch(url, binary=True)
    except Exception as exc:
        logging.info('Artwork: %s', type(exc).__name__)
    return None
