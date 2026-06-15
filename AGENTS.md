# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Présentation

Clone macOS de Wispr Flow : une app de dictée vocale qui capte l'audio au maintien d'un raccourci clavier, transcrit via l'API Mistral (Voxtral), puis injecte le texte dans l'application active.

## Commandes

```bash
# Lancer l'app
./run.sh
# ou directement :
.venv/bin/python3 main.py

# Installer les dépendances (dans le venv existant)
.venv/bin/pip install -r requirements.txt
```

## Configuration

Copier `.env.example` → `.env` et renseigner `MISTRAL_API_KEY`. Les paramètres audio, le raccourci et le modèle sont tous dans `config.py`.

## Architecture

Le flux de données principal est linéaire :

```
HotkeyListener (pynput thread)
    → cmd_queue (thread-safe)
    → DictationApp.run() [boucle principale, ~33 Hz]
        → AudioRecorder (sounddevice stream)
        → MistralTranscriber (API Voxtral)  ← thread daemon
        → TextInjector (clipboard + AppleScript Cmd+V)
        → Overlay (fenêtre HUD PyObjC)
```

**`main.py` / `DictationApp`** — orchestre tout via une `queue.Queue`. Les événements du listener clavier (thread séparé) et la transcription (thread daemon) communiquent avec la boucle principale uniquement par cette queue. Les commandes sont : `start_recording`, `stop_recording`, `inject_text`, `error`, `hide`.

**`overlay.py`** — Fenêtre HUD native macOS (PyObjC / AppKit + Quartz). Ne peut pas devenir fenêtre principale/key (évite de voler le focus). L'opacité est gérée manuellement (pas d'animation Core Animation). `update()` doit être appelé dans la boucle principale pour que NSApplication traite ses événements.

**`text_injector.py`** — Copie le texte dans le presse-papier via `pyperclip`, attend 80 ms, puis simule Cmd+V via `osascript` / System Events.

**`audio_recorder.py`** — Détecte le silence : si l'amplitude max est inférieure à 15 (int16), l'enregistrement est ignoré et `None` est retourné.

## Permissions macOS requises (pour Terminal.app)

1. Réglages → Confidentialité → **Microphone**
2. Réglages → Confidentialité → **Accessibilité**
3. Réglages → Confidentialité → **Automatisation** → cocher "System Events"

Sans la permission Accessibilité, `pynput` ne peut pas lire les touches globales. Sans Automatisation → System Events, `osascript` ne peut pas simuler Cmd+V.

## Points de vigilance

- **PyObjC** (`AppKit`, `Quartz`) est fourni par le système macOS et **ne figure pas dans `requirements.txt`** — il ne s'installe pas via pip sur Apple Silicon dans un venv standard.
- Le modèle Mistral utilisé est `voxtral-mini-latest` avec `language="fr"` (configurable dans `config.py`).
- L'injection de texte écrase le presse-papier de l'utilisateur à chaque dictée.
