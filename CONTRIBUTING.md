# Contributing

Use Python 3.11+ and deterministic tests. Install test dependencies with `python -m pip install -e ".[test]"`, then run `python -m compileall -q app tests` and `python -m pytest -q`.

Keep capture/model imports lazy. Tests must use injected capture, recognition, translation and input-hook fakes: do not open audio devices, install global hooks, download models or launch the overlay in the automated suite.

Preserve the microphone-first routing contract, bounded queues, engine/generation checks at GUI delivery and terminal STOPPING state. Keep UI rendering independent of route priority. Add regression coverage for timing/lifecycle changes; use threading Events instead of arbitrary sleeps.

Do not commit secrets, recordings, transcripts, model caches, logs, virtual environments or build artifacts. Update README and CHANGELOG when behavior or setup changes. Actual audio, CUDA and game-overlay checks are opt-in manual work.
