# VoxBridge

Local-first Windows desktop translator for gaming and live conversations. It translates partner system audio EN→RU and shows it in a compact overlay. Holding Mouse 5 gives the microphone absolute priority: RU→EN; partner transcription is suspended.

## Current implementation

The repository includes a real PySide6 overlay/tray entry point, centralized exclusive-priority state machine, bounded audio buffer, LM Studio-compatible translation provider, settings model, deterministic tests, and PyInstaller configuration. Windows WASAPI capture, faster-whisper model loading, and global hook adapters are designed as optional hardware-facing integrations and must be verified on a Windows machine with the selected devices.

## Install

```powershell
cd C:\Users\user\Desktop\ACTIVE\VoxBridge
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m app
```

In LM Studio load a translation-capable instruction model and start its local server at `http://localhost:1234`; enter its exact model id in settings when the full settings UI is enabled. First speech-model downloads require internet access. After model files are present and LM Studio is local, audio/translations can remain local. No telemetry, raw audio persistence, cloud speech recognition, or silent remote fallback is implemented.

## Behavior and limitations

The state machine is `STARTING`, `LISTENING_PARTNER`, `PUSH_TO_TALK`, `FINALIZING_USER_SPEECH`, `PAUSED`, `ERROR`, `STOPPING`. While PTT is held, partner frames and stale partner results are rejected. The UI is frameless, always on top, draggable, and has a tray menu. Default shortcuts planned for integration are Mouse 5, `Ctrl+Shift+V`, and `Ctrl+Shift+P`. Exclusive-fullscreen games may prevent overlays; borderless mode is recommended. No TTS, virtual microphone, chat injection, or process injection is used.

## Tests and build

```powershell
python -m pytest -q
python -m PyInstaller packaging/voxbridge.spec
```

Tests do not need a physical microphone, GPU, model weights, or LM Studio. For manual Windows acceptance, verify loopback capture, microphone selection, Mouse 5 press/release, device disconnect recovery, and focus/fullscreen behavior. Third-party dependencies retain their own licenses; the project is MIT licensed.
