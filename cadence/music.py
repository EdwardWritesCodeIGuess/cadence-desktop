"""Apple Music via native Apple Events; polling never launches Music."""
import time
from Foundation import NSAppleScript
from .core import Track

SCRIPT = '''
if application id "com.apple.Music" is not running then return {"stopped"}
tell application id "com.apple.Music"
    set playbackState to player state as text
    if playbackState is "stopped" then return {"stopped"}
    set currentSong to current track
    set trackID to ""
    try
        set trackID to persistent ID of currentSong
    end try
    return {playbackState, name of currentSong, artist of currentSong, album of currentSong, trackID, player position as text, duration of currentSong as text}
end tell
'''

class MusicReader:
    def __init__(self):
        self.script = NSAppleScript.alloc().initWithSource_(SCRIPT)

    def read(self):
        before = time.monotonic()
        descriptor, error = self.script.executeAndReturnError_(None)
        after = time.monotonic()
        if error:
            code = error.get('NSAppleScriptErrorNumber', 0)
            if code == -1743:
                raise PermissionError('Allow Cadence → Music in System Settings → Privacy & Security → Automation')
            raise RuntimeError(f'Apple Music is unavailable ({code})')
        if descriptor.numberOfItems() < 7:
            return Track(sampled_at=after)
        fields = [descriptor.descriptorAtIndex_(i).stringValue() or '' for i in range(1, 8)]
        playing = fields[0] == 'playing'
        position = float(fields[5].replace(',', '.')) + (min(1, after-before)/2 if playing else 0)
        return Track(title=fields[1], artist=fields[2], album=fields[3], identifier=fields[4],
                     position=position, duration=float(fields[6].replace(',', '.')),
                     playing=playing, sampled_at=after)
