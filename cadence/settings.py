import json
from pathlib import Path

SUPPORT = Path.home() / 'Library/Application Support/Cadence'
DEFAULTS = dict(width=620, height=310, font_size=36, opacity=.65, style='Aurora',
                font='SF Rounded', accent='#A8BAFF', auto_color=True, motion=True,
                locked=False, show_art=True, offset=0., x=None, y=None)

class Settings(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        try:
            data = json.loads((SUPPORT/'settings.json').read_text())
            for key in DEFAULTS:
                if key not in data:
                    continue
                default, value = DEFAULTS[key], data[key]
                if default is None:
                    if isinstance(value, (float, int)):
                        self[key] = value
                elif isinstance(value, type(default)) or isinstance(default, float) and isinstance(value, int):
                    self[key] = value
        except (OSError, ValueError, TypeError):
            pass
        for key, low, high in [('width', 360, 1000), ('height', 220, 600), ('font_size', 20, 60), ('opacity', 0, 1), ('offset', -3, 3)]:
            self[key] = max(low, min(high, self[key]))
        if self['style'] not in ('Aurora', 'Glass', 'Typography'):
            self['style'] = 'Aurora'
        if len(self['accent']) != 7 or not self['accent'].startswith('#'):
            self['accent'] = DEFAULTS['accent']

    def save(self):
        SUPPORT.mkdir(parents=True, exist_ok=True)
        temp = SUPPORT/'settings.tmp'
        temp.write_text(json.dumps(self, indent=2))
        temp.replace(SUPPORT/'settings.json')
