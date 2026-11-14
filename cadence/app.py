"""Native AppKit UI. Desktop-level window, never a floating overlay."""
import concurrent.futures
import logging
import queue
import threading
import time

import objc
import AppKit as A
import Foundation as F
import Quartz as Q
from .core import Playback, Track
from .music import MusicReader
from .providers import lyrics, word_lyrics, artwork
from .settings import Settings, SUPPORT, LYRIC_STYLES, RANGES
from .visuals import Renderer, color


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
        if not hasattr(self, 'renderer'):
            self.renderer = Renderer()
        self.renderer.paint(self.owner, self.bounds())


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
        for title, action, key in [('Customize…', 'customize:', ','), ('Lock / unlock position', 'toggleLock:', ''), ('Center widget', 'center:', ''), ('Show / hide widget', 'toggleVisible:', ''), ('Refresh lyrics', 'refresh:', 'r'), ('Lyrics earlier (+100 ms)', 'earlier:', ''), ('Lyrics later (−100 ms)', 'later:', ''), ('Toggle lyrics only', 'lyricsOnly:', ''), ('Open Apple Music', 'openMusic:', ''), ('Quit Cadence', 'quit:', 'q')]:
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
                self.stop.wait(.35)

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
        self.pending_lyrics = 2
        for kind, fn in [('lyrics', lyrics), ('words', word_lyrics), ('art', artwork)]:
            future = self.pool.submit(fn, track)
            def done(result, kind=kind, generation=generation):
                if result.cancelled():
                    return
                try:
                    self.events.put((kind, generation, result.result()))
                except Exception:
                    logging.exception('Asset lookup failed')
                    self.events.put((kind, generation, ([], 'Lyrics unavailable · try Refresh') if kind in ('lyrics', 'words') else None))
            future.add_done_callback(done)
            self.pending.append(future)

    def tick_(self, timer):
        changed = False
        while not self.events.empty():
            event = self.events.get_nowait()
            kind = event[0]
            if kind == 'track':
                track = event[1]
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
                if kind in ('lyrics', 'words'):
                    self.pending_lyrics = max(0, self.pending_lyrics-1)
                    if event[2][0] or kind == 'lyrics':
                        self.playback.accept(event[1], *event[2])
                    self.loading = not self.playback.lines and self.pending_lyrics > 0
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
            self.source_label.setStringValue_(self.playback.source or 'Play a song to check lyric timing')

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
        self.preferences = A.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(((0, 0), (550, 710)), A.NSWindowStyleMaskTitled | A.NSWindowStyleMaskClosable | A.NSWindowStyleMaskMiniaturizable, A.NSBackingStoreBuffered, False)
        self.preferences.setReleasedWhenClosed_(False)
        self.preferences.setTitle_('Cadence · Customize')
        self.preferences.center()
        content = self.preferences.contentView()
        self.label(content, 'Give every word a little life.', 26, 654, 500, 23)
        self.connection_label = self.label(content, self.status, 26, 615, 500, 11)
        self.label(content, 'Desktop lyrics, exactly your way.', 26, 586, 500, 12)
        tabs = A.NSTabView.alloc().initWithFrame_(((18, 48), (514, 530)))
        content.addSubview_(tabs)
        panes = {}
        for name in ('Effects', 'Layout', 'Colors', 'Timing'):
            item = A.NSTabViewItem.alloc().initWithIdentifier_(name)
            item.setLabel_(name)
            pane = A.NSView.alloc().initWithFrame_(((0, 0), (480, 480)))
            item.setView_(pane); tabs.addTabViewItem_(item); panes[name] = pane
        def popup(parent, key, title, options, y):
            self.label(parent, title, 16, y, 160)
            control = A.NSPopUpButton.alloc().initWithFrame_pullsDown_(((184, y-2), (282, 28)), False)
            control.addItemsWithTitles_(options); control.selectItemWithTitle_(self.settings[key])
            control.setTarget_(self); control.setAction_('changed:')
            self.controls[key] = control; parent.addSubview_(control)
        def slider(parent, key, title, y):
            self.label(parent, title, 16, y, 160)
            low, high = RANGES[key]
            control = A.NSSlider.sliderWithValue_minValue_maxValue_target_action_(self.settings[key], low, high, self, 'changed:')
            control.setFrame_(((184, y), (212, 22))); control.setContinuous_(True)
            self.controls[key] = control; parent.addSubview_(control)
            self.controls[key+'_value'] = self.label(parent, self.formatValue(key), 406, y, 66, 11)
        def checkbox(parent, key, title, y):
            control = A.NSButton.checkboxWithTitle_target_action_(title, self, 'changed:')
            control.setFrame_(((16, y), (450, 22))); control.setState_(int(self.settings[key]))
            self.controls[key] = control; parent.addSubview_(control)
        def well(parent, key, title, y):
            self.label(parent, title, 16, y)
            control = A.NSColorWell.alloc().initWithFrame_(((184, y-1), (70, 28)))
            control.setColor_(color(self.settings[key])); control.setTarget_(self); control.setAction_('changed:')
            self.controls[key] = control; parent.addSubview_(control)
        effects = panes['Effects']
        popup(effects, 'lyric_style', 'Lyric style', list(LYRIC_STYLES), 450)
        popup(effects, 'font', 'Typeface', ['SF Rounded', 'SF Pro', 'Avenir Next', 'Helvetica Neue', 'Georgia', 'Courier'], 410)
        popup(effects, 'alignment', 'Alignment', ['Left', 'Center', 'Right'], 370)
        for key, title, y in [('font_size', 'Lyric size', 325), ('pop_amount', 'Pop strength', 285), ('animation_speed', 'Animation speed', 245), ('line_spacing', 'Line spacing', 205), ('ransom_chaos', 'Cutout variation', 165)]:
            slider(effects, key, title, y)
        checkbox(effects, 'motion', 'Animate words and background', 118)
        checkbox(effects, 'scroll_lines', 'Scroll smoothly between lyric lines', 86)
        checkbox(effects, 'show_neighbors', 'Show surrounding lyrics', 54)
        self.label(effects, 'Ransom Note uses its own collage of mixed typefaces.', 16, 14, 460, 11)
        layout = panes['Layout']
        popup(layout, 'layout', 'Display', ['Full widget', 'Lyrics only'], 450)
        popup(layout, 'style', 'Backdrop', ['Aurora', 'Glass', 'Typography'], 410)
        slider(layout, 'width', 'Width', 360); slider(layout, 'height', 'Height', 320)
        for key, title, y in [('show_title', 'Song title and artist', 266), ('show_art', 'Album artwork (with song title)', 234), ('show_progress', 'Progress bar', 202), ('show_time', 'Elapsed time', 170), ('show_source', 'Apple Music / timing label', 138), ('locked', 'Lock position — click through the widget', 88)]:
            checkbox(layout, key, title, y)
        self.label(layout, 'Lyrics only hides the backdrop, header, time and progress.', 16, 38, 460, 11)
        self.label(layout, 'Your individual choices return when you select Full widget.', 16, 16, 460, 11)
        colors = panes['Colors']
        for key, title, y in [('opacity', 'Backdrop opacity', 450), ('text_opacity', 'Lyric opacity', 410), ('context_opacity', 'Surrounding lyrics', 370)]:
            slider(colors, key, title, y)
        well(colors, 'accent', 'Active word / accent', 305)
        well(colors, 'text_color', 'Other words', 255)
        checkbox(colors, 'auto_color', 'Match accent to album artwork', 200)
        self.label(colors, 'Choosing a custom accent turns album color matching off.', 16, 144, 465, 11)
        self.label(colors, 'Paper cutouts keep their own colors; the accent lights up', 16, 108, 465, 11)
        self.label(colors, 'the word being sung.', 16, 86, 465, 11)
        timing = panes['Timing']
        self.source_label = self.label(timing, 'Play a song to check lyric timing', 16, 450, 460, 12)
        slider(timing, 'offset', 'Timing offset (sec)', 394)
        self.label(timing, 'Positive = earlier lyrics. Negative = later lyrics.', 16, 350, 460, 12)
        for title, action, x, width in [('Earlier +100 ms', 'earlier:', 16, 154), ('Later −100 ms', 'later:', 176, 154), ('Reset', 'resetTiming:', 336, 120)]:
            button = A.NSButton.buttonWithTitle_target_action_(title, self, action)
            button.setFrame_(((x, 297), (width, 32))); timing.addSubview_(button)
        for value, y in [('Start with +0.22 seconds, then adjust while listening.', 242),
                         ('Real word timestamps are preferred when available.', 204),
                         ('Otherwise word timing is estimated from synced lines.', 180),
                         ('An offset fixes consistent lag; it cannot fix every word', 142),
                         ('when a song has only line timestamps.', 118)]:
            self.label(timing, value, 16, y, 465, 12)
        self.label(content, 'Drag the widget to move it. Right-click it to customize.', 26, 15, 500, 11)

    @objc.python_method
    def setOffset(self, value):
        self.settings['offset'] = max(-5, min(5, round(value, 2)))
        if 'offset' in self.controls:
            self.controls['offset'].setDoubleValue_(self.settings['offset'])
            self.controls['offset_value'].setStringValue_(self.formatValue('offset'))
        self.settings.save(); self.view.setNeedsDisplay_(True)

    def earlier_(self, sender):
        self.setOffset(self.settings['offset']+.1)

    def later_(self, sender):
        self.setOffset(self.settings['offset']-.1)

    def resetTiming_(self, sender):
        self.setOffset(.22)

    def lyricsOnly_(self, sender):
        self.settings['layout'] = 'Full widget' if self.settings['layout'] == 'Lyrics only' else 'Lyrics only'
        if 'layout' in self.controls:
            self.controls['layout'].selectItemWithTitle_(self.settings['layout'])
        self.settings.save(); self.view.setNeedsDisplay_(True)

    @objc.python_method
    def formatValue(self, key):
        value = self.settings[key]
        return f'{value:+.2f}' if key == 'offset' else f'{value:.0%}' if key in ('opacity', 'text_opacity', 'context_opacity', 'pop_amount', 'ransom_chaos') else f'{value:.1f}×' if key in ('animation_speed', 'line_spacing') else str(int(value))

    def changed_(self, sender):
        key = next((k for k, v in self.controls.items() if v == sender), None)
        if key in ('style', 'font', 'lyric_style', 'alignment', 'layout'):
            self.settings[key] = str(sender.titleOfSelectedItem())
        elif key in ('locked', 'auto_color', 'motion', 'show_art', 'show_title', 'show_progress', 'show_time', 'show_source', 'show_neighbors', 'scroll_lines'):
            self.settings[key] = bool(sender.state())
        elif key in ('accent', 'text_color'):
            c = sender.color().colorUsingColorSpace_(A.NSColorSpace.deviceRGBColorSpace())
            self.settings[key] = '#'+''.join(f'{round(v*255):02X}' for v in [c.redComponent(), c.greenComponent(), c.blueComponent()])
            if key == 'accent':
                self.settings['auto_color'] = False
                self.controls['auto_color'].setState_(0)
        elif key in RANGES:
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
