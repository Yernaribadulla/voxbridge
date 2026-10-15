# Changelog

## 0.4.0
- Fixed the global mouse callback signature and duplicate/held-button handling; failed keyboard-hook startup now cleans up the mouse listener.
- Added bounded microphone-first recognition and translation queues, preserving microphone work on overload.
- Reject audio crossing route boundaries; preserve the final microphone block after release.
- Check engine identity, generation and sequence again at GUI delivery; restart result ordering after settings changes.
- Release retired model resources after workers stop and prevent overlapping model reloads.
- Added explicit error handling/retry for failed capture and bounded LM Studio response contracts.
- Added validated atomic settings, environment overrides, CPU compute safeguards, font/opacity controls and a preview mode without audio/hooks/models.
- Separated text widgets and QSS from overlay control; corrected packaging paths and included the theme in Python wheels/PyInstaller data.
- Added hardware-free regression tests and Windows/Linux CI.

## 0.3.1
- Fixed settings Save handling; selected devices and model ID now persist after accepting the dialog.

## 0.3.0
- Restyled the overlay to match the supplied reference, with bounded two-line text, a 6.5-second fade, and a highlighted active-microphone strip.

## 0.2.0
- Connected WASAPI speaker loopback and microphone capture to the Whisper and LM Studio pipeline.
- Added settings for devices, multilingual model, compute type, API endpoint/model, Mouse 5 rebinding, global shortcuts, and real-time overlay status.
- Corrected PySide6 window flags and setup instructions; ensured audio package is tracked by Git.

## 0.1.0
- Initial local-first Windows translator shell, routing state machine, provider, buffer, tests, and packaging configuration.
