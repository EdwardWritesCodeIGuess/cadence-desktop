"""Run on macOS: python tests/ui_smoke.py /absolute/scratch/directory.
Uses synthetic playback and an in-memory settings object; never controls Music.
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import objc
import AppKit as A
import Foundation as F
import cadence.app as ui
from cadence.settings import DEFAULTS, LYRIC_STYLES
from cadence.core import Track, parse_lrc

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
class MemorySettings(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
    def save(self):
        pass
ui.Settings = MemorySettings

class SmokeController(ui.Controller):
    @objc.python_method
    def poll(self):
        pass
    @objc.python_method
    def requestAssets(self):
        pass
    def finish_(self, timer):
        try:
            assert self.panel.level() < A.NSNormalWindowLevel
            assert not self.panel.isFloatingPanel()
            track = Track(title='Evening Light', artist='Cadence preview', identifier='test', duration=180,
                          position=5, playing=True, sampled_at=time.monotonic())
            self.playback.update(track)
            self.playback.accept(self.playback.generation, parse_lrc('[00:00]A quiet moment\n[00:04]Let the evening settle in\n[00:10]And the music carry on', 180), 'demo')
            self.settings['style'] = 'Aurora'
            from dataclasses import replace
            frame_times = []
            for style in LYRIC_STYLES:
                self.settings['lyric_style'] = style
                for frame in range(6):
                    self.playback.update(replace(track, position=4+frame*.22, sampled_at=time.monotonic()))
                    self.playback.clock.reset(self.playback.track)
                    started = time.perf_counter()
                    self.view.setNeedsDisplay_(True); self.view.display()
                    if frame > 0: frame_times.append((time.perf_counter()-started)*1000)
                bitmap = self.view.bitmapImageRepForCachingDisplayInRect_(self.view.bounds())
                self.view.cacheDisplayInRect_toBitmapImageRep_(self.view.bounds(), bitmap)
                bitmap.representationUsingType_properties_(A.NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(str(OUT/(style+'.png')), True)
            # Verify lyrics-only actually leaves header/footer/background transparent.
            self.settings['lyric_style'] = 'Ransom Note'
            self.lyricsOnly_(None)
            self.view.setNeedsDisplay_(True); self.view.display()
            bitmap = self.view.bitmapImageRepForCachingDisplayInRect_(self.view.bounds())
            self.view.cacheDisplayInRect_toBitmapImageRep_(self.view.bounds(), bitmap)
            assert bitmap.colorAtX_y_(10, 10).alphaComponent() == 0
            assert bitmap.colorAtX_y_(100, bitmap.pixelsHigh()-18).alphaComponent() == 0
            bitmap.representationUsingType_properties_(A.NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(str(OUT/'lyrics-only.png'), True)
            self.lyricsOnly_(None)
            self.settings['show_progress'] = False
            self.view.setNeedsDisplay_(True); self.view.display()
            self.view.cacheDisplayInRect_toBitmapImageRep_(self.view.bounds(), bitmap)
            bitmap.representationUsingType_properties_(A.NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(str(OUT/'no-progress.png'), True)
            before = self.settings['offset']
            self.earlier_(None); assert abs(self.settings['offset']-before-.1) < .001
            self.later_(None); assert abs(self.settings['offset']-before) < .001
            self.controls['width'].setDoubleValue_(760)
            self.changed_(self.controls['width'])
            assert self.panel.frame().size.width == 760
            self.panel.setFrameOrigin_((80, 100)); self.savePosition()
            assert self.settings['x'] == 80 and self.settings['y'] == 100
            self.toggleLock_(None); assert self.panel.ignoresMouseEvents()
            self.toggleLock_(None); assert not self.panel.ignoresMouseEvents()
            for preset, size in [('Wide lyrics', (680, 340)), ('Square lyrics', (380, 380)),
                                 ('Compact strip', (560, 180)), ('Album card', (380, 520)),
                                 ('Clock + lyrics', (480, 500))]:
                self.controls['widget_preset'].selectItemWithTitle_(preset)
                self.changed_(self.controls['widget_preset'])
                assert tuple(self.panel.frame().size) == size
                assert not self.settings['show_neighbors']
                self.view.setNeedsDisplay_(True); self.view.display()
                bitmap = self.view.bitmapImageRepForCachingDisplayInRect_(self.view.bounds())
                self.view.cacheDisplayInRect_toBitmapImageRep_(self.view.bounds(), bitmap)
                bitmap.representationUsingType_properties_(A.NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(str(OUT/(preset+'.png')), True)
            # A real opaque covering window must suspend the widget, without locking the Mac.
            cover = A.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(self.panel.frame(), A.NSWindowStyleMaskBorderless, A.NSBackingStoreBuffered, False)
            cover.setOpaque_(True); cover.setBackgroundColor_(A.NSColor.blackColor())
            cover.orderFrontRegardless()
            F.NSRunLoop.currentRunLoop().runUntilDate_(F.NSDate.dateWithTimeIntervalSinceNow_(.25))
            self.refreshVisibility()
            assert not self.render_active.is_set(), 'Covered widget must stop'
            assert self.display_link.isPaused() and self.control_paused
            cover.orderOut_(None)
            F.NSRunLoop.currentRunLoop().runUntilDate_(F.NSDate.dateWithTimeIntervalSinceNow_(.25))
            self.screenLocked_(None); assert not self.panel.isVisible()
            assert self.lock_panel is not None and self.lock_panel.isVisible()
            assert self.lock_panel.ignoresMouseEvents()
            assert self.lock_space.space > 0
            assert self.panel.level() < A.NSNormalWindowLevel
            self.screenUnlocked_(None); assert self.panel.isVisible()
            assert self.lock_panel is None and self.lock_space.space == 0
            self.hidden = True; self.refreshVisibility()
            assert not self.render_active.is_set()
            assert self.display_link.isPaused()
            assert self.control_paused
            self.hidden = False; self.refreshVisibility()
            content = self.preferences.contentView()
            bitmap = content.bitmapImageRepForCachingDisplayInRect_(content.bounds())
            content.cacheDisplayInRect_toBitmapImageRep_(content.bounds(), bitmap)
            bitmap.representationUsingType_properties_(A.NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(str(OUT/'settings.png'), True)
            import statistics
            print('Warm draw median:', round(statistics.median(frame_times), 2), 'ms; max:', round(max(frame_times), 2), 'ms', flush=True)
            print('PASS: all nine styles, five widget presets, animation frames, lyrics-only transparency, no-progress rendering, timing nudges, desktop level, resizing, position, click-through, private lock-screen space, click-through, teardown, actual occlusion and hidden render/poll suspension', flush=True)
        except Exception:
            import traceback
            traceback.print_exc()
            import os
            os._exit(1)
        self.quit_(None)

app = A.NSApplication.sharedApplication()
app.setActivationPolicy_(A.NSApplicationActivationPolicyAccessory)
app.setAppearance_(A.NSAppearance.appearanceNamed_(A.NSAppearanceNameDarkAqua))
controller = SmokeController.alloc().init()
app.setDelegate_(controller)
timer = F.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(1, controller, 'finish:', None, False)
app.run()
