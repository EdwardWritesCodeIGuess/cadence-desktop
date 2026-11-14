"""On-demand Apple Intelligence catalogue matching; never generates lyric text."""
import json
import re
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from Foundation import NSBundle
from .core import normalize, clean_title
from .providers import lyrics


def helper_path():
    bundle = Path(str(NSBundle.mainBundle().resourcePath() or ''))/'CadenceAI'
    return bundle if bundle.is_file() else Path(__file__).resolve().parents[1]/'native/build/CadenceAI'


def validated_query(track, response):
    title, artist = response.get('title', ''), response.get('artist', '')
    cleaned = re.sub(r'\s*[\(\[]\s*official\s+(?:audio|video|music video|lyric video)\s*[\)\]]', '', track.title, flags=re.I)
    if not isinstance(title, str) or not isinstance(artist, str) or not title:
        raise RuntimeError('Apple Intelligence returned an incomplete match; lyrics unchanged')
    if normalize(artist) != normalize(track.artist) or normalize(clean_title(title)) not in (normalize(clean_title(track.title)), normalize(clean_title(cleaned))):
        raise RuntimeError('AI suggestion would change the song or version; lyrics unchanged')
    return replace(track, title=title, artist=artist)


def refine(track, visible):
    executable = helper_path()
    if not executable.is_file():
        raise RuntimeError('Apple Intelligence helper is not installed')
    if not visible.is_set():
        raise RuntimeError('Show the widget before using Apple Intelligence')
    process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    started = time.monotonic()
    try:
        payload = json.dumps(dict(title=track.title, artist=track.artist)).encode()
        while True:
            try:
                out, err = process.communicate(payload, timeout=.2)
                break
            except subprocess.TimeoutExpired:
                payload = None
                if not visible.is_set() or time.monotonic()-started > 30:
                    raise RuntimeError('Apple Intelligence stopped (hidden widget or time limit)')
        response = json.loads(out.decode('utf-8'))
        if response.get('error'):
            raise RuntimeError(response['error'])
        candidate = validated_query(track, response)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
    if candidate.title == track.title and candidate.artist == track.artist:
        raise RuntimeError('Apple Intelligence confirmed the current song metadata.')
    if not visible.is_set():
        raise RuntimeError('Refinement stopped because the widget is hidden')
    return lyrics(candidate)
