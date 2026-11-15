"""Native kinetic typography and procedural paper cutouts. No downloaded assets."""
import math
import random
import hashlib
import time
import zlib
from datetime import datetime
from functools import lru_cache
import AppKit as A
import Foundation as F
from .core import active_line, display_line, demo_lines, DEMO_TRACK, DEMO_LENGTH
from .motion import word_motion, smoothstep, kinetic_pose, kinetic_peak, settle, approach
from .palette import from_hex, DEFAULT_SECONDARY


@lru_cache(maxsize=64)
def rgb(hex_value):
    return from_hex(hex_value)


def color(value, alpha=1):
    """Accepts '#RRGGBB' or an (r, g, b) tuple, so animated colours need no hex round trip."""
    red, green, blue = value if isinstance(value, tuple) else rgb(value)
    return A.NSColor.colorWithCalibratedRed_green_blue_alpha_(red, green, blue, alpha)


@lru_cache(maxsize=128)
def font(size, face='SF Rounded', weight=A.NSFontWeightMedium):
    if face in ('SF Rounded', 'SF Pro'):
        base = A.NSFont.systemFontOfSize_weight_(size, weight)
        if face == 'SF Rounded':
            descriptor = base.fontDescriptor().fontDescriptorWithDesign_(A.NSFontDescriptorSystemDesignRounded)
            if descriptor:
                return A.NSFont.fontWithDescriptor_size_(descriptor, size)
        return base
    return A.NSFont.fontWithName_size_(face, size) or A.NSFont.systemFontOfSize_(size)


@lru_cache(maxsize=2)
def paragraph(centered):
    style = A.NSMutableParagraphStyle.alloc().init()
    style.setLineBreakMode_(A.NSLineBreakByTruncatingTail)
    style.setAlignment_(A.NSTextAlignmentCenter if centered else A.NSTextAlignmentLeft)
    return style


def text(value, rect, size=13, tint='#FFFFFF', alpha=1, face='SF Pro', centered=False, weight=A.NSFontWeightMedium):
    attrs = {A.NSFontAttributeName: font(size, face, weight), A.NSForegroundColorAttributeName: color(tint, alpha), A.NSParagraphStyleAttributeName: paragraph(centered)}
    F.NSString.stringWithString_(str(value)).drawInRect_withAttributes_(rect, attrs)


def rounded(rect, radius=20):
    return A.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius)


@lru_cache(maxsize=2048)
def measure(value, size, face):
    return F.NSString.stringWithString_(value).sizeWithAttributes_({A.NSFontAttributeName: font(size, face, A.NSFontWeightSemibold)}).width


@lru_cache(maxsize=512)
def measure_heavy(value, size, face):
    return F.NSString.stringWithString_(value).sizeWithAttributes_({A.NSFontAttributeName: font(size, face, A.NSFontWeightHeavy)}).width


def beat(line, position, speed=1.):
    """1 at the start of each word, fading quickly: lets the backdrop breathe with the lyrics."""
    start = None
    for word in line.words:
        if word.start > position:
            break
        start = word.start
    return math.exp(-(position-start)*4.5*speed) if start is not None else 0.


def glow(tint, strength, radius):
    shadow = A.NSShadow.alloc().init()
    shadow.setShadowColor_(color(tint, max(0., min(1., strength))))
    shadow.setShadowBlurRadius_(radius)
    shadow.setShadowOffset_((0, 0))
    return shadow


def align_x(width, available, alignment, left=0):
    return left + (0 if alignment == 'Left' else available-width if alignment == 'Right' else (available-width)/2)


@lru_cache(maxsize=1024)
def paper_metrics(value, size, chaos, seed):
    """Measure cutouts without rasterizing candidates during text fitting."""
    rng = random.Random(seed)
    faces = ['Georgia-Bold', 'Courier-Bold', 'HelveticaNeue-CondensedBlack', 'AvenirNext-Heavy', 'TimesNewRomanPS-BoldMT']
    palettes = [('#F5EAD4', '#22202B'), ('#DFD7C6', '#19151E'), ('#25212D', '#FFF4DD'),
                ('#F2A9BD', '#30202C'), ('#D3DCBB', '#20291E'), ('#DBC6EB', '#302A3B')]
    glyphs = []
    for ch in value:
        face = rng.choice(faces)
        scale = 1+rng.uniform(-.12, .10)*chaos
        glyph_size = size*scale
        width = measure(ch, glyph_size, face)+size*.17
        glyphs.append((ch, face, glyph_size, width, rng.choice(palettes), rng.uniform(-9, 9)*chaos, rng.uniform(-.07, .07)*size*chaos))
    width = sum(g[3]+size*.045 for g in glyphs)+size*.35
    height = size*1.65
    return tuple(glyphs), width, height


@lru_cache(maxsize=192)
def paper_word(value, size, chaos, seed):
    glyphs, width, height = paper_metrics(value, size, chaos, seed)
    rng = random.Random(seed ^ 0xCADE)
    image = A.NSImage.alloc().initWithSize_((max(1, width), height))
    image.lockFocusFlipped_(True)
    x = size*.15
    for ch, face, glyph_size, gw, palette, angle, jitter in glyphs:
        A.NSGraphicsContext.saveGraphicsState()
        transform = A.NSAffineTransform.transform()
        transform.translateXBy_yBy_(x+gw/2, height/2+jitter)
        transform.rotateByDegrees_(angle)
        transform.concat()
        paper = A.NSBezierPath.bezierPath()
        gh = size*1.18
        points = [(-gw/2, -gh/2+1), (gw*.12, -gh/2-1), (gw/2, -gh/2+2),
                  (gw/2-1, gh/2), (-gw*.15, gh/2-1), (-gw/2+1, gh/2+1)]
        paper.moveToPoint_(points[0])
        for point in points[1:]:
            paper.lineToPoint_(point)
        paper.closePath()
        color('#000000', .25).set()
        shadow = A.NSAffineTransform.transform(); shadow.translateXBy_yBy_(1.5, 2); shadow.concat()
        paper.fill(); shadow.invert(); shadow.concat()
        color(palette[0]).set(); paper.fill()
        # Fine ink/paper marks create texture without bitmap downloads.
        color('#41372F', .10).setStroke()
        for _ in range(3):
            yy = rng.uniform(-gh*.4, gh*.4)
            line = A.NSBezierPath.bezierPath(); line.setLineWidth_(.45)
            line.moveToPoint_((-gw*.4, yy)); line.lineToPoint_((gw*.4, yy+rng.uniform(-1, 1))); line.stroke()
        attrs = {A.NSFontAttributeName: font(glyph_size, face, A.NSFontWeightBold), A.NSForegroundColorAttributeName: color(palette[1])}
        F.NSString.stringWithString_(ch).drawAtPoint_withAttributes_((-measure(ch, glyph_size, face)/2, -glyph_size*.65), attrs)
        A.NSGraphicsContext.restoreGraphicsState()
        x += gw+size*.045
    image.unlockFocus()
    return image, width, height


@lru_cache(maxsize=192)
def layout_words(tokens, size, face, available, ransom, chaos):
    rows, widths = [[]], [0.]
    for index, value in enumerate(tokens):
        seed = int.from_bytes(hashlib.blake2b((str(index)+value).encode(), digest_size=4).digest(), 'little')
        image = None
        if ransom:
            image = (value.strip(), size*.82, chaos, seed)
            _, width, height = paper_metrics(*image)
        else:
            width = measure(value.strip(), size, face)
        width += size*.25
        if rows[-1] and widths[-1]+width > available:
            rows.append([]); widths.append(0.)
        rows[-1].append((index, width, image))
        widths[-1] += width
    return rows, widths


@lru_cache(maxsize=96)
def fit_phrase(tokens, size, face, w, area, neighbors, mode, chaos, spacing):
    ransom = mode == 'Ransom Note'
    room = max(30, area-(68 if neighbors and mode != 'Pop' else 16))
    while True:
        rows, widths = layout_words(tokens, size, face, w-80, ransom, chaos)
        row_height = size*max(spacing, 1.55 if ransom else 1.1)
        if (len(rows)*row_height <= room and max(widths, default=0) <= w-80) or size <= 14:
            return size, row_height, rows, widths
        size -= 2


class Renderer:
    def __init__(self):
        self.key = None
        self.index = -1
        self.last_position = 0
        self.line_start = 0
        self.scrolling = False
        self.ribbon_x = None
        self.last_draw = 0
        self.warm_target = None
        self.warm_index = 0
        self.accent_rgb = None
        self.second_rgb = None
        self.track_key = None
        self.track_at = 0
        self.preview_lines = None
        self.preview_starts = None
        self.preview_epoch = 0

    def prewarm(self, owner, bounds):
        s = owner.settings
        if s['lyric_style'] != 'Ransom Note' or not owner.playback.lines:
            return
        lines = owner.playback.lines
        idx = active_line(lines, owner.playback.position_at(time.monotonic())+s['offset'], owner.playback.starts)+1
        if idx >= len(lines):
            return
        bare = s['layout'] == 'Lyrics only'
        top = 82 if s['show_title'] and not bare else 20
        bottom = bounds.size.height-(46 if (s['show_time'] or s['show_source']) and not bare else 26 if s['show_progress'] and not bare else 20)
        args = (tuple(w.text for w in lines[idx].words), s['font_size'], s['font'], bounds.size.width,
                bottom-top, s['show_neighbors'], 'Ransom Note', s['ransom_chaos'], s['line_spacing'])
        if self.warm_target != args:
            self.warm_target, self.warm_index = args, 0
        _, _, rows, _ = fit_phrase(*args)
        images = [image for row in rows for _, _, image in row if image]
        if self.warm_index < len(images):
            paper_word(*images[self.warm_index])
            self.warm_index += 1

    def paint(self, owner, bounds):
        s = owner.settings
        w, h = bounds.size.width, bounds.size.height
        now = time.monotonic()
        dt = min(.1, max(0, now-self.last_draw))
        self.last_draw = now
        motion = s['motion']
        playback = owner.playback
        track, lines, starts, source = playback.track, playback.lines, playback.starts, playback.source
        elapsed = playback.position_at(now)
        position = elapsed+s['offset']
        # With nothing playing, the Customize window drives a looping sample so
        # every control can be judged without starting a song.
        preview = not track.title and getattr(owner, 'previewing', False) and not getattr(owner, 'locked', False)
        if preview:
            if self.preview_lines is None:
                self.preview_lines = demo_lines()
                self.preview_starts = [ln.start for ln in self.preview_lines]
                self.preview_epoch = now
            track, lines, starts = DEMO_TRACK, self.preview_lines, self.preview_starts
            elapsed = position = (now-self.preview_epoch) % DEMO_LENGTH
        # Colours glide between songs instead of snapping.
        target = rgb(owner.accent if s['auto_color'] else s['accent'])
        second = rgb(getattr(owner, 'secondary', DEFAULT_SECONDARY) if s['auto_color'] else DEFAULT_SECONDARY)
        if self.accent_rgb is None or not motion:
            self.accent_rgb, self.second_rgb = target, second
        else:
            self.accent_rgb = approach(self.accent_rgb, target, dt, 4.5)
            self.second_rgb = approach(self.second_rgb, second, dt, 4.5)
        accent = self.accent_rgb
        if track.key != self.track_key:
            self.track_key, self.track_at = track.key, now
        appear = smoothstep((now-self.track_at)/.45) if motion else 1.
        opacity = s['opacity']
        bare = s['layout'] == 'Lyrics only'
        header = s['show_title'] and not bare
        footer = (s['show_time'] or s['show_source']) and not bare
        progress = s['show_progress'] and not bare
        top = 112 if s['show_clock'] and not bare else 82 if header else 20
        bottom = h-(46 if footer else 26 if progress else 20)
        album_card = s['widget_preset'] == 'Album card' and not bare and s['show_art']
        art_y = top
        art_side = min(w-64, (bottom-top)*.5) if album_card else 0
        if album_card:
            top += art_side+18
        center = (top+bottom)/2
        idx, gap = display_line(lines, position, starts) if lines else (-1, None)
        pulse = beat(lines[idx], position, s['animation_speed'])*s['pop_amount'] if idx >= 0 and motion else 0.
        A.NSColor.clearColor().set()
        A.NSRectFillUsingOperation(bounds, A.NSCompositingOperationClear)
        A.NSGraphicsContext.saveGraphicsState()
        A.NSGraphicsContext.currentContext().setImageInterpolation_(A.NSImageInterpolationHigh)
        rounded(((0, 0), (w, h)), 26).addClip()
        if s['style'] != 'Typography' and not bare:
            color('#10121E', opacity).set(); A.NSRectFill(bounds)
            if s['style'] == 'Aurora' and opacity > 0:
                drift = ((now-self.preview_epoch) if preview else position)*.16 if motion else 0
                for dx, dy, tint in [(0, 0, accent), (.55, .22, self.second_rgb)]:
                    x = w*(dx-.1+.08*math.sin(drift+dx*4))
                    y = h*(dy-.5+.14*math.cos(drift+dy*3))
                    # Each sung word briefly brightens and widens the glow.
                    gradient = A.NSGradient.alloc().initWithStartingColor_endingColor_(color(tint, min(1., opacity*(.42+.3*pulse))), color(tint, 0))
                    gradient.drawFromCenter_radius_toCenter_radius_options_((x+w*.45, y+h*.7), 0, (x+w*.45, y+h*.7), w*(.65+.05*pulse), 0)
            color('#FFFFFF', .09*opacity).setStroke()
            border = rounded(((.5, .5), (w-1, h-1)), 26); border.setLineWidth_(1); border.stroke()
        if not track.title:
            text('Play a song in Apple Music', ((20, center-18), (w-40, 44)), min(28, s['font_size']), accent, centered=True)
            if not bare:
                text(owner.status, ((20, center+28), (w-40, 35)), 12, alpha=.6, centered=True)
            A.NSGraphicsContext.restoreGraphicsState()
            return
        if s['show_clock'] and not bare:
            stamp = datetime.now()
            text(stamp.strftime('%I:%M').lstrip('0'), ((20, 16), (w-40, 56)), 44, s['text_color'], centered=True)
            text(stamp.strftime('%A, %B %d'), ((20, 75), (w-40, 24)), 13, alpha=.55, centered=True)
        if header and not s['show_clock']:
            x = 26
            if s['show_art'] and not album_card:
                self.artwork(owner, ((24, 22), (42, 42)), 9, accent, 23, .143, now, motion, preview)
                x = 78
            nudge = (1-appear)*6
            text(track.title, ((x, 23+nudge), (w-x-92, 23)), 14, alpha=appear, weight=A.NSFontWeightSemibold)
            text(track.artist, ((x, 45+nudge), (w-x-92, 20)), 12, alpha=.5*appear)
            if preview:
                text('PREVIEW', ((w-92, 28), (68, 20)), 9, accent, centered=True)
            elif track.playing:
                self.equalizer(w-46, 47, accent, elapsed, motion)
            else:
                text('PAUSED', ((w-92, 28), (68, 20)), 9, accent, centered=True)
        if album_card:
            self.artwork(owner, (((w-art_side)/2, art_y), (art_side, art_side)), 16, accent, art_side*.4, .25, now, motion, preview)
        if self.key != track.key or idx != self.index:
            self.scrolling = self.key == track.key and idx == self.index+1 and abs(position-self.last_position) < 1
            self.line_start = now
            self.ribbon_x = None
            self.key, self.index = track.key, idx
        self.last_position = position
        transition = min(1, (now-self.line_start)*s['animation_speed']/.38)
        ease = 1-(1-transition)**3
        slide = (1-ease) if self.scrolling and s['scroll_lines'] and motion else 0
        # A new line fades up quickly; its first word is never fully hidden.
        arrive = .35+.65*min(1., transition*2.5) if motion else 1.
        A.NSGraphicsContext.saveGraphicsState()
        A.NSBezierPath.bezierPathWithRect_(((14, top-4), (w-28, bottom-top+8))).addClip()
        if idx >= 0 and lines[idx].text:
            current = lines[idx]
            mode = s['lyric_style']
            if mode == 'Kinetic Word':
                previous_word = lines[idx-1].words[-1] if idx > 0 and lines[idx-1].words else None
                self.kinetic(current, position, s, w, top, bottom, accent, previous_word)
            elif mode == 'Spotlight':
                self.spotlight(current, position, s, w, center, accent)
            elif mode == 'Ribbon':
                self.ribbon(current, position, s, w, center, accent, dt)
            elif mode == 'Scroll':
                spread = max(34, min(s['font_size']*s['line_spacing']*1.2, (bottom-top)/3))
                for j in range(max(0, idx-2), min(len(lines), idx+3)):
                    distance = j-idx+slide
                    if j != idx and not s['show_neighbors']:
                        continue
                    size = s['font_size'] if j == idx else s['font_size']*.56
                    if j == idx:
                        self.phrase(current, position, s, w, center+distance*spread, accent, top, bottom, 'Pop', max_size=min(size, spread*.65), opacity=arrive)
                    else:
                        text(lines[j].text, ((28, center+distance*spread-size*.6), (w-56, size*1.5)), size, s['text_color'], s['context_opacity']*s['text_opacity'], face=s['font'], centered=True)
            else:
                block_height = self.phrase(current, position, s, w, center+slide*48, accent, top, bottom, mode, opacity=arrive)
                if s['show_neighbors']:
                    previous = lines[idx-1].text if idx > 0 else ''
                    following = lines[idx+1].text if idx+1 < len(lines) else ''
                    for value, y in [(previous, center-block_height/2-32+slide*48), (following, center+block_height/2+12+slide*48)]:
                        text(value, ((26, y), (w-52, 24)), min(15, s['font_size']*.45), s['text_color'], s['context_opacity']*s['text_opacity'], face=s['font'], centered=True)
        elif lines and gap and gap[1] is not None and gap[1] > gap[0]:
            # An instrumental break: three dots fill as the next line approaches.
            fade = smoothstep((position-gap[0])/.3)*smoothstep((gap[1]-position)/.3) if motion else 1.
            self.dots(w/2, center, accent, s['text_opacity']*fade, position, (position-gap[0])/(gap[1]-gap[0]), 6., motion)
        elif lines:
            text('♪', ((24, center-20), (w-48, 48)), 32, accent, s['text_opacity'], centered=True, face=s['font'])
        else:
            loading = owner.loading and not preview
            message = 'Finding the words…' if loading else source or 'No synced lyrics found'
            text(message, ((24, center-20), (w-48, 48)), 18, accent, s['text_opacity'], centered=True, face=s['font'])
            if loading and motion:
                self.dots(w/2, center+26, accent, s['text_opacity']*.8, now, None, 3.5, True)
        A.NSGraphicsContext.restoreGraphicsState()
        if footer:
            if s['show_source']:
                label = 'PREVIEW / SAMPLE WORDS' if preview else 'APPLE MUSIC / '+('WORD SYNC' if (source == 'Word-synced lyrics' or 'exact word' in source) else 'ESTIMATED WORDS')
                text(label, ((26, h-36), (w-120, 16)), 9, alpha=.4)
            if s['show_time']:
                shown = max(0, elapsed)
                text(f'{int(shown)//60}:{int(shown)%60:02}', ((w-78, h-37), (50, 18)), 10, alpha=.6, centered=True)
        if progress:
            color('#FFFFFF', .12).set(); rounded(((26, h-16), (w-52, 3)), 1.5).fill()
            if track.duration > 0:
                filled = (w-52)*max(0., min(1., elapsed/track.duration))
                color(accent, .85).set(); rounded(((26, h-16), (filled, 3)), 1.5).fill()
                color(accent, 1).set(); A.NSBezierPath.bezierPathWithOvalInRect_(((26+filled-3.5, h-18), (7, 7))).fill()
        A.NSGraphicsContext.restoreGraphicsState()

    def artwork(self, owner, rect, radius, accent, glyph, inset, now, motion, preview):
        # Artwork fades in over its placeholder instead of popping.
        (x, y), (side, _) = rect
        art = None if preview else owner.art
        fade = smoothstep((now-getattr(owner, 'art_at', 0))/.5) if motion else 1.
        A.NSGraphicsContext.saveGraphicsState()
        rounded(rect, radius).addClip()
        if not art or fade < 1:
            color(accent, .18).set(); A.NSRectFill(rect)
            text('♫', ((x, y+side*inset), (side, side*(1-inset))), glyph, accent, 1-fade if art else 1, centered=True)
        if art:
            art.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(rect, A.NSZeroRect, A.NSCompositingOperationSourceOver, fade, True, None)
        A.NSGraphicsContext.restoreGraphicsState()

    def equalizer(self, x, baseline, tint, clock, motion):
        # Four small bars that move while music plays.
        for i in range(4):
            level = .25+.75*abs(math.sin(clock*(3.1+i*1.37)+i*1.9)) if motion else (.5, .9, .65, .4)[i]
            height = 3+13*level
            color(tint, .9).set()
            rounded(((x+i*5.5, baseline-height), (3, height)), 1.5).fill()

    def dots(self, cx, cy, tint, alpha, clock, progress, radius, motion):
        for i in range(3):
            wave = .5+.5*math.sin(clock*4.2-i*.9) if motion else .5
            lit = wave if progress is None else smoothstep(progress*3-i)
            r = radius*(.82+.18*wave)
            y = cy-(radius*.9*wave if progress is None else 0)
            color(tint, alpha*(.28+.72*lit)).set()
            A.NSBezierPath.bezierPathWithOvalInRect_(((cx+(i-1)*radius*3.4-r, y-r), (2*r, 2*r))).fill()

    def phrase(self, line, position, s, w, center, accent, top, bottom, mode, max_size=None, opacity=1.):
        size, row_height, rows, widths = fit_phrase(tuple(word.text for word in line.words),
            max_size or s['font_size'], s['font'], w, bottom-top, s['show_neighbors'],
            mode, s['ransom_chaos'], s['line_spacing'])
        height = len(rows)*row_height
        for ri, (row, width) in enumerate(zip(rows, widths)):
            x = align_x(width, w-80, s['alignment'], 40)
            for index, slot, image in row:
                word = line.words[index]
                self.word(word, position, s, x+slot/2, center-height/2+(ri+.5)*row_height, slot-size*.25, size, accent, mode, image, index, opacity)
                x += slot
        return height

    def word(self, word, position, s, x, y, width, size, accent, mode, image=None, index=0, opacity=1.):
        highlight, scale, alpha, entered, lift = word_motion(position, word.start, word.end,
            s['animation_speed'], s['pop_amount'], s['motion'])
        alpha *= s['text_opacity'] * opacity
        if mode == 'Typewriter':
            if entered <= 0:
                return
            alpha *= entered
        if isinstance(image, tuple):
            image = paper_word(*image)[0]
        if mode == 'Wave' and s['motion']:
            y += math.sin(position*3.5+index*.7)*size*.13
        y -= size*lift
        A.NSGraphicsContext.saveGraphicsState()
        transform = A.NSAffineTransform.transform(); transform.translateXBy_yBy_(x, y); transform.scaleBy_(scale); transform.concat()
        if image:
            iw, ih = image.size()
            if highlight > .001:
                color(accent, .22*s['text_opacity']*highlight*opacity).set(); rounded(((-iw/2-3, -size*.66), (iw+6, size*1.32)), 5).fill()
            image.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(((-iw/2, -ih/2), (iw, ih)), A.NSZeroRect, A.NSCompositingOperationSourceOver, alpha, True, None)
        else:
            if highlight > .001 and mode == 'Pop':
                color(accent, .22*s['text_opacity']*highlight*opacity).set(); rounded(((-width/2-5, -size*.6), (width+10, size*1.22)), 8).fill()
            attrs = {A.NSFontAttributeName: font(size, s['font'], A.NSFontWeightSemibold), A.NSForegroundColorAttributeName: color(s['text_color'], alpha).blendedColorWithFraction_ofColor_(highlight, color(accent, alpha))}
            if mode == 'Neon' and highlight > .001:
                attrs[A.NSShadowAttributeName] = glow(accent, .8*highlight*opacity, 9*(.5+s['glow']))
            F.NSString.stringWithString_(word.text.strip()).drawAtPoint_withAttributes_((-width/2, -size*.65), attrs)
        A.NSGraphicsContext.restoreGraphicsState()

    def kinetic(self, line, position, s, w, top, bottom, accent, previous_word=None):
        # One large word; independent X/Y scaling provides the stretchy fit in the reference.
        index = next((i for i, word in enumerate(line.words) if word.start <= position < word.end), None)
        if index is None:
            index = next((i-1 for i, word in enumerate(line.words) if word.start > position), len(line.words)-1)
        if index < 0:
            return
        word = line.words[index]
        center = (top+bottom)/2
        room = (bottom-top)*(.55 if s['show_neighbors'] else .84)
        speed, amount, motion = s['animation_speed'], s['pop_amount'], s['motion']
        age = max(0., position-word.start)
        # The word springs in: it grows past its size and settles, stretching
        # while it moves, with a slight lean that alternates word to word.
        alpha, scale, stretch, tilt, rise = kinetic_pose(age, max(.025, word.end-word.start), speed, amount, motion)
        headroom = min(1., 1.06/kinetic_peak(amount)) if motion else 1.
        travel = 10+30*amount
        lean = min(3.5, 9*amount)*(1 if index % 2 else -1)
        breathe = 1+.04*amount*math.sin(age*5.5)*(1-math.exp(-age*3)) if motion else 1.
        held = settle(position, word.end) if motion else 1.
        def draw(item, fade, across, upward, shift, degrees, halo):
            value = item.text.strip()
            if not value or fade < .001:
                return None
            base = 100.
            fnt = font(base, s['font'], A.NSFontWeightHeavy)
            width = measure_heavy(value, base, s['font'])
            sx, sy = (w-72)/max(1, width), room/(base*.9)
            uniform = min(sx, sy)
            fill = s['stretch_fill']
            sx = (uniform+(sx-uniform)*fill)*headroom
            sy = (uniform+(sy-uniform)*fill)*headroom
            A.NSGraphicsContext.saveGraphicsState()
            transform = A.NSAffineTransform.transform(); transform.translateXBy_yBy_(w/2, center+shift)
            if degrees:
                transform.rotateByDegrees_(degrees)
            transform.scaleXBy_yBy_(sx*across, sy*upward); transform.concat()
            attrs = {A.NSFontAttributeName: fnt, A.NSForegroundColorAttributeName: color(accent, fade*s['text_opacity'])}
            if halo > .01:
                attrs[A.NSShadowAttributeName] = glow(accent, halo, 6+18*s['glow'])
            F.NSString.stringWithString_(value).drawAtPoint_withAttributes_((-width/2, -base*.64), attrs)
            A.NSGraphicsContext.restoreGraphicsState()
            return width*sx/2, base*.9*sy/2
        previous_word = line.words[index-1] if index > 0 else previous_word
        if previous_word and alpha < 1 and 0 <= word.start-previous_word.end < 2:
            # The outgoing word puffs up and drifts away as it fades, starting
            # from the brightness it had settled to so nothing jumps.
            grow = 1+.25*amount*alpha
            draw(previous_word, (1-alpha)*settle(position, previous_word.end), grow, grow, -travel*.8*alpha, 0, 0)
        halo = s['glow']*(.35+.65*math.exp(-age*5*speed))*alpha*held if motion else s['glow']*.35
        extent = draw(word, alpha*held, scale*(1-stretch)*breathe, scale*(1+stretch)*breathe, travel*rise, lean*tilt, halo)
        if extent and motion and s['sparks']:
            self.sparks(word, age, w/2, center, extent[0], extent[1], accent, amount, speed, s['text_opacity'])
        if s['show_neighbors']:
            previous = line.words[index-1].text.strip() if index > 0 else ''
            following = line.words[index+1].text.strip() if index+1 < len(line.words) else ''
            for value, y in [(previous, top+4), (following, bottom-28)]:
                text(value, ((24, y), (w-48, 28)), 22, s['text_color'], s['context_opacity'], centered=True, weight=A.NSFontWeightBold)

    def sparks(self, word, age, cx, cy, rx, ry, tint, amount, speed, alpha):
        # A short burst from the edge of each new word. Seeded by the word, so
        # the same burst is redrawn every frame without storing particles.
        life = .6/speed
        if age >= life or amount <= 0:
            return
        t = age/life
        travel = 1-(1-t)**3
        rng = random.Random(zlib.crc32(word.text.encode('utf-8')) ^ int(word.start*1000))
        bright = tuple(c+(1-c)*.45 for c in tint)
        for _ in range(int(6+16*amount)):
            angle = rng.uniform(0, 2*math.pi)
            reach = rng.uniform(16, 52)*(.5+amount)*travel
            size = rng.uniform(1.6, 4.4)*(1-.55*t)
            color(bright, rng.uniform(.45, 1.)*(1-t)**1.5*alpha).set()
            x = cx+math.cos(angle)*(rx*.92+reach)
            y = cy+math.sin(angle)*(ry*.8+reach)+10*t*t
            A.NSBezierPath.bezierPathWithOvalInRect_(((x-size/2, y-size/2), (size, size))).fill()

    def spotlight(self, line, position, s, w, center, accent):
        index = next((i for i, word in enumerate(line.words) if word.start <= position < word.end), None)
        if index is None:
            index = next((i for i, word in enumerate(line.words) if word.start > position), len(line.words)-1)
        if index < 0:
            return
        word = line.words[index]
        blend = smoothstep((position-word.start)/min(.14/s['animation_speed'], max(.03, (word.end-word.start)*.4))) if s['motion'] else 1.
        def draw(item, yy, opacity):
            size = s['font_size']*1.7
            while measure(item.text.strip(), size, s['font']) > w-110 and size > 16:
                size -= 2
            width = measure(item.text.strip(), size, s['font'])
            self.word(item, position, s, w/2, yy, width, size, accent, 'Neon', opacity=opacity)
            return size
        if index > 0 and blend < 1 and word.start-line.words[index-1].end < .2:
            draw(line.words[index-1], center-12*blend, 1-blend)
        size = draw(word, center+12*(1-blend), blend)
        if s['show_neighbors']:
            for value, y in [(' '.join(t.text.strip() for t in line.words[max(0, index-3):index]), center-size*.9-25),
                             (' '.join(t.text.strip() for t in line.words[index+1:index+4]), center+size*.8)]:
                text(value, ((26, y), (w-52, 24)), 16, s['text_color'], s['context_opacity']*s['text_opacity'], centered=True)

    def ribbon(self, line, position, s, w, center, accent, dt):
        size = s['font_size']*1.15
        widths = [measure(word.text.strip(), size, s['font'])+size*.45 for word in line.words]
        centers, cursor = [], 0
        for width in widths:
            centers.append(cursor+width/2); cursor += width
        index = next((i for i, word in enumerate(line.words) if word.start <= position < word.end), None)
        if index is None:
            index = next((i for i, word in enumerate(line.words) if word.start > position), len(widths)-1)
        if index < 0:
            return
        target = w/2-centers[index]
        if self.ribbon_x is None or not s['motion']:
            self.ribbon_x = target
        else:
            self.ribbon_x += (target-self.ribbon_x)*(1-math.exp(-dt*18*s['animation_speed']))
        for i, (word, width, x) in enumerate(zip(line.words, widths, centers)):
            xx = x+self.ribbon_x
            if -width < xx < w+width:
                self.word(word, position, s, xx, center, width-size*.45, size, accent, 'Pop', index=i)
