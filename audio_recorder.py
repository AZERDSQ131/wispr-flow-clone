import io
import wave

import numpy as np
import sounddevice as sd

from config import CHANNELS, DTYPE, SAMPLE_RATE


def _find_builtin_mic():
    """Retourne l'index du micro intégré (évite les loopbacks et agrégats)."""
    priority_keywords = ["macbook", "built-in", "microphone intégré"]
    fallback = None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] < 1:
            continue
        name = d["name"].lower()
        if any(k in name for k in priority_keywords):
            return i
        if fallback is None:
            fallback = i
    return fallback


class AudioRecorder:
    def __init__(self):
        self.recording = []
        self.stream = None
        self._done = False
        self._mic_index = _find_builtin_mic()

    def start_recording(self):
        # Ferme proprement un éventuel stream précédent avant d'en ouvrir un nouveau
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        self.recording = []
        self._done = False
        self.stream = sd.InputStream(
            device=self._mic_index,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._callback,
        )
        self.stream.start()

    def _callback(self, indata, frames, time, status):
        if status:
            print(f"[audio] {status}")
        self.recording.append(indata.copy())

    def stop_recording(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        if not self.recording:
            return None

        audio_data = np.concatenate(self.recording, axis=0)

        if np.max(np.abs(audio_data)) < 15:
            return None

        return audio_data

    @staticmethod
    def save_to_wav(audio_data):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data.tobytes())
        buffer.seek(0)
        return buffer
