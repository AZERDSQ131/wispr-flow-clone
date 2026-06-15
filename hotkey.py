import threading
import time

from CoreFoundation import (
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    CFRunLoopStop,
    kCFRunLoopDefaultMode,
)
from Quartz import (
    CGEventGetFlags,
    CGEventSetFlags,
    CGEventSetIntegerValueField,
    CGEventSetType,
    CGEventTapCreate,
    CGEventTapEnable,
    CFMachPortCreateRunLoopSource,
    kCGEventFlagsChanged,
    kCGEventTapOptionDefault,
    kCGHIDEventTap,
    kCGHeadInsertEventTap,
    kCGKeyboardEventKeycode,
)

# Fn est un modificateur macOS, pas une touche ordinaire.
# CGEventTap sur kCGHIDEventTap capture ses changements de flag.
kCGEventFlagMaskSecondaryFn = 0x800000
_MASK = 1 << kCGEventFlagsChanged

DOUBLE_TAP_WINDOW = 0.35   # secondes entre deux taps
HOLD_THRESHOLD = 0.25      # secondes pour distinguer maintien vs tap
LATCH_COOLDOWN = 0.5       # zone morte après arrêt depuis LATCHED


class HotkeyListener:
    """
    Machine d'états :
      IDLE → (press) → PRESSING → (release long)   → IDLE  [on_stop]
                                → (release rapide) → FIRST_TAP
      FIRST_TAP → (timeout)  → IDLE  [on_stop]
      FIRST_TAP → (2e press) → LATCHED  [recording continue, pas de restart]
      LATCHED   → (press)    → IDLE  [on_stop]

    Principe clé : le recording n'est JAMAIS interrompu puis relancé lors
    d'un double-tap. On démarre au 1er press et on continue jusqu'à on_stop.
    """

    def __init__(self, on_start, on_stop):
        self.on_start = on_start
        self.on_stop = on_stop
        self.permission_granted = True

        self._lock = threading.Lock()
        self._state = "IDLE"
        self._press_time = 0.0
        self._tap_timer = None
        self._fn_down = False
        self._recovering_from_timeout = False
        self._latch_stop_time = 0.0
        self._run_loop = None
        self._thread = None
        self._tap = None

    def _cancel_timer(self):
        if self._tap_timer:
            self._tap_timer.cancel()
            self._tap_timer = None

    def _tap_timeout(self):
        # Appelé si aucun 2e press n'est venu : c'était un tap simple → stop.
        cb = None
        with self._lock:
            if self._state == "FIRST_TAP":
                self._state = "IDLE"
                cb = self.on_stop
        print(f"[hotkey] tap_timeout → {'on_stop' if cb else 'rien'}", flush=True)
        if cb:
            cb()

    def _on_fn_press(self):
        cb = None
        with self._lock:
            if self._recovering_from_timeout:
                self._recovering_from_timeout = False
                print("[hotkey] press ignoré (recovering_from_timeout)", flush=True)
                return

            prev = self._state
            if self._state == "IDLE":
                if time.time() - self._latch_stop_time < LATCH_COOLDOWN:
                    print("[hotkey] press ignoré (latch cooldown)", flush=True)
                    return
                self._press_time = time.time()
                self._state = "PRESSING"
                cb = self.on_start

            elif self._state == "FIRST_TAP":
                self._cancel_timer()
                self._state = "LATCHED"

            elif self._state == "LATCHED":
                self._latch_stop_time = time.time()
                self._state = "IDLE"
                cb = self.on_stop

        print(f"[hotkey] press  {prev} → {self._state}  cb={'on_start' if cb is self.on_start else 'on_stop' if cb is self.on_stop else 'rien'}", flush=True)
        if cb:
            cb()

    def _on_fn_release(self):
        cb = None
        with self._lock:
            prev = self._state
            if self._state == "PRESSING":
                duration = time.time() - self._press_time
                if duration >= HOLD_THRESHOLD:
                    self._state = "IDLE"
                    cb = self.on_stop
                else:
                    self._state = "FIRST_TAP"
                    self._tap_timer = threading.Timer(
                        DOUBLE_TAP_WINDOW, self._tap_timeout
                    )
                    self._tap_timer.start()

        print(f"[hotkey] release {prev} → {self._state}  cb={'on_stop' if cb else 'rien'}", flush=True)
        if cb:
            cb()

    def _event_callback(self, proxy, event_type, event, refcon):
        if event_type in (0xFFFFFFFE, 0xFFFFFFFF):
            if self._tap:
                CGEventTapEnable(self._tap, True)
            if self._fn_down:
                self._fn_down = False
                with self._lock:
                    simulate_release = self._state != "PRESSING"
                    if not simulate_release:
                        self._recovering_from_timeout = True
                if simulate_release:
                    self._on_fn_release()
            return event

        if event_type == kCGEventFlagsChanged:
            flags = CGEventGetFlags(event)
            fn_pressed = bool(flags & kCGEventFlagMaskSecondaryFn)
            if fn_pressed != self._fn_down:
                self._fn_down = fn_pressed
                if fn_pressed:
                    self._on_fn_press()
                else:
                    self._on_fn_release()
            CGEventSetFlags(event, flags & ~kCGEventFlagMaskSecondaryFn)
            CGEventSetType(event, 0)  # kCGEventNull
        return event

    def _run(self):
        tap = CGEventTapCreate(
            kCGHIDEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            _MASK,
            self._event_callback,
            None,
        )
        if not tap:
            self.permission_granted = False
            return

        self._tap = tap
        source = CFMachPortCreateRunLoopSource(None, tap, 0)
        self._run_loop = CFRunLoopGetCurrent()
        CFRunLoopAddSource(self._run_loop, source, kCFRunLoopDefaultMode)
        CGEventTapEnable(tap, True)
        CFRunLoopRun()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        time.sleep(0.1)

    def stop(self):
        self._cancel_timer()
        if self._run_loop:
            CFRunLoopStop(self._run_loop)
