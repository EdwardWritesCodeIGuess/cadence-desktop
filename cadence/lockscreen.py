"""Private SkyLight space bridge, adapted from Maestro (see MAESTRO-LICENSE).

Only a separate, click-through lock-screen window is put in this space. Desktop
windows are never elevated. All symbols are resolved before any private call.
"""
import ctypes as C
import logging
import objc
from Foundation import NSArray


class LockScreenSpace:
    def __init__(self):
        self.connection = 0
        self.space = 0
        self.available = False
        self.reason = ''
        try:
            self.lib = C.CDLL('/System/Library/PrivateFrameworks/SkyLight.framework/SkyLight')
            signatures = {
                'SLSMainConnectionID': (C.c_int32, []),
                'SLSSpaceCreate': (C.c_uint64, [C.c_int32, C.c_int32, C.c_void_p]),
                'SLSSpaceSetAbsoluteLevel': (None, [C.c_int32, C.c_uint64, C.c_int32]),
                'SLSSpaceAddWindowsAndRemoveFromSpaces': (None, [C.c_int32, C.c_uint64, C.c_void_p, C.c_int32]),
                'SLSShowSpaces': (None, [C.c_int32, C.c_void_p]),
                'SLSSpaceDestroy': (None, [C.c_int32, C.c_uint64]),
            }
            self.functions = {}
            for name, (result, args) in signatures.items():
                fn = getattr(self.lib, name)
                fn.restype, fn.argtypes = result, args
                self.functions[name] = fn
            try:
                self.level = C.c_int32.in_dll(self.lib, 'kSLSSpaceAbsoluteLevelNotificationCenterAtScreenLock').value
            except ValueError:
                self.level = 400  # Same fallback as Maestro.
            self.available = True
        except (OSError, AttributeError) as exc:
            self.reason = str(exc)
            logging.warning('Lock-screen APIs unavailable: %s', self.reason)

    def attach(self, window):
        if not self.available:
            return False
        f = self.functions
        if not self.connection:
            self.connection = f['SLSMainConnectionID']()
        if not self.space:
            self.space = f['SLSSpaceCreate'](self.connection, 1, None)
            if not self.space:
                self.reason = 'WindowServer could not create the lock-screen space'
                return False
            f['SLSSpaceSetAbsoluteLevel'](self.connection, self.space, self.level)
        number = window.windowNumber()
        if number <= 0:
            self.close()
            self.reason = 'Lock-screen window could not be created'
            return False
        windows = NSArray.arrayWithArray_([number])
        f['SLSSpaceAddWindowsAndRemoveFromSpaces'](self.connection, self.space, objc.pyobjc_id(windows), 7)
        spaces = NSArray.arrayWithArray_([self.space])
        f['SLSShowSpaces'](self.connection, objc.pyobjc_id(spaces))
        logging.info('Lock-screen space attached: space=%d level=%d window=%d', self.space, self.level, number)
        return True

    def close(self):
        if self.space:
            self.functions['SLSSpaceDestroy'](self.connection, self.space)
            logging.info('Lock-screen space released')
            self.space = 0
