"""Read-only Apple Music TTML cache lookup; see APPLE-MUSIC-LYRICS-LICENSE."""
import json
import logging
import re
import sqlite3
from pathlib import Path
from xml.etree import ElementTree as ET
from .core import Line, Word, match_candidate, parse_lrc

ROOT = Path.home()/'Library/Caches/com.apple.Music'


def timestamp(value):
    if not value:
        return None
    if value.endswith('ms'):
        return float(value[:-2])/1000
    if value.endswith('s'):
        return float(value[:-1])
    out = 0.
    for part in value.split(':'):
        out = out*60+float(part)
    return out


def parse_ttml(raw):
    if '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper():
        return [], False
    root = ET.fromstring(raw)
    lines, exact = [], False
    for p in root.iter():
        if p.tag.rsplit('}', 1)[-1] != 'p':
            continue
        start, end = timestamp(p.get('begin')), timestamp(p.get('end'))
        if start is None:
            continue
        parts = []
        timed = False
        def walk(node, a, b):
            nonlocal timed
            if any(k.endswith('}role') and v in ('x-bg', 'x-translation', 'x-roman') for k, v in node.attrib.items()):
                return
            a = timestamp(node.get('begin')) if node.get('begin') else a
            b = timestamp(node.get('end')) if node.get('end') else b
            if node is not p and node.get('begin'):
                timed = True
            if node.text:
                parts.append((node.text, a, b))
            for child in node:
                walk(child, a, b)
                if child.tail:
                    parts.append((child.tail, a, b))
        walk(p, start, end or start+5)
        content = ''.join(text for text, _, _ in parts).strip()
        if not content:
            continue
        if not timed:
            minutes, seconds = divmod(start, 60)
            lines.extend(parse_lrc(f'[{int(minutes):02d}:{seconds:06.3f}]{content}', end or start+5))
            continue
        exact = True
        words = []
        buffer, begins, ends = '', None, None
        for text, a, b in parts:
            for token in re.findall(r'\s+|\S+', text):
                if token.isspace():
                    if buffer:
                        words.append(Word(buffer+' ', begins, max(begins+.01, ends)))
                        buffer, begins, ends = '', None, None
                else:
                    buffer += token
                    begins = a if begins is None else min(begins, a)
                    ends = b if ends is None else max(ends, b)
        if buffer:
            words.append(Word(buffer, begins, max(begins+.01, ends)))
        if words:
            lines.append(Line(start, end or words[-1].end, content, words))
    return sorted(lines, key=lambda line: line.start), exact


def apple_lyrics(track):
    db_path = ROOT/'Cache.db'
    if not db_path.exists():
        return [], ''
    try:
        with sqlite3.connect(db_path.as_uri()+'?mode=ro', uri=True, timeout=.25) as db:
            rows = db.execute("""SELECT d.isDataOnFS,d.receiver_data FROM cfurl_cache_response r
                JOIN cfurl_cache_receiver_data d USING(entry_ID)
                WHERE r.request_key LIKE '%syllable-lyrics%' ORDER BY r.time_stamp DESC LIMIT 80""").fetchall()
        for on_disk, payload in rows:
            if int(on_disk):
                name = payload if isinstance(payload, str) else payload.decode('utf-8')
                if not re.fullmatch(r'[a-fA-F0-9-]{36}', name):
                    continue
                file = ROOT/'fsCachedData'/name
                if not file.exists() or file.stat().st_size > 5_000_000:
                    continue
                payload = file.read_bytes()
            try:
                data = json.loads(payload)
                for song in data.get('data', []):
                    meta = song.get('attributes', {})
                    if not match_candidate(track, meta.get('name', ''), meta.get('artistName', ''), meta.get('durationInMillis', 0)/1000):
                        continue
                    documents = song.get('relationships', {}).get('syllable-lyrics', {}).get('data', [])
                    for document in documents:
                        raw = document.get('attributes', {}).get('ttmlLocalizations')
                        if isinstance(raw, dict):
                            raw = raw.get('en') or raw.get('en-US') or next(iter(raw.values()), '')
                        if isinstance(raw, str) and raw.lstrip().startswith('<'):
                            lines, exact = parse_ttml(raw)
                            if lines:
                                return lines, 'Apple Music · exact word timing' if exact else 'Apple Music · synced lines'
            except (ValueError, TypeError, ET.ParseError):
                continue
    except (OSError, sqlite3.Error):
        logging.info('Apple Music lyric cache unavailable; using online providers')
    return [], ''
