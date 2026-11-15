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
from .lockscreen import LockScreenSpace
from .palette import album_palette, DEFAULT_ACCENT, DEFAULT_SECONDARY
from .placement import snap_origin

PRESETS = ('Custom', 'Wide lyrics', 'Square lyrics', 'Compact strip', 'Album card', 'Clock + lyrics')
# Menu item tags; the status-bar and right-click menus are kept in step by tag.
TAG_TRACK, TAG_LOCK, TAG_VISIBLE, TAG_BARE, TAG_OFFSET = 1, 2, 3, 4, 5


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
            # Hold Option while dragging to place the widget freely.
            if not event.modifierFlags() & A.NSEventModifierFlagOption:
                self.owner.snapPosition()
            self.owner.savePosition()

    def rightMouseDown_(self, event):
        self.owner.syncMenus()
        A.NSMenu.popUpContextMenu_withEvent_forView_(self.owner.context_menu, event, self)

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
        self.ai_status = ''
        self.ai_busy = False
        self.art = None
        self.art_at = 0
        self.accent = DEFAULT_ACCENT
        self.secondary = DEFAULT_SECONDARY
        self.previewing = False
        self.animate_until = 0
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix='lookup')
        self.pending = []
        self.hidden = False
        session = Q.CGSessionCopyCurrentDictionary() or {}
        self.locked = bool(session.get('CGSSessionScreenIsLocked', False))
        self.sleeping = False
        self.render_active = threading.Event()
        self.control_paused = False
        self.redraw = True
        self.display_link = None
        self.frame_fallback = None
        self.lock_panel = None
        self.lock_view = None
        self.lock_space = LockScreenSpace()
        self.assets_needed = False
        self.dirty_at = None
        self.last_draw = 0
        self.preferences = None
        self.controls = {}
        self.makePanel()
        self.makeMenu()
        self.timer = F.NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(.25, self, 'tick:', None, True)
        F.NSRunLoop.mainRunLoop().addTimer_forMode_(self.timer, F.NSRunLoopCommonModes)
        self.timer.setTolerance_(.04)
        self.bindFrames(self.view)
        F.NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(self, 'screensChanged:', A.NSApplicationDidChangeScreenParametersNotification, None)
        center = F.NSDistributedNotificationCenter.defaultCenter()
        center.addObserver_selector_name_object_(self, 'screenLocked:', 'com.apple.screenIsLocked', None)
        center.addObserver_selector_name_object_(self, 'screenUnlocked:', 'com.apple.screenIsUnlocked', None)
        # Music announces play, pause and track changes; read it at once instead of waiting for the next poll.
        center.addObserver_selector_name_object_(self, 'musicChanged:', 'com.apple.Music.playerInfo', None)
        workspace = A.NSWorkspace.sharedWorkspace().notificationCenter()
        workspace.addObserver_selector_name_object_(self, 'screenSleep:', A.NSWorkspaceScreensDidSleepNotification, None)
        workspace.addObserver_selector_name_object_(self, 'screenWake:', A.NSWorkspaceScreensDidWakeNotification, None)
        F.NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(self, 'visibilityChanged:', A.NSWindowDidChangeOcclusionStateNotification, None)
        if self.locked:
            self.screenLocked_(None)
        self.refreshVisibility()
        threading.Thread(target=self.poll, daemon=True, name='AppleMusic').start()
        if not self.locked:
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
        self.view.renderer = Renderer()
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
        self.menu = self.buildMenu()
        self.context_menu = self.buildMenu()
        self.status_item.setMenu_(self.menu)
        self.syncMenus()

    @objc.python_method
    def buildMenu(self):
        menu = A.NSMenu.alloc().init()
        def add(parent, title, action, key='', tag=0):
            item = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
            item.setTarget_(self)
            item.setTag_(tag)
            parent.addItem_(item)
            return item
        add(menu, 'Cadence · Apple Music', None, '', TAG_TRACK)
        menu.addItem_(A.NSMenuItem.separatorItem())
        add(menu, 'Customize…', 'customize:', ',')
        for title, action, options in [('Lyric style', 'pickStyle:', LYRIC_STYLES), ('Widget layout', 'pickPreset:', PRESETS)]:
            submenu = A.NSMenu.alloc().init()
            for option in options:
                add(submenu, option, action)
            add(menu, title, None).setSubmenu_(submenu)
        add(menu, 'Lyrics only', 'lyricsOnly:', '', TAG_BARE)
        menu.addItem_(A.NSMenuItem.separatorItem())
        add(menu, 'Refresh lyrics', 'refresh:', 'r')
        add(menu, 'Lyrics earlier (+100 ms)', 'earlier:')
        add(menu, 'Lyrics later (−100 ms)', 'later:')
        add(menu, 'Timing offset', None, '', TAG_OFFSET)
        menu.addItem_(A.NSMenuItem.separatorItem())
        add(menu, 'Lock position', 'toggleLock:', '', TAG_LOCK)
        add(menu, 'Center widget', 'center:')
        add(menu, 'Show widget', 'toggleVisible:', '', TAG_VISIBLE)
        menu.addItem_(A.NSMenuItem.separatorItem())
        add(menu, 'Open Apple Music', 'openMusic:')
        add(menu, 'Quit Cadence', 'quit:', 'q')
        menu.setDelegate_(self)
        return menu

    @objc.python_method
    def syncMenus(self):
        """Checkmarks and labels always show the current state in both menus."""
        if not hasattr(self, 'context_menu'):
            return
        s, track = self.settings, self.playback.track
        title = (track.title+' — '+track.artist)[:90] if track.title else 'Cadence · Nothing playing'
        for menu in (self.menu, self.context_menu):
            for item in menu.itemArray():
                tag = item.tag()
                if tag == TAG_TRACK:
                    item.setTitle_(title)
                elif tag == TAG_LOCK:
                    item.setState_(int(s['locked']))
                elif tag == TAG_VISIBLE:
                    item.setState_(int(not self.hidden))
                elif tag == TAG_BARE:
                    item.setState_(int(s['layout'] == 'Lyrics only'))
                elif tag == TAG_OFFSET:
                    item.setTitle_(f"Timing offset {s['offset']:+.2f} s")
                submenu = item.submenu()
                if submenu is not None:
                    for child in submenu.itemArray():
                        child.setState_(int(str(child.title()) in (s['lyric_style'], s['widget_preset'])))

    def menuNeedsUpdate_(self, menu):
        self.syncMenus()

    @objc.python_method
    def snapPosition(self):
        screen = self.panel.screen() or A.NSScreen.mainScreen()
        area, frame = screen.visibleFrame(), self.panel.frame()
        origin = (frame.origin.x, frame.origin.y)
        size = (frame.size.width, frame.size.height)
        target = snap_origin(origin, size, (area.origin.x, area.origin.y, area.size.width, area.size.height))
        if target != origin:
            self.panel.setFrame_display_animate_((target, size), True, True)

    @objc.python_method
    def touched(self):
        """A setting changed: keep animating briefly so colour and layout changes ease in."""
        self.redraw = True
        self.animate_until = time.monotonic()+1.5
        self.syncMenus()
        self.view.setNeedsDisplay_(True)

    @objc.python_method
    def poll(self):
        with objc.autorelease_pool():
            reader = MusicReader()
            while not self.stop.is_set():
                self.render_active.wait()
                if self.stop.is_set():
                    return
                try:
                    with objc.autorelease_pool():
                        self.events.put(('track', reader.read()))
                except Exception as exc:
                    self.events.put(('error', str(exc)))
                self.wake.wait(.35)
                self.wake.clear()

    @objc.python_method
    def requestAssets(self):
        if not self.render_active.is_set():
            self.assets_needed = True
            return
        self.assets_needed = False
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

    @objc.python_method
    def drain(self):
        """Apply queued results. Runs every frame, so a pause, seek or new song shows at once."""
        changed = lively = False
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == 'track':
                track = event[1]
                lively = lively or track.playing != self.playback.track.playing
                if self.playback.update(track):
                    self.art = None
                    self.requestAssets()
                    self.syncMenus()
                    lively = True
                    logging.info('Track changed; generation=%d', self.playback.generation)
                self.status = 'Play a song in Apple Music'
                changed = True
            elif kind == 'error':
                self.status = event[1]
                if self.playback.update(Track()):
                    self.art = None
                    self.loading = False
                    self.syncMenus()
                changed = True
            elif kind == 'ai':
                self.ai_busy = False
                if event[1] == self.playback.generation:
                    result, error = event[2]
                    if result and 'exact word' not in self.playback.source and self.playback.source != 'Word-synced lyrics':
                        self.playback.accept(event[1], *result)
                    self.ai_status = error or 'Apple Intelligence lyric match checked'
                    changed = True
            elif event[1] == self.playback.generation:
                if kind in ('lyrics', 'words'):
                    self.pending_lyrics = max(0, self.pending_lyrics-1)
                    if event[2][0] or kind == 'lyrics':
                        self.playback.accept(event[1], *event[2])
                    self.loading = not self.playback.lines and self.pending_lyrics > 0
                    logging.info('Lyrics ready; lines=%d; %s', len(self.playback.lines), self.playback.source)
                elif kind == 'art':
                    self.showArtwork(event[2])
                changed = lively = True
        if changed:
            self.redraw = True
        if lively:
            self.animate_until = time.monotonic()+1.5
        return changed

    @objc.python_method
    def showArtwork(self, data):
        """The previous song's colours stay until this arrives, then glide to the new ones."""
        self.accent, self.secondary = DEFAULT_ACCENT, DEFAULT_SECONDARY
        if not data:
            return
        payload = F.NSData.dataWithBytes_length_(data, len(data))
        self.art = A.NSImage.alloc().initWithData_(payload)
        self.art_at = time.monotonic()
        bitmap = A.NSBitmapImageRep.imageRepWithData_(payload)
        if not bitmap:
            return
        samples = []
        wide, high = bitmap.pixelsWide(), bitmap.pixelsHigh()
        space = A.NSColorSpace.deviceRGBColorSpace()
        for column in range(10):
            for row in range(10):
                c = bitmap.colorAtX_y_(int(wide*(column+.5)/10), int(high*(row+.5)/10))
                c = c.colorUsingColorSpace_(space) if c else None
                if c:
                    samples.append((c.redComponent(), c.greenComponent(), c.blueComponent()))
        self.accent, self.secondary = album_palette(samples)

    def musicChanged_(self, note):
        self.wake.set()

    def tick_(self, timer):
        self.drain()
        now = time.monotonic()
        if self.dirty_at is not None and now-self.dirty_at > .4:
            self.settings.save()
            self.dirty_at = None
        self.refreshVisibility()
        previewing = bool(self.preferences and self.preferences.isVisible() and not self.playback.track.title)
        if previewing != self.previewing:
            self.previewing = previewing
            self.redraw = True
        if self.render_active.is_set():
            if self.assets_needed:
                self.requestAssets()
            view = self.lock_view if self.locked else self.view
            if view and hasattr(view, 'renderer'):
                view.renderer.prewarm(self, view.bounds())
        if self.preferences and self.preferences.isVisible():
            connection = ('Connected to Apple Music · '+self.playback.track.title) if self.playback.track.title else self.status
            if self.previewing:
                connection = 'Nothing playing · the widget is previewing your settings'
            self.connection_label.setStringValue_(connection if self.render_active.is_set() else 'Widget paused while covered · show your desktop to resume')
            self.source_label.setStringValue_(self.playback.source or 'Play a song to check lyric timing')
            self.ai_label.setStringValue_(self.ai_status or 'Uses the on-device Apple Intelligence model only on request.')

    @objc.python_method
    def bindFrames(self, view):
        if self.display_link:
            self.display_link.invalidate(); self.display_link = None
        if self.frame_fallback:
            self.frame_fallback.invalidate(); self.frame_fallback = None
        if view is None:
            return
        try:
            self.display_link = view.displayLinkWithTarget_selector_(self, 'frame:')
            self.display_link.setPreferredFrameRateRange_(Q.CAFrameRateRangeMake(60, 60, 60))
            self.display_link.addToRunLoop_forMode_(F.NSRunLoop.mainRunLoop(), F.NSRunLoopCommonModes)
            logging.info('Rendering synchronized to display at up to 60 fps')
        except (AttributeError, TypeError):
            self.frame_fallback = F.NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(1/60, self, 'frame:', None, True)
            F.NSRunLoop.mainRunLoop().addTimer_forMode_(self.frame_fallback, F.NSRunLoopCommonModes)
            logging.info('Display link unavailable; using 60 Hz fallback')

    @objc.python_method
    def refreshVisibility(self):
        if not hasattr(self, 'panel'):
            return
        window = self.lock_panel if self.locked else self.panel
        visible = bool(window and window.isVisible() and (self.locked or window.occlusionState() & A.NSWindowOcclusionStateVisible))
        active = visible and not self.hidden and not self.sleeping
        was_active = self.render_active.is_set()
        if active:
            self.render_active.set()
            if not was_active:
                self.redraw = True
        else:
            self.render_active.clear()
        if hasattr(self, 'timer') and active == self.control_paused:
            self.timer.setFireDate_(F.NSDate.date() if active else F.NSDate.distantFuture())
            self.control_paused = not active
        if was_active != active:
            logging.info('Widget visibility: %s', 'active' if active else 'idle; rendering and playback polling suspended')
        if not active and hasattr(self, 'connection_label'):
            self.connection_label.setStringValue_('Widget paused while covered · show your desktop to resume')
        if self.display_link:
            self.display_link.setPaused_(not active)
        if self.frame_fallback:
            self.frame_fallback.setFireDate_(F.NSDate.date() if active else F.NSDate.distantFuture())

    def visibilityChanged_(self, note):
        self.refreshVisibility()

    def frame_(self, link):
        if not self.render_active.is_set():
            return
        if not self.events.empty():
            self.drain()
        view = self.lock_view if self.locked else self.view
        preview = self.previewing and not self.locked
        if view and (self.redraw or self.playback.track.playing or preview or time.monotonic() < self.animate_until):
            view.setNeedsDisplay_(True)
            view.displayIfNeeded()
            self.redraw = False

    @objc.python_method
    def makeLockPanel(self):
        if self.lock_panel is not None:
            return True
        if not self.lock_space.available:
            return False
        screen = self.panel.screen() or A.NSScreen.mainScreen()
        frame = screen.frame()
        width = min(self.settings['width'], frame.size.width-48)
        height = min(self.settings['height'], frame.size.height*.35)
        rect = ((frame.origin.x+(frame.size.width-width)/2, frame.origin.y+42), (width, height))
        panel = DesktopPanel.alloc().initWithContentRect_styleMask_backing_defer_(rect, A.NSWindowStyleMaskBorderless | A.NSWindowStyleMaskNonactivatingPanel, A.NSBackingStoreBuffered, False)
        panel.setOpaque_(False); panel.setBackgroundColor_(A.NSColor.clearColor())
        panel.setHasShadow_(False); panel.setHidesOnDeactivate_(False)
        panel.setFloatingPanel_(True); panel.setIgnoresMouseEvents_(True)
        panel.setLevel_(Q.CGWindowLevelForKey(Q.kCGScreenSaverWindowLevelKey))
        panel.setCollectionBehavior_(A.NSWindowCollectionBehaviorCanJoinAllSpaces | A.NSWindowCollectionBehaviorStationary | A.NSWindowCollectionBehaviorFullScreenAuxiliary | A.NSWindowCollectionBehaviorIgnoresCycle)
        panel.setTitle_('Cadence Lock Screen Lyrics')
        view = LyricView.alloc().initWithFrame_(((0, 0), (width, height)))
        view.owner = self; view.renderer = Renderer()
        view.setAutoresizingMask_(A.NSViewWidthSizable | A.NSViewHeightSizable)
        panel.setContentView_(view)
        if not self.lock_space.attach(panel):
            panel.orderOut_(None)
            return False
        self.lock_panel, self.lock_view = panel, view
        return True

    @objc.python_method
    def dropLockPanel(self):
        if self.lock_panel:
            self.lock_panel.orderOut_(None)
        self.lock_space.close()
        self.lock_panel = self.lock_view = None

    def screenLocked_(self, note):
        self.locked = True
        self.panel.orderOut_(None)
        if self.settings['lock_screen'] and not self.hidden and self.makeLockPanel():
            self.lock_panel.orderFrontRegardless()
            self.bindFrames(self.lock_view)
        else:
            self.bindFrames(None)
        self.redraw = True
        self.refreshVisibility()

    def screenUnlocked_(self, note):
        self.locked = False
        self.dropLockPanel()
        if not self.hidden:
            self.panel.orderFrontRegardless()
        self.bindFrames(self.view)
        self.redraw = True
        self.refreshVisibility()

    def screenSleep_(self, note):
        self.sleeping = True; self.refreshVisibility()

    def screenWake_(self, note):
        self.sleeping = False; self.redraw = True; self.refreshVisibility()

    def screensChanged_(self, note):
        self.restorePosition()
        self.savePosition()
        if self.locked:
            self.dropLockPanel(); self.screenLocked_(None)

    def center_(self, sender):
        self.settings['x'] = self.settings['y'] = None
        self.restorePosition()
        self.savePosition()

    def toggleVisible_(self, sender):
        self.hidden = not self.hidden
        if self.locked:
            self.dropLockPanel(); self.screenLocked_(None)
        elif self.hidden:
            self.panel.orderOut_(None)
        else:
            self.panel.orderFrontRegardless()
        self.refreshVisibility()
        self.syncMenus()

    def toggleLock_(self, sender):
        self.settings['locked'] = not self.settings['locked']
        self.panel.setIgnoresMouseEvents_(self.settings['locked'])
        self.settings.save()
        if 'locked' in self.controls:
            self.controls['locked'].setState_(int(self.settings['locked']))
        self.syncMenus()

    def pickStyle_(self, sender):
        self.settings['lyric_style'] = str(sender.title())
        if 'lyric_style' in self.controls:
            self.controls['lyric_style'].selectItemWithTitle_(self.settings['lyric_style'])
        self.settings.save(); self.touched()

    def pickPreset_(self, sender):
        if self.preferences is None:
            self.buildPreferences()
        self.settings['widget_preset'] = str(sender.title())
        self.controls['widget_preset'].selectItemWithTitle_(self.settings['widget_preset'])
        self.applyPreset()
        self.settings.save(); self.touched()

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
        self.wake.set()
        self.render_active.set()
        self.bindFrames(None)
        self.dropLockPanel()
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
        self.refreshVisibility()

    @objc.python_method
    def buildPreferences(self):
        self.preferences = A.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(((0, 0), (550, 710)), A.NSWindowStyleMaskTitled | A.NSWindowStyleMaskClosable | A.NSWindowStyleMaskMiniaturizable, A.NSBackingStoreBuffered, False)
        self.preferences.setReleasedWhenClosed_(False)
        self.preferences.setTitle_('Cadence · Customize')
        self.preferences.center()
        content = self.preferences.contentView()
        self.label(content, 'Give every word a little life.', 26, 654, 500, 23).setFont_(A.NSFont.boldSystemFontOfSize_(22))
        self.connection_label = self.label(content, self.status, 26, 615, 500, 11)
        self.label(content, 'Desktop lyrics, exactly your way. Changes show on the widget as you make them.', 26, 586, 500, 12).setTextColor_(A.NSColor.secondaryLabelColor())
        tabs = A.NSTabView.alloc().initWithFrame_(((18, 48), (514, 530)))
        content.addSubview_(tabs)
        panes = {}
        for name in ('Effects', 'Layout', 'Colors', 'Timing', 'Widgets'):
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
        def checkbox(parent, key, title, y, tip=None):
            control = A.NSButton.checkboxWithTitle_target_action_(title, self, 'changed:')
            control.setFrame_(((16, y), (450, 22))); control.setState_(int(self.settings[key]))
            if tip:
                control.setToolTip_(tip)
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
        self.controls['font'].setToolTip_('Ransom Note uses its own collage of mixed typefaces.')
        for key, title, y in [('font_size', 'Lyric size', 330), ('pop_amount', 'Pop strength', 296), ('glow', 'Glow', 262), ('animation_speed', 'Animation speed', 228), ('line_spacing', 'Line spacing', 194), ('ransom_chaos', 'Cutout variation', 160), ('stretch_fill', 'Stretch to fill', 126)]:
            slider(effects, key, title, y)
        self.controls['pop_amount'].setToolTip_('How far each word springs past its size as it is sung.')
        self.controls['glow'].setToolTip_('Soft light around the word being sung, in Kinetic Word, Spotlight and Neon.')
        checkbox(effects, 'motion', 'Animate words and background', 94)
        checkbox(effects, 'sparks', 'Sparks on each new word (Kinetic Word)', 70, 'A short burst from the edge of each word. Scales with Pop strength.')
        checkbox(effects, 'scroll_lines', 'Scroll smoothly between lyric lines', 46)
        checkbox(effects, 'show_neighbors', 'Show surrounding lyrics', 22)
        layout = panes['Layout']
        popup(layout, 'layout', 'Display', ['Full widget', 'Lyrics only'], 450)
        popup(layout, 'style', 'Backdrop', ['Aurora', 'Glass', 'Typography'], 410)
        slider(layout, 'width', 'Width', 360); slider(layout, 'height', 'Height', 320)
        for key, title, y in [('show_title', 'Song title and artist', 266), ('show_art', 'Album artwork (with song title)', 234), ('show_progress', 'Progress bar', 202), ('show_time', 'Elapsed time', 170), ('show_source', 'Apple Music / timing label', 138), ('lock_screen', 'Show lyrics on the lock screen', 104), ('locked', 'Lock position — click through the widget', 72)]:
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
        ai_button = A.NSButton.buttonWithTitle_target_action_('Find a better lyric match with Apple Intelligence', self, 'refineAI:')
        ai_button.setFrame_(((16, 64), (450, 32))); timing.addSubview_(ai_button)
        self.ai_label = self.label(timing, self.ai_status, 16, 24, 465, 10)
        widgets = panes['Widgets']
        popup(widgets, 'widget_preset', 'Widget layout', list(PRESETS), 450)
        self.label(widgets, 'Presets resize this movable desktop widget.', 16, 398, 465, 12)
        self.label(widgets, 'Wide / Square: one large word that stretches to fit.', 16, 356, 465, 12)
        self.label(widgets, 'Compact strip: scrolling lyrics in a small horizontal card.', 16, 322, 465, 12)
        self.label(widgets, 'Album card: artwork with the current word underneath.', 16, 288, 465, 12)
        self.label(widgets, 'Clock + lyrics: a clock above the active word.', 16, 254, 465, 12)
        self.label(widgets, 'Hidden widgets pause animation and Apple Music polling.', 16, 194, 465, 12)
        self.label(widgets, 'Network and AI work starts only while the widget is visible.', 16, 164, 465, 12)
        self.label(content, 'Drag to move · snaps to edges (hold ⌥ to place freely) · right-click for the menu', 26, 15, 500, 11).setTextColor_(A.NSColor.secondaryLabelColor())

    def refineAI_(self, sender):
        if self.ai_busy:
            return
        if 'exact word' in self.playback.source or self.playback.source == 'Word-synced lyrics':
            self.ai_status = 'Exact word timestamps are already available.'
            return
        if not self.render_active.is_set() or not self.playback.track.key:
            self.ai_status = 'Show the lyric widget and load a song first.'
            return
        from .ai_matching import refine
        self.ai_status = 'Apple Intelligence is checking the song match…'
        self.ai_busy = True
        generation, track = self.playback.generation, self.playback.track
        future = self.pool.submit(refine, track, self.render_active)
        def done(result):
            try:
                self.events.put(('ai', generation, (result.result(), '')))
            except Exception as exc:
                self.events.put(('ai', generation, (None, str(exc))))
        future.add_done_callback(done)

    @objc.python_method
    def applyPreset(self):
        name = self.settings['widget_preset']
        presets = {'Wide lyrics': (680, 340, 'Kinetic Word'), 'Square lyrics': (380, 380, 'Kinetic Word'),
                   'Compact strip': (560, 180, 'Ribbon'), 'Album card': (380, 520, 'Kinetic Word'),
                   'Clock + lyrics': (480, 500, 'Kinetic Word')}
        if name not in presets:
            return
        width, height, effect = presets[name]
        self.settings.update(width=width, height=height, lyric_style=effect, layout='Full widget',
            show_clock=name == 'Clock + lyrics', show_title=name == 'Album card', show_art=True,
            show_progress=False, show_time=False, show_source=False, show_neighbors=False)
        for key in ('width', 'height'):
            self.controls[key].setDoubleValue_(self.settings[key])
            self.controls[key+'_value'].setStringValue_(self.formatValue(key))
        for key in ('lyric_style', 'layout'):
            self.controls[key].selectItemWithTitle_(self.settings[key])
        for key in ('show_title', 'show_art', 'show_progress', 'show_time', 'show_source', 'show_neighbors'):
            self.controls[key].setState_(int(self.settings[key]))
        self.panel.setContentSize_((width, height))
        self.restorePosition(); self.savePosition()

    @objc.python_method
    def setOffset(self, value):
        self.settings['offset'] = max(-5, min(5, round(value, 2)))
        if 'offset' in self.controls:
            self.controls['offset'].setDoubleValue_(self.settings['offset'])
            self.controls['offset_value'].setStringValue_(self.formatValue('offset'))
        self.settings.save(); self.touched()

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
        self.settings.save(); self.touched()

    @objc.python_method
    def formatValue(self, key):
        value = self.settings[key]
        return f'{value:+.2f}' if key == 'offset' else f'{value:.0%}' if key in ('opacity', 'text_opacity', 'context_opacity', 'pop_amount', 'ransom_chaos', 'stretch_fill', 'glow') else f'{value:.1f}×' if key in ('animation_speed', 'line_spacing') else str(int(value))

    def changed_(self, sender):
        key = next((k for k, v in self.controls.items() if v == sender), None)
        if key in ('style', 'font', 'lyric_style', 'alignment', 'layout', 'widget_preset'):
            self.settings[key] = str(sender.titleOfSelectedItem())
        elif key in ('locked', 'auto_color', 'motion', 'show_art', 'show_title', 'show_progress', 'show_time', 'show_source', 'show_neighbors', 'scroll_lines', 'lock_screen', 'sparks'):
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
        if key == 'widget_preset':
            self.applyPreset()
        self.panel.setIgnoresMouseEvents_(self.settings['locked'])
        if key in ('width', 'height'):
            self.panel.setContentSize_((self.settings['width'], self.settings['height']))
            self.savePosition()
        if key == 'lock_screen' and self.locked:
            self.dropLockPanel(); self.screenLocked_(None)
        self.dirty_at = time.monotonic()
        self.touched()


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
