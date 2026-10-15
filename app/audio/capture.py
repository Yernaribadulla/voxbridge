"""Windows WASAPI capture. Hardware imports stay inside device/capture functions."""

from __future__ import annotations
import threading
import numpy as np

SAMPLE_RATE = 16000
BLOCK_FRAMES = 1024
STREAM_BLOCKSIZE = 4096


def input_devices():
    import soundcard as sc

    return [(m.name, m.id) for m in sc.all_microphones(include_loopback=False)]


def output_devices():
    import soundcard as sc

    return [(s.name, s.id) for s in sc.all_speakers()]


class SpeechSegmenter:
    """Energy VAD with bounded chunks; trailing microphone speech can be flushed."""

    def __init__(
        self,
        on_segment,
        threshold=0.008,
        silence_seconds=0.55,
        min_seconds=0.32,
        max_seconds=8.0,
    ):
        self.on_segment = on_segment
        self.threshold = threshold
        self.silence_samples = int(silence_seconds * SAMPLE_RATE)
        self.min_samples = int(min_seconds * SAMPLE_RATE)
        self.max_samples = int(max_seconds * SAMPLE_RATE)
        self.reset()

    def feed(self, frame):
        audio = np.asarray(frame, dtype=np.float32).reshape(-1)
        if not audio.size:
            return
        audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        voiced = float(np.sqrt(np.mean(audio * audio))) >= self.threshold
        if voiced or self.frames:
            self.frames.append(audio.copy())
            self.samples += audio.size
            if voiced:
                self.voiced += audio.size
                self.silence = 0
            else:
                self.silence += audio.size
        if self.frames and (
            self.silence >= self.silence_samples or self.samples >= self.max_samples
        ):
            self.flush()

    def flush(self):
        frames, voiced = self.frames, self.voiced
        self.reset()  # A failing consumer must not keep old audio in the buffer.
        if frames and voiced >= self.min_samples:
            self.on_segment(np.concatenate(frames).astype(np.float32, copy=False))

    def reset(self):
        self.frames = []
        self.voiced = self.silence = self.samples = 0


class CaptureThread(threading.Thread):
    def __init__(self, source, device_id, generation, router, on_segment, on_error):
        super().__init__(name=f"voxbridge-{source}-capture", daemon=True)
        self.source = source
        self.device_id = device_id
        self.generation = generation
        self.router = router
        self.on_error = on_error
        self.stop_event = threading.Event()
        self._segment_generation = generation
        self._on_segment = on_segment
        self.segmenter = SpeechSegmenter(self._deliver_segment)

    def _deliver_segment(self, audio):
        self._on_segment(self.source, self._segment_generation, audio)

    def stop(self):
        self.stop_event.set()

    def accept_block(self, audio, before, after):
        """Reject blocks crossing PTT/pause boundaries instead of retagging old audio."""
        stable = before.generation == after.generation
        if self.source == "partner":
            allowed = stable and before.accept_partner and after.accept_partner
        else:
            # Keep the final read begun while PTT was held, even after release.
            allowed = (
                stable
                and before.accept_microphone
                and self.router.accepts_result("microphone", self.generation)
            )
        if not allowed:
            self.segmenter.reset()
            return
        if self._segment_generation != before.generation:
            self.segmenter.reset()
        self._segment_generation = before.generation
        self.segmenter.feed(audio)

    def run(self):
        try:
            import soundcard as sc

            mic = sc.get_microphone(
                self.device_id, include_loopback=self.source == "partner"
            )
            # Native-channel reads avoid the documented WASAPI mono-read issue.
            with mic.recorder(
                samplerate=SAMPLE_RATE,
                channels=mic.channels,
                blocksize=STREAM_BLOCKSIZE,
            ) as recorder:
                while not self.stop_event.is_set():
                    before = self.router.decision()
                    audio = recorder.record(numframes=BLOCK_FRAMES)
                    if getattr(audio, "ndim", 1) > 1:
                        audio = np.mean(audio, axis=1, dtype=np.float32)
                    self.accept_block(audio, before, self.router.decision())
        except Exception as exc:
            if not self.stop_event.is_set():
                self.on_error(f"{self.source}: {exc}")
        finally:
            if self.source == "microphone":
                self.segmenter.flush()
            else:
                self.segmenter.reset()
