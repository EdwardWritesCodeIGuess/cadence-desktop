import json
from pathlib import Path

SUPPORT = Path.home() / 'Library/Application Support/Cadence'
LYRIC_STYLES = ('Kinetic Word', 'Ransom Note', 'Pop', 'Spotlight', 'Ribbon', 'Scroll', 'Typewriter', 'Neon', 'Wave')
DEFAULTS = dict(width=680, height=340, font_size=38, opacity=.65, style='Aurora',
                lyric_style='Kinetic Word', font='SF Rounded', accent='#A8BAFF',
                auto_color=True, motion=True, locked=False, show_art=True,
                offset=.22, x=None, y=None, layout='Full widget', show_title=True,
                show_progress=True, show_time=True, show_source=True, show_neighbors=True,
                scroll_lines=True, pop_amount=.35, animation_speed=1., line_spacing=1.4,
                context_opacity=.3, text_opacity=1., ransom_chaos=.65, alignment='Center',
                text_color='#FFFFFF', lock_screen=True, stretch_fill=.8, widget_preset='Custom', show_clock=False, settings_version=4)
RANGES = {'width': (360, 1200), 'height': (180, 700), 'font_size': (20, 80),
          'opacity': (0, 1), 'offset': (-5, 5), 'pop_amount': (0, .8),
          'animation_speed': (.5, 2), 'line_spacing': (1.1, 2),
          'context_opacity': (0, .8), 'text_opacity': (.2, 1), 'ransom_chaos': (0, 1), 'stretch_fill': (0, 1)}

class Settings(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        try:
            data = json.loads((SUPPORT/'settings.json').read_text(encoding='utf-8'))
            for key, default in DEFAULTS.items():
                value = data.get(key, default)
                if default is None:
                    if isinstance(value, (float, int)):
                        self[key] = value
                elif isinstance(value, type(default)) or isinstance(default, float) and isinstance(value, int):
                    self[key] = value
            if data.get('settings_version', 1) < 2 and data.get('offset', 0) == 0:
                self['offset'] = .22
        except (OSError, ValueError, TypeError):
            pass
        if self.get('settings_version', 1) < 4:
            self['lyric_style'] = 'Kinetic Word'
            self['show_neighbors'] = False
        self['settings_version'] = 4
        for key, (low, high) in RANGES.items():
            self[key] = max(low, min(high, self[key]))
        for key, options in [('style', ('Aurora', 'Glass', 'Typography')), ('lyric_style', LYRIC_STYLES),
                             ('layout', ('Full widget', 'Lyrics only')), ('alignment', ('Left', 'Center', 'Right'))]:
            if self[key] not in options:
                self[key] = DEFAULTS[key]
        for key in ('accent', 'text_color'):
            try:
                assert len(self[key]) == 7 and self[key].startswith('#')
                int(self[key][1:], 16)
            except (ValueError, AssertionError):
                self[key] = DEFAULTS[key]

    def save(self):
        SUPPORT.mkdir(parents=True, exist_ok=True)
        temp = SUPPORT/'settings.tmp'
        temp.write_text(json.dumps(self, indent=2), encoding='utf-8')
        temp.replace(SUPPORT/'settings.json')
