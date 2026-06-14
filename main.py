import queue
import subprocess
import sys
import threading
import time

import Quartz
from AppKit import NSEvent

from audio_recorder import AudioRecorder
from config import MISTRAL_API_KEY
from hotkey import HotkeyListener
from overlay import Overlay
from text_injector import TextInjector
from transcriber import MistralTranscriber


_NX_KEYTYPE_PLAY = 16


def _media_playpause():
    """Envoie la touche Play/Pause système (fonctionne avec tous les lecteurs)."""
    for key_down in (True, False):
        flags = 0xa00 if key_down else 0xb00
        data1 = (_NX_KEYTYPE_PLAY << 16) | flags
        ev = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            14, (0, 0), 0, 0, 0, None, 8, data1, -1,
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev.CGEvent())


def _fn_emoji_disable():
    """Désactive temporairement le clavier emoji sur la touche Fn/Globe.
    Retourne la valeur originale pour la restaurer à la fermeture."""
    result = subprocess.run(
        ["defaults", "read", "com.apple.HIToolbox", "AppleFnUsageType"],
        capture_output=True, text=True,
    )
    original = result.stdout.strip() if result.returncode == 0 else None
    subprocess.run(
        ["defaults", "write", "com.apple.HIToolbox", "AppleFnUsageType", "-int", "0"],
        capture_output=True,
    )
    # Force la prise en compte immédiate par le daemon de préférences
    subprocess.run(["killall", "-HUP", "cfprefsd"], capture_output=True)
    return original


def _fn_emoji_restore(original):
    """Restaure le comportement original de la touche Fn/Globe."""
    if original is not None:
        subprocess.run(
            ["defaults", "write", "com.apple.HIToolbox", "AppleFnUsageType",
             "-int", original],
            capture_output=True,
        )
    else:
        subprocess.run(
            ["defaults", "delete", "com.apple.HIToolbox", "AppleFnUsageType"],
            capture_output=True,
        )
    subprocess.run(["killall", "-HUP", "cfprefsd"], capture_output=True)


PERMISSIONS_GUIDE = """\
╔══════════════════════════════════════════════════════════════╗
║  1.  Réglages → Confidentialité → Microphone                ║
║       → Ajoute Terminal.app                                 ║
║                                                              ║
║  2.  Réglages → Confidentialité → Accessibilité              ║
║       → Ajoute Terminal.app                                 ║
║                                                              ║
║  3.  Réglages → Confidentialité → Automatisation             ║
║       → Ajoute Terminal.app → coche "System Events"          ║
╚══════════════════════════════════════════════════════════════╝"""


class DictationApp:
    def __init__(self):
        if not MISTRAL_API_KEY:
            print("""\nErreur : MISTRAL_API_KEY non définie.
Créez un fichier .env à partir de .env.example :
    cp .env.example .env
    # éditez .env et mettez votre clé API Mistral""")
            sys.exit(1)

        self.recorder = AudioRecorder()
        self.injector = TextInjector()
        self.overlay = Overlay()
        self.transcriber = MistralTranscriber()

        self.cmd_queue = queue.Queue()
        self._media_paused = False

        self.hotkey = HotkeyListener(
            on_start=self._on_hotkey_pressed,
            on_stop=self._on_hotkey_released,
            on_cancel=self._on_hotkey_cancelled,
        )

    def _on_hotkey_pressed(self):
        self.cmd_queue.put(("start_recording", None))

    def _on_hotkey_released(self):
        self.cmd_queue.put(("stop_recording", None))

    def _on_hotkey_cancelled(self):
        self.cmd_queue.put(("cancel_recording", None))

    def _resume_media_if_needed(self):
        if self._media_paused:
            self._media_paused = False
            _media_playpause()

    def _handle_cancel_recording(self):
        self.recorder.stop_recording()
        self.overlay.hide()
        self._resume_media_if_needed()

    def _handle_start_recording(self):
        _media_playpause()
        self._media_paused = True
        self.overlay.show_recording()
        self.recorder.start_recording()

    def _handle_stop_recording(self):
        audio_data = self.recorder.stop_recording()
        self._resume_media_if_needed()
        self.overlay.show_processing()
        if audio_data is None:
            self.overlay.hide()
            return
        thread = threading.Thread(target=self._process_audio, args=(audio_data,))
        thread.daemon = True
        thread.start()

    def _process_audio(self, audio_data):
        try:
            audio_bytes = self.recorder.save_to_wav(audio_data).getvalue()
            text = self.transcriber.transcribe(audio_bytes)
            if text and text.strip():
                self.cmd_queue.put(("inject_text", text.strip()))
            else:
                self.cmd_queue.put(("hide", None))
        except Exception as e:
            print(f"[erreur] {e}")
            self.cmd_queue.put(("error", str(e)[:45]))

    def _handle_inject_text(self, text):
        self.injector.inject(text)
        self.overlay.hide()

    def _handle_error(self, message):
        self.overlay.show_error(message)
        thread = threading.Thread(target=lambda: (
            time.sleep(2.5), self.cmd_queue.put(("hide", None))
        ))
        thread.daemon = True
        thread.start()

    def run(self):
        print("\U0001f3a4 Wispr Flow Clone")
        print("Maintien Fn       → enregistre, relâche pour envoyer.")
        print("Double-tap Fn     → latch, puis Fn pour envoyer.")
        print("Ctrl+C pour quitter.\n")

        self.overlay.show_idle()
        self.hotkey.start()
        if not self.hotkey.permission_granted:
            print("""⚠️  Permission Accessibilité requise !
Le raccourci clavier ne fonctionnera pas sans cette permission.
""")
            print(PERMISSIONS_GUIDE)
            print("\nAprès avoir accordé les permissions, relance l'app.")

        try:
            while True:
                try:
                    cmd, data = self.cmd_queue.get_nowait()
                    if cmd == "start_recording":
                        self._handle_start_recording()
                    elif cmd == "cancel_recording":
                        self._handle_cancel_recording()
                    elif cmd == "stop_recording":
                        self._handle_stop_recording()
                    elif cmd == "inject_text":
                        self._handle_inject_text(data)
                    elif cmd == "error":
                        self._handle_error(data)
                    elif cmd == "hide":
                        self.overlay.hide()
                except queue.Empty:
                    pass
                self.overlay.update()
                time.sleep(0.03)
        except KeyboardInterrupt:
            print("\nAu revoir !")
        finally:
            self.hotkey.stop()
            self.overlay.close()


if __name__ == "__main__":
    original_fn_type = _fn_emoji_disable()
    try:
        app = DictationApp()
        app.run()
    finally:
        _fn_emoji_restore(original_fn_type)
