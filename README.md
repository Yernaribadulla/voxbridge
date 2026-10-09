# VoxBridge

VoxBridge is a Windows desktop voice translator for games and live conversations. It captures speaker loopback, recognizes the partner's English, translates it to Russian, and displays both in an always-on-top overlay. Hold Mouse 5 to switch transcription to your microphone; your Russian speech is translated to English. The routing state changes before GUI or inference work, and partner frames/results are rejected during push-to-talk.

## Install and run

Windows 10/11, Python 3.11+ (Python 3.14 works when the optional dependencies provide wheels), a microphone, a playback device, and local LM Studio are needed.

```powershell
cd C:\Users\user\Desktop\ACTIVE\VoxBridge
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app
```

Activation is optional. In PowerShell, if desired, run `Set-ExecutionPolicy -Scope Process Bypass` and then `\.venv\Scripts\Activate.ps1`.

## First setup

Open Settings. Select the physical microphone and the speaker/output endpoint to capture. Select multilingual Whisper `base` or `small`; do not select English-only `tiny.en` for Russian microphone speech. Choose CPU (`int8`) for compatibility, or NVIDIA CUDA (`float16`) if CTranslate2 and compatible NVIDIA CUDA/cuDNN libraries are installed. If CUDA fails, switch to CPU.

Install LM Studio, load a translation-capable instruction model, enable its local server, and use `http://localhost:1234/v1` unless you intentionally configure another endpoint. Enter the model ID shown in LM Studio, then run the connection test. Without a model ID VoxBridge can recognize speech but cannot translate it. Starting VoxBridge asks before loading Whisper; the first model download needs internet and its size varies by model/backend. Models are cached locally.

## Controls

- Mouse 5 / X2: hold to speak Russian. The in-window hold button is available if a game blocks the global hook.
- `Ctrl+Shift+V`: show/hide the overlay.
- `Ctrl+Shift+P`: pause/resume audio processing.
- Tray menu: show/hide, pause/resume, settings, exit.

The overlay is frameless, always on top, and draggable. Borderless windowed mode is recommended; a normal Qt window is not guaranteed above exclusive-fullscreen games. Audio is processed in memory and not saved. VoxBridge does not upload audio/transcripts, collect telemetry, or silently fall back to a remote service. A non-local translation endpoint receives transcript text.

## Architecture and limitations

`app/core/state.py` owns route priority and generations. `app/audio/capture.py` uses SoundCard/WASAPI for microphone and speaker loopback, with short blocks and energy-based segmentation. `app/audio/engine.py` loads one multilingual faster-whisper model, prioritizes microphone jobs, rejects stale partner results, and calls LM Studio asynchronously. One Whisper model is shared across both directions to avoid holding two copies in GPU memory.

An inference call already in progress when Mouse 5 is pressed cannot be interrupted inside CTranslate2; its output is discarded, queued partner segments are invalidated, and no new partner segment is submitted while PTT is held. Latency and accuracy depend on the speech/translation models, hardware, and game load. LM Studio runs separately and needs its own memory/VRAM.

## Development

```powershell
python -m pytest -q
python -m PyInstaller packaging/voxbridge.spec
```

Automated tests do not require a GPU, model weights, physical audio devices, or LM Studio. Check actual audio devices, global hooks in games, and CUDA on the target PC. Do not commit secrets, recordings, transcripts, model caches, logs, or virtual environments. MIT license; third-party dependencies keep their own licenses.
