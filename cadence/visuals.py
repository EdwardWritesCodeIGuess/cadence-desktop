"""Native kinetic typography and procedural paper cutouts. No downloaded assets."""
import math
import random
import hashlib
import time
from datetime import datetime
from functools import lru_cache
import AppKit as A
import Foundation as F
from .core import active_line
from .motion import word_motion, smoothstep

def color(hex_value, alpha=1):
    try:
        value = int(hex_value.lstrip('#'), 16)
    except ValueError:
        value = 0xA8BAFF
    return A.NSColor.colorWithCalibratedRed_green_blue_alpha_(((value >> 16)&255)/255, ((value >> 8)&255)/255, (value&255)/255, alpha)


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


def text(value, rect, size=13, tint='#FFFFFF', alpha=1, face='SF Pro', centered=False, weight=A.NSFontWeightMedium):
    paragraph = A.NSMutableParagraphStyle.alloc().init()
    paragraph.setLineBreakMode_(A.NSLineBreakByTruncatingTail)
    paragraph.setAlignment_(A.NSTextAlignmentCenter if centered else A.NSTextAlignmentLeft)
    attrs = {A.NSFontAttributeName: font(size, face, weight), A.NSForegroundColorAttributeName: color(tint, alpha), A.NSParagraphStyleAttributeName: paragraph}
    F.NSString.stringWithString_(str(value)).drawInRect_withAttributes_(rect, attrs)


def rounded(rect, radius=20):
    return A.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius)


@lru_cache(maxsize=2048)
def measure(value, size, face):
    return F.NSString.stringWithString_(value).sizeWithAttributes_({A.NSFontAttributeName: font(size, face, A.NSFontWeightSemibold)}).width


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

    def prewarm(self, owner, bounds):
        s = owner.settings
        if s['lyric_style'] != 'Ransom Note' or not owner.playback.lines:
            return
        lines = owner.playback.lines
        idx = active_line(lines, owner.playback.position_at(time.monotonic())+s['offset'])+1
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
        track = owner.playback.track
        position = owner.playback.position_at(now)+s['offset']
        accent = owner.accent if s['auto_color'] else s['accent']
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
        A.NSColor.clearColor().set()
        A.NSRectFillUsingOperation(bounds, A.NSCompositingOperationClear)
        A.NSGraphicsContext.saveGraphicsState()
        A.NSGraphicsContext.currentContext().setImageInterpolation_(A.NSImageInterpolationHigh)
        rounded(((0, 0), (w, h)), 26).addClip()
        if s['style'] != 'Typography' and not bare:
            color('#10121E', opacity).set(); A.NSRectFill(bounds)
            if s['style'] == 'Aurora' and opacity > 0:
                phase = position*.16 if s['motion'] else 0
                for dx, dy, tint in [(0, 0, accent), (.55, .22, '#7355B8')]:
                    x = w*(dx-.1+.08*math.sin(phase+dx*4))
                    y = h*(dy-.5+.14*math.cos(phase+dy*3))
                    gradient = A.NSGradient.alloc().initWithStartingColor_endingColor_(color(tint, opacity*.42), color(tint, 0))
                    gradient.drawFromCenter_radius_toCenter_radius_options_((x+w*.45, y+h*.7), 0, (x+w*.45, y+h*.7), w*.65, 0)
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
                A.NSGraphicsContext.saveGraphicsState(); rounded(((24, 22), (42, 42)), 9).addClip()
                if owner.art:
                    owner.art.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(((24, 22), (42, 42)), A.NSZeroRect, A.NSCompositingOperationSourceOver, 1, True, None)
                else:
                    color(accent, .18).set(); A.NSRectFill(((24, 22), (42, 42)))
                    text('♫', ((24, 28), (42, 30)), 23, accent, centered=True)
                A.NSGraphicsContext.restoreGraphicsState(); x = 78
            text(track.title, ((x, 23), (w-x-92, 23)), 14, weight=A.NSFontWeightSemibold)
            text(track.artist, ((x, 45), (w-x-92, 20)), 12, alpha=.5)
            text('PLAYING' if track.playing else 'PAUSED', ((w-92, 28), (68, 20)), 9, accent, centered=True)
        if album_card:
            A.NSGraphicsContext.saveGraphicsState()
            artwork_rect = (((w-art_side)/2, art_y), (art_side, art_side))
            rounded(artwork_rect, 16).addClip()
            if owner.art:
                owner.art.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(artwork_rect, A.NSZeroRect, A.NSCompositingOperationSourceOver, 1, True, None)
            else:
                color(accent, .2).set(); A.NSRectFill(artwork_rect)
                text('♫', (((w-art_side)/2, art_y+art_side*.25), (art_side, art_side*.6)), art_side*.4, accent, centered=True)
            A.NSGraphicsContext.restoreGraphicsState()
        lines = owner.playback.lines
        idx = active_line(lines, position)
        if self.key != track.key or idx != self.index:
            self.scrolling = self.key == track.key and idx == self.index+1 and abs(position-self.last_position) < 1
            self.line_start = now
            self.ribbon_x = None
            self.key, self.index = track.key, idx
        self.last_position = position
        transition = min(1, (now-self.line_start)*s['animation_speed']/.38)
        ease = 1-(1-transition)**3
        slide = (1-ease) if self.scrolling and s['scroll_lines'] and s['motion'] else 0
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
                gap = max(34, min(s['font_size']*s['line_spacing']*1.2, (bottom-top)/3))
                for j in range(max(0, idx-2), min(len(lines), idx+3)):
                    distance = j-idx+slide
                    if j != idx and not s['show_neighbors']:
                        continue
                    size = s['font_size'] if j == idx else s['font_size']*.56
                    if j == idx:
                        self.phrase(current, position, s, w, center+distance*gap, accent, top, bottom, 'Pop', max_size=min(size, gap*.65))
                    else:
                        text(lines[j].text, ((28, center+distance*gap-size*.6), (w-56, size*1.5)), size, s['text_color'], s['context_opacity']*s['text_opacity'], face=s['font'], centered=True)
            else:
                block_height = self.phrase(current, position, s, w, center+slide*48, accent, top, bottom, mode)
                if s['show_neighbors']:
                    previous = lines[idx-1].text if idx > 0 else ''
                    following = lines[idx+1].text if idx+1 < len(lines) else ''
                    for value, y in [(previous, center-block_height/2-32+slide*48), (following, center+block_height/2+12+slide*48)]:
                        text(value, ((26, y), (w-52, 24)), min(15, s['font_size']*.45), s['text_color'], s['context_opacity']*s['text_opacity'], face=s['font'], centered=True)
        else:
            message = '♪' if lines else ('Finding the words…' if owner.loading else owner.playback.source or 'No synced lyrics found')
            text(message, ((24, center-20), (w-48, 48)), 32 if lines else 18, accent, s['text_opacity'], centered=True, face=s['font'])
        A.NSGraphicsContext.restoreGraphicsState()
        if footer:
            if s['show_source']:
                text('APPLE MUSIC / '+('WORD SYNC' if (owner.playback.source == 'Word-synced lyrics' or 'exact word' in owner.playback.source) else 'ESTIMATED WORDS'), ((26, h-36), (w-120, 16)), 9, alpha=.4)
            if s['show_time']:
                shown = max(0, owner.playback.position_at(now))
                text(f'{int(shown)//60}:{int(shown)%60:02}', ((w-78, h-37), (50, 18)), 10, alpha=.6, centered=True)
        if progress:
            color('#FFFFFF', .12).set(); rounded(((26, h-15), (w-52, 2)), 1).fill()
            if track.duration > 0:
                color(accent, .8).set(); rounded(((26, h-15), ((w-52)*min(1, owner.playback.position_at(now)/track.duration), 2)), 1).fill()
        A.NSGraphicsContext.restoreGraphicsState()

    def phrase(self, line, position, s, w, center, accent, top, bottom, mode, max_size=None):
        size, row_height, rows, widths = fit_phrase(tuple(word.text for word in line.words),
            max_size or s['font_size'], s['font'], w, bottom-top, s['show_neighbors'],
            mode, s['ransom_chaos'], s['line_spacing'])
        height = len(rows)*row_height
        for ri, (row, width) in enumerate(zip(rows, widths)):
            x = align_x(width, w-80, s['alignment'], 40)
            for index, slot, image in row:
                word = line.words[index]
                self.word(word, position, s, x+slot/2, center-height/2+(ri+.5)*row_height, slot-size*.25, size, accent, mode, image, index)
                x += slot
        return height

    def word(self, word, position, s, x, y, width, size, accent, mode, image=None, index=0, opacity=1.):
        highlight, scale, alpha, entered = word_motion(position, word.start, word.end,
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
                shadow = A.NSShadow.alloc().init(); shadow.setShadowColor_(color(accent, .8*highlight*opacity)); shadow.setShadowBlurRadius_(9); shadow.setShadowOffset_((0, 0)); attrs[A.NSShadowAttributeName] = shadow
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
        duration = max(.025, word.end-word.start)
        age = max(0., position-word.start)
        transition = smoothstep(age/min(.15/s['animation_speed'], duration*.45)) if s['motion'] else 1.
        def draw(item, fade, vertical):
            value = item.text.strip()
            if not value or fade < .001:
                return
            base = 100.
            fnt = font(base, s['font'], A.NSFontWeightHeavy)
            width = F.NSString.stringWithString_(value).sizeWithAttributes_({A.NSFontAttributeName: fnt}).width
            sx, sy = (w-72)/max(1, width), room/(base*.9)
            uniform = min(sx, sy)
            fill = s['stretch_fill']
            sx = uniform+(sx-uniform)*fill
            sy = uniform+(sy-uniform)*fill
            bounce = 1-.34*s['pop_amount']*math.exp(-age*16*s['animation_speed'])*math.cos(age*22*s['animation_speed']) if s['motion'] else 1.
            A.NSGraphicsContext.saveGraphicsState()
            transform = A.NSAffineTransform.transform(); transform.translateXBy_yBy_(w/2, center+vertical)
            transform.scaleXBy_yBy_(sx*bounce, sy*(2-bounce)); transform.concat()
            attrs = {A.NSFontAttributeName: fnt, A.NSForegroundColorAttributeName: color(accent, fade*s['text_opacity'])}
            F.NSString.stringWithString_(value).drawAtPoint_withAttributes_((-width/2, -base*.64), attrs)
            A.NSGraphicsContext.restoreGraphicsState()
        previous_word = line.words[index-1] if index > 0 else previous_word
        if previous_word and transition < 1 and 0 <= word.start-previous_word.end < .2:
            draw(previous_word, 1-transition, -18*transition)
        draw(word, transition, 18*(1-transition))
        if s['show_neighbors']:
            previous = line.words[index-1].text.strip() if index > 0 else ''
            following = line.words[index+1].text.strip() if index+1 < len(line.words) else ''
            for value, y in [(previous, top+4), (following, bottom-28)]:
                text(value, ((24, y), (w-48, 28)), 22, s['text_color'], s['context_opacity'], centered=True, weight=A.NSFontWeightBold)

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
