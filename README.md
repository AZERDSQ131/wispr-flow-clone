# Spill

A macOS voice dictation app. Hold or double-tap **Fn** to record your voice, release (or tap again) to transcribe and inject the text wherever your cursor is.

Transcription is powered by [Mistral's Voxtral](https://mistral.ai/) model.

---

## Features

- **Hold Fn** → records while held, pauses media, then resumes and injects on release
- **Double-tap Fn** → latches recording, tap Fn again to transcribe and inject
- Native macOS HUD overlay (no Dock icon)
- Always-on mic indicator in the corner of the screen
- Forces the built-in microphone — no loopback or system audio bleed
- Suppresses the macOS emoji keyboard triggered by the Fn/Globe key

---

## Requirements

- macOS 12+
- Python 3.12 (framework build — `python.org` or Homebrew)
- A [Mistral API key](https://console.mistral.ai/api-keys/)

---

## Installation

```bash
git clone https://github.com/AZERDSQ131/spill
cd spill

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure your API key
cp .env.example .env
# Edit .env and paste your Mistral API key
```

---

## macOS Permissions

The app needs three permissions for **Terminal.app** (or whichever terminal you use):

1. **System Settings → Privacy → Microphone** → add Terminal
2. **System Settings → Privacy → Accessibility** → add Terminal
3. **System Settings → Privacy → Automation** → add Terminal → check "System Events"

---

## Usage

```bash
./run.sh
```

| Gesture | Action |
|---|---|
| Hold **Fn** (≥ 0.25s) | Records while held → pauses media, then resumes and injects on release |
| **Double-tap Fn** | Latches recording → tap Fn once more to transcribe and inject |

The transcribed text is injected at your cursor position in any app via clipboard paste.

---

## Configuration

All settings are in `config.py`:

| Variable | Default | Description |
|---|---|---|
| `HOTKEY_KEY` | `"fn"` | Key used to trigger recording |
| `MISTRAL_MODEL` | `"voxtral-mini-latest"` | Voxtral model to use |
| `MISTRAL_LANGUAGE` | `"fr"` | Language hint for transcription |
| `SAMPLE_RATE` | `16000` | Audio sample rate (Hz) |
| `RECORDING_TIMEOUT` | `60` | Max recording duration (seconds) |

---

## Architecture

```
HotkeyListener  (CGEventTap thread)
    │
    ▼  cmd_queue
DictationApp.run()  (main loop ~33 Hz)
    ├── AudioRecorder    — sounddevice stream, built-in mic
    ├── MistralTranscriber — Voxtral API call (daemon thread)
    ├── TextInjector     — clipboard + AppleScript Cmd+V
    └── Overlay          — native NSWindow HUD (PyObjC)
```

The hotkey listener uses a **CGEventTap** at `kCGHIDEventTap` level (below the window server) to intercept Fn key events. All inter-thread communication goes through a `queue.Queue` to keep the main loop single-threaded.

---

## License

MIT
