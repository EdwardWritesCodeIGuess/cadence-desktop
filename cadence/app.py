"""Native AppKit UI. Desktop-level window, never a floating overlay."""
import concurrent.futures
import logging
import math
import queue
import threading
import time
from pathlib import Path

import objc
import AppKit as A
import Foundation as F
import Quartz as Q
from .core import Playback, Track, active_line
from .music import MusicReader
from .providers import lyrics, artwork
from .settings import Settings, SUPPORT


def color(hex_value, alpha=1):
    try:
        value = int(hex_value.lstrip('#'), 16)
    except ValueError:
        value = 0xA8BAFF
    return A.NSColor.colorWithCalibratedRed_green_blue_alpha_(((value >> 16)&255)/255, ((value >> 8)&255)/255, (value&255)/255, alpha)


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


class DesktopPanel(A.NSPanel):
    def canBecomeKeyWindow(self):
        return False

    def canBecomeMainWindow(self):
        return False


class LyricView(A.NSView):
    def isFlipped(self):
        return True

    def isOpaque(self):
        return False

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        if not self.owner.settings['locked']:
            self.window().performWindowDragWithEvent_(event)
            self.owner.savePosition()

    def rightMouseDown_(self, event):
        self.owner.customize_(None)

    def drawRect_(self, rect):
        owner = self.owner
        s = owner.settings
        bounds = self.bounds()
        w, h = bounds.size.width, bounds.size.height
        A.NSColor.clearColor().set()
        A.NSRectFillUsingOperation(bounds, A.NSCompositingOperationClear)
        accent = owner.accent if s['auto_color'] else s['accent']
        now = time.monotonic()
        opacity = s['opacity']
        A.NSGraphicsContext.saveGraphicsState()
        rounded(((0, 0), (w, h)), 26).addClip()
        if s['style'] != 'Typography':
            color('#10121E', opacity).set()
            A.NSRectFill(bounds)
            if s['style'] == 'Aurora' and opacity > 0:
                phase = now*.16 if s['motion'] and owner.playback.track.playing else 0
                for dx, dy, tint in [(0, 0, accent), (.55, .22, '#7355B8')]:
                    x = w * (dx-.1 + .08*math.sin(phase+dx*4))
                    y = h * (dy-.5 + .14*math.cos(phase+dy*3))
                    gradient = A.NSGradient.alloc().initWithStartingColor_endingColor_(color(tint, opacity*.42), color(tint, 0))
                    gradient.drawFromCenter_radius_toCenter_radius_options_((x+w*.45, y+h*.7), 0, (x+w*.45, y+h*.7), w*.65, 0)
            color('#FFFFFF', .09*opacity).setStroke()
            border = rounded(((.5, .5), (w-1, h-1)), 26)
            border.setLineWidth_(1)
            border.stroke()
        A.NSGraphicsContext.restoreGraphicsState()
        track = owner.playback.track
        if not track.title:
            text('C A D E N C E', ((28, 27), (w-56, 22)), 11, accent, weight=A.NSFontWeightSemibold)
            text('Your music, at home.', ((28, h/2-30), (w-56, 50)), min(34, s['font_size']), face=s['font'], centered=True)
            text(owner.status, ((28, h/2+25), (w-56, 42)), 13, alpha=.65, centered=True)
            text('Drag to place  ·  Right-click to customize', ((20, h-32), (w-40, 20)), 11, alpha=.45, centered=True)
            return
        title_x = 26
        if s['show_art']:
            if owner.art:
                A.NSGraphicsContext.saveGraphicsState()
                rounded(((24, 22), (42, 42)), 9).addClip()
                owner.art.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(((24, 22), (42, 42)), A.NSZeroRect, A.NSCompositingOperationSourceOver, 1, True, None)
                A.NSGraphicsContext.restoreGraphicsState()
            else:
                color(accent, .18).set()
                rounded(((24, 22), (42, 42)), 9).fill()
                text('♫', ((24, 28), (42, 30)), 23, accent, centered=True)
            title_x = 78
        text(track.title, ((title_x, 23), (w-title_x-92, 23)), 14, weight=A.NSFontWeightSemibold)
        text(track.artist, ((title_x, 45), (w-title_x-92, 20)), 12, alpha=.5)
        text('PLAYING' if track.playing else 'PAUSED', ((w-92, 28), (68, 20)), 9, accent, centered=True)
        position = track.position_at(now) + s['offset']
        lines = owner.playback.lines
        idx = active_line(lines, position)
        middle = 80 + (h-132)/2
        if idx >= 0 and lines[idx].text:
            current = lines[idx]
            previous = lines[idx-1].text if idx > 0 else ''
            following = lines[idx+1].text if idx+1 < len(lines) else ''
            # Fit the active phrase into at most three rows, downscaling long phrases.
            size = s['font_size']
            tokens = current.words
            while True:
                fnt = font(size, s['font'], A.NSFontWeightSemibold)
                measures = [F.NSString.stringWithString_(word.text).sizeWithAttributes_({A.NSFontAttributeName: fnt}).width for word in tokens]
                rows, widths = [[]], [0.]
                for word, width in zip(tokens, measures):
                    if rows[-1] and widths[-1]+width > w-64:
                        rows.append([]); widths.append(0.)
                    rows[-1].append((word, width)); widths[-1] += width
                if len(rows)*size*1.23 <= h-170 and max(widths, default=0) <= w-56 or size <= 16:
                    break
                size -= 2
            row_height = size*1.23
            top = middle-len(rows)*row_height/2
            text(previous, ((30, max(73, top-31)), (w-60, 23)), min(14, size*.5), alpha=.28, centered=True, face=s['font'])
            for row_idx, (row, row_width) in enumerate(zip(rows, widths)):
                x = (w-row_width)/2
                for word, width in row:
                    active = word.start <= position < word.end
                    passed = position >= word.end
                    tint = accent if active else '#FFFFFF'
                    alpha = 1 if active else (.85 if passed else .38)
                    rise = -2 if active and s['motion'] else 0
                    attrs = {A.NSFontAttributeName: fnt, A.NSForegroundColorAttributeName: color(tint, alpha)}
                    F.NSString.stringWithString_(word.text).drawAtPoint_withAttributes_((x, top+row_idx*row_height+rise), attrs)
                    x += width
            text(following, ((30, min(h-67, top+len(rows)*row_height+7)), (w-60, 23)), min(14, size*.5), alpha=.32, centered=True, face=s['font'])
        else:
            message = '♪' if lines else ('Finding the words…' if owner.loading else owner.playback.source or 'No synced lyrics found')
            text(message, ((24, middle-20), (w-48, 48)), 32 if lines else 20, accent, centered=True, face=s['font'])
        text('APPLE MUSIC  /  '+('WORD SYNC' if 'Word-synced' in owner.playback.source else 'LYRICS'), ((26, h-36), (w-120, 16)), 9, alpha=.4)
        duration = track.duration
        shown = max(0, track.position_at(now))
        text(f'{int(shown)//60}:{int(shown)%60:02}', ((w-78, h-37), (50, 18)), 10, alpha=.6, centered=True)
        color('#FFFFFF', .12).set()
        rounded(((26, h-15), (w-52, 2)), 1).fill()
        if duration > 0:
            color(accent, .8).set()
            rounded(((26, h-15), ((w-52)*min(1, shown/duration), 2)), 1).fill()


class Controller(A.NSObject):
    def applicationDidFinishLaunching_(self, note):
        self.settings = Settings()
        self.playback = Playback()
        self.status = 'Play a song in Apple Music'
        self.loading = False
        self.art = None
        self.accent = '#A8BAFF'
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix='lookup')
        self.pending = []
        self.hidden = False
        self.locked = False
        self.dirty_at = None
        self.last_draw = 0
        self.preferences = None
        self.controls = {}
        self.makePanel()
        self.makeMenu()
        self.timer = F.NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(1/30, self, 'tick:', None, True)
        F.NSRunLoop.mainRunLoop().addTimer_forMode_(self.timer, F.NSRunLoopCommonModes)
        self.timer.setTolerance_(.008)
        F.NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(self, 'screensChanged:', A.NSApplicationDidChangeScreenParametersNotification, None)
        center = F.NSDistributedNotificationCenter.defaultCenter()
        center.addObserver_selector_name_object_(self, 'screenLocked:', 'com.apple.screenIsLocked', None)
        center.addObserver_selector_name_object_(self, 'screenUnlocked:', 'com.apple.screenIsUnlocked', None)
        threading.Thread(target=self.poll, daemon=True, name='AppleMusic').start()
        self.customize_(None)
        logging.info('Cadence started; desktop window level=%d, normal=%d', self.panel.level(), A.NSNormalWindowLevel)

    @objc.python_method
    def makePanel(self):
        s = self.settings
        self.panel = DesktopPanel.alloc().initWithContentRect_styleMask_backing_defer_(((0, 0), (s['width'], s['height'])), A.NSWindowStyleMaskBorderless | A.NSWindowStyleMaskNonactivatingPanel, A.NSBackingStoreBuffered, False)
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(A.NSColor.clearColor())
        self.panel.setHasShadow_(False)
        self.panel.setHidesOnDeactivate_(False)
        self.panel.setFloatingPanel_(False)
        self.panel.setLevel_(Q.CGWindowLevelForKey(Q.kCGDesktopIconWindowLevelKey)+1)
        self.panel.setCollectionBehavior_(A.NSWindowCollectionBehaviorCanJoinAllSpaces | A.NSWindowCollectionBehaviorStationary | A.NSWindowCollectionBehaviorIgnoresCycle)
        self.panel.setTitle_('Cadence Desktop Lyrics')
        self.panel.setIgnoresMouseEvents_(s['locked'])
        self.view = LyricView.alloc().initWithFrame_(((0, 0), (s['width'], s['height'])))
        self.view.owner = self
        self.view.setAutoresizingMask_(A.NSViewWidthSizable | A.NSViewHeightSizable)
        self.panel.setContentView_(self.view)
        self.restorePosition()
        self.panel.orderFrontRegardless()

    @objc.python_method
    def restorePosition(self):
        s = self.settings
        size = self.panel.frame().size
        origin = (s['x'], s['y']) if s['x'] is not None and s['y'] is not None else None
        if origin and not any(F.NSContainsRect(screen.visibleFrame(), (origin, size)) for screen in A.NSScreen.screens()):
            origin = None
        if origin is None:
            frame = A.NSScreen.mainScreen().visibleFrame()
            origin = (frame.origin.x+max(12, (frame.size.width-size.width)/2), frame.origin.y+50)
        self.panel.setFrameOrigin_(origin)

    @objc.python_method
    def savePosition(self):
        self.settings['x'], self.settings['y'] = self.panel.frame().origin
        self.settings.save()

    @objc.python_method
    def makeMenu(self):
        self.status_item = A.NSStatusBar.systemStatusBar().statusItemWithLength_(A.NSVariableStatusItemLength)
        image = A.NSImage.imageWithSystemSymbolName_accessibilityDescription_('waveform', 'Cadence')
        image.setTemplate_(True)
        self.status_item.button().setImage_(image)
        menu = A.NSMenu.alloc().init()
        self.track_item = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Cadence · Apple Music', None, '')
        menu.addItem_(self.track_item)
        for title, action, key in [('Customize…', 'customize:', ','), ('Lock / unlock position', 'toggleLock:', ''), ('Center widget', 'center:', ''), ('Show / hide widget', 'toggleVisible:', ''), ('Refresh lyrics', 'refresh:', 'r'), ('Open Apple Music', 'openMusic:', ''), ('Quit Cadence', 'quit:', 'q')]:
            item = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
            item.setTarget_(self)
            menu.addItem_(item)
        self.status_item.setMenu_(menu)

    @objc.python_method
    def poll(self):
        with objc.autorelease_pool():
            reader = MusicReader()
            while not self.stop.is_set():
                try:
                    with objc.autorelease_pool():
                        self.events.put(('track', reader.read()))
                except Exception as exc:
                    self.events.put(('error', str(exc)))
                self.stop.wait(.65)

    @objc.python_method
    def requestAssets(self):
        for future in self.pending:
            future.cancel()
        self.pending = []
        generation, track = self.playback.generation, self.playback.track
        if not track.key:
            self.loading = False
            return
        self.loading = True
        for kind, fn in [('lyrics', lyrics), ('art', artwork)]:
            future = self.pool.submit(fn, track)
            def done(result, kind=kind, generation=generation):
                if result.cancelled():
                    return
                try:
                    self.events.put((kind, generation, result.result()))
                except Exception:
                    logging.exception('Asset lookup failed')
                    self.events.put((kind, generation, ([], 'Lyrics unavailable · try Refresh') if kind == 'lyrics' else None))
            future.add_done_callback(done)
            self.pending.append(future)

    def tick_(self, timer):
        changed = False
        while not self.events.empty():
            event = self.events.get_nowait()
            kind = event[0]
            if kind == 'track':
                track = event[1]
                was_playing = self.playback.track.playing
                if self.playback.update(track):
                    self.art = None
                    self.accent = '#A8BAFF'
                    self.requestAssets()
                    logging.info('Track changed; generation=%d', self.playback.generation)
                self.status = 'Play a song in Apple Music'
                self.track_item.setTitle_((track.title+' — '+track.artist)[:90] if track.title else 'Cadence · Nothing playing')
                changed = True
            elif kind == 'error':
                self.status = event[1]
                if self.playback.update(Track()):
                    self.art = None
                    self.loading = False
                changed = True
            elif event[1] == self.playback.generation:
                if kind == 'lyrics':
                    self.playback.accept(event[1], *event[2])
                    self.loading = False
                    logging.info('Lyrics ready; lines=%d; %s', len(self.playback.lines), self.playback.source)
                elif kind == 'art' and event[2]:
                    self.art = A.NSImage.alloc().initWithData_(F.NSData.dataWithBytes_length_(event[2], len(event[2])))
                    bitmap = A.NSBitmapImageRep.imageRepWithData_(F.NSData.dataWithBytes_length_(event[2], len(event[2])))
                    if bitmap:
                        samples = []
                        for x, y in [(.2, .2), (.5, .5), (.8, .3), (.3, .8)]:
                            c = bitmap.colorAtX_y_(int(bitmap.pixelsWide()*x), int(bitmap.pixelsHigh()*y)).colorUsingColorSpace_(A.NSColorSpace.deviceRGBColorSpace())
                            if c:
                                rgb = [c.redComponent(), c.greenComponent(), c.blueComponent()]
                                samples.append(rgb)
                        if samples:
                            rgb = max(samples, key=lambda v: max(v)-min(v))
                            rgb = [.4+.6*v for v in rgb]
                            self.accent = '#'+''.join(f'{int(v*255):02X}' for v in rgb)
                changed = True
        now = time.monotonic()
        if self.dirty_at is not None and now-self.dirty_at > .4:
            self.settings.save()
            self.dirty_at = None
        visible = not self.hidden and not self.locked
        # Avoid rendering when macOS reports the desktop widget fully occluded.
        exposed = bool(self.panel.occlusionState() & A.NSWindowOcclusionStateVisible)
        if visible and exposed and (changed or self.playback.track.playing and now-self.last_draw >= 1/30):
            self.view.setNeedsDisplay_(True)
            self.last_draw = now
        if self.preferences and self.preferences.isVisible():
            self.connection_label.setStringValue_((('Connected to Apple Music · '+self.playback.track.title) if self.playback.track.title else self.status))

    def screenLocked_(self, note):
        self.locked = True
        self.panel.orderOut_(None)

    def screenUnlocked_(self, note):
        self.locked = False
        if not self.hidden:
            self.panel.orderFrontRegardless()

    def screensChanged_(self, note):
        self.restorePosition()
        self.savePosition()

    def center_(self, sender):
        self.settings['x'] = self.settings['y'] = None
        self.restorePosition()
        self.savePosition()

    def toggleVisible_(self, sender):
        self.hidden = not self.hidden
        if self.hidden or self.locked:
            self.panel.orderOut_(None)
        else:
            self.panel.orderFrontRegardless()

    def toggleLock_(self, sender):
        self.settings['locked'] = not self.settings['locked']
        self.panel.setIgnoresMouseEvents_(self.settings['locked'])
        self.settings.save()
        if 'locked' in self.controls:
            self.controls['locked'].setState_(int(self.settings['locked']))

    def refresh_(self, sender):
        self.playback.generation += 1
        self.playback.lines = []
        self.requestAssets()
        self.view.setNeedsDisplay_(True)

    def openMusic_(self, sender):
        A.NSWorkspace.sharedWorkspace().openURL_(F.NSURL.URLWithString_('music://'))

    def quit_(self, sender):
        A.NSApplication.sharedApplication().terminate_(None)

    def applicationShouldTerminate_(self, app):
        self.stop.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.savePosition()
        return A.NSTerminateNow

    def applicationShouldHandleReopen_hasVisibleWindows_(self, app, visible):
        self.customize_(None)
        return False

    @objc.python_method
    def label(self, parent, title, x, y, width=400, size=12):
        label = A.NSTextField.labelWithString_(title)
        label.setFrame_(((x, y), (width, 23)))
        label.setFont_(A.NSFont.systemFontOfSize_(size))
        parent.addSubview_(label)
        return label

    def customize_(self, sender):
        if self.preferences is None:
            self.buildPreferences()
        self.preferences.makeKeyAndOrderFront_(None)
        A.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    @objc.python_method
    def buildPreferences(self):
        self.preferences = A.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(((0, 0), (490, 650)), A.NSWindowStyleMaskTitled | A.NSWindowStyleMaskClosable | A.NSWindowStyleMaskMiniaturizable, A.NSBackingStoreBuffered, False)
        self.preferences.setReleasedWhenClosed_(False)
        self.preferences.setTitle_('Cadence · Customize')
        self.preferences.center()
        content = self.preferences.contentView()
        self.label(content, 'Make room for the music.', 28, 594, size=23)
        self.connection_label = self.label(content, self.status, 28, 560, 436, 11)
        self.label(content, 'Lives above your wallpaper, below your windows.', 28, 533, 436, 12)
        y = 486
        for key, title, options in [('style', 'Look', ['Aurora', 'Glass', 'Typography']), ('font', 'Typeface', ['SF Rounded', 'SF Pro', 'Avenir Next', 'Helvetica Neue', 'Georgia'])]:
            self.label(content, title, 28, y)
            control = A.NSPopUpButton.alloc().initWithFrame_pullsDown_(((180, y-2), (280, 28)), False)
            control.addItemsWithTitles_(options)
            control.selectItemWithTitle_(self.settings[key])
            control.setTarget_(self); control.setAction_('changed:')
            self.controls[key] = control
            content.addSubview_(control)
            y -= 39
        for key, title, low, high in [('width', 'Width', 360, 1000), ('height', 'Height', 220, 600), ('font_size', 'Lyric size', 20, 60), ('opacity', 'Backdrop opacity', 0, 1), ('offset', 'Timing offset (seconds)', -3, 3)]:
            self.label(content, title, 28, y, 160)
            control = A.NSSlider.sliderWithValue_minValue_maxValue_target_action_(self.settings[key], low, high, self, 'changed:')
            control.setFrame_(((180, y), (218, 22)))
            control.setContinuous_(True)
            self.controls[key] = control
            content.addSubview_(control)
            self.controls[key+'_value'] = self.label(content, self.formatValue(key), 407, y, 60, 11)
            y -= 35
        self.label(content, 'Custom accent', 28, y)
        well = A.NSColorWell.alloc().initWithFrame_(((180, y-1), (65, 25)))
        well.setColor_(color(self.settings['accent']))
        well.setTarget_(self); well.setAction_('changed:')
        self.controls['accent'] = well; content.addSubview_(well)
        y -= 37
        for key, title in [('auto_color', 'Match the album artwork'), ('motion', 'Animate the aurora and active words'), ('show_art', 'Show album cover'), ('locked', 'Lock position (click through the widget)')]:
            control = A.NSButton.checkboxWithTitle_target_action_(title, self, 'changed:')
            control.setFrame_(((28, y), (430, 22)))
            control.setState_(int(self.settings[key]))
            self.controls[key] = control; content.addSubview_(control)
            y -= 28
        self.label(content, 'Drag the widget to move it. Right-click it to return here.', 28, 33, 440, 11)
        self.label(content, 'Line-synced lyrics use estimated word timing.', 28, 12, 440, 10)

    @objc.python_method
    def formatValue(self, key):
        value = self.settings[key]
        return f'{value:+.1f}' if key == 'offset' else f'{value:.0%}' if key == 'opacity' else str(int(value))

    def changed_(self, sender):
        key = next((k for k, v in self.controls.items() if v == sender), None)
        if key in ('style', 'font'):
            self.settings[key] = str(sender.titleOfSelectedItem())
        elif key in ('locked', 'auto_color', 'motion', 'show_art'):
            self.settings[key] = bool(sender.state())
        elif key == 'accent':
            c = sender.color().colorUsingColorSpace_(A.NSColorSpace.deviceRGBColorSpace())
            self.settings[key] = '#'+''.join(f'{round(v*255):02X}' for v in [c.redComponent(), c.greenComponent(), c.blueComponent()])
            self.settings['auto_color'] = False
            self.controls['auto_color'].setState_(0)
        elif key in ('width', 'height', 'font_size', 'opacity', 'offset'):
            value = sender.doubleValue()
            self.settings[key] = int(value) if key in ('width', 'height', 'font_size') else value
            self.controls[key+'_value'].setStringValue_(self.formatValue(key))
        self.panel.setIgnoresMouseEvents_(self.settings['locked'])
        if key in ('width', 'height'):
            self.panel.setContentSize_((self.settings['width'], self.settings['height']))
            self.savePosition()
        self.dirty_at = time.monotonic()
        self.view.setNeedsDisplay_(True)


def run():
    SUPPORT.mkdir(parents=True, exist_ok=True)
    from logging.handlers import RotatingFileHandler
    logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(SUPPORT/'cadence.log', maxBytes=200000, backupCount=1, encoding='utf-8')], format='%(asctime)s %(message)s')
    app = A.NSApplication.sharedApplication()
    # A second launch should reuse the running app, including when invoked directly.
    running = A.NSRunningApplication.runningApplicationsWithBundleIdentifier_('com.edwardlink.cadence')
    if len(running) > 1:
        return
    app.setActivationPolicy_(A.NSApplicationActivationPolicyAccessory)
    app.setAppearance_(A.NSAppearance.appearanceNamed_(A.NSAppearanceNameDarkAqua))
    delegate = Controller.alloc().init()
    app.setDelegate_(delegate)
    app.run()
