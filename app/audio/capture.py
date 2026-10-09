"""Windows WASAPI microphone and speaker-loopback capture using SoundCard."""
from __future__ import annotations
import threading
import time
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
    """Lightweight energy VAD; emits bounded utterance chunks after a short pause."""
    def __init__(self, on_segment, threshold=0.008, silence_seconds=0.55, min_seconds=0.32, max_seconds=8.0):
        self.on_segment=on_segment; self.threshold=threshold; self.silence_seconds=silence_seconds
        self.min_seconds=min_seconds; self.max_seconds=max_seconds; self.frames=[]; self.voiced=0; self.silence=0; self.samples=0
    def feed(self, frame):
        audio=np.asarray(frame,dtype=np.float32).reshape(-1)
        if not audio.size: return
        voiced=float(np.sqrt(np.mean(audio*audio))) >= self.threshold
        if voiced:
            self.frames.append(audio.copy()); self.voiced+=len(audio); self.silence=0; self.samples+=len(audio)
        elif self.frames:
            self.frames.append(audio.copy()); self.silence+=len(audio); self.samples+=len(audio)
        if self.frames and (self.silence >= self.silence_seconds*SAMPLE_RATE or self.samples >= self.max_seconds*SAMPLE_RATE):
            self.flush()
    def flush(self):
        if self.frames and self.voiced >= self.min_seconds*SAMPLE_RATE:
            self.on_segment(np.concatenate(self.frames).astype(np.float32,copy=False))
        self.reset()
    def reset(self): self.frames=[]; self.voiced=0; self.silence=0; self.samples=0

class CaptureThread(threading.Thread):
    def __init__(self, source, device_id, generation, router, on_segment, on_error):
        super().__init__(name=f'voxbridge-{source}-capture',daemon=True)
        self.source=source; self.device_id=device_id; self.generation=generation; self.router=router
        self.on_error=on_error; self.stop_event=threading.Event()
        self.segmenter=SpeechSegmenter(lambda audio:on_segment(source,(router.decision().generation if source=='partner' else generation),audio))
    def stop(self): self.stop_event.set()
    def run(self):
        try:
            import soundcard as sc
            if self.source=='partner':
                mic=sc.get_microphone(self.device_id,include_loopback=True)
            else:
                mic=sc.get_microphone(self.device_id,include_loopback=False)
            # SoundCard documents a WASAPI bug for mono-only reads; capture the
            # endpoint's native channels and downmix ourselves after capture.
            with mic.recorder(samplerate=SAMPLE_RATE,channels=mic.channels,blocksize=STREAM_BLOCKSIZE) as recorder:
                while not self.stop_event.is_set():
                    audio=recorder.record(numframes=BLOCK_FRAMES)
                    if getattr(audio,'ndim',1)>1: audio=np.mean(audio,axis=1,dtype=np.float32)
                    route=self.router.decision()
                    allowed=(route.accept_partner if self.source=='partner' else self.router.accepts_capture(self.source,self.generation))
                    if allowed: self.segmenter.feed(audio)
                    elif self.source=='partner': self.segmenter.reset()
        except Exception as exc:
            if not self.stop_event.is_set(): self.on_error(f'{self.source}: {exc}')
        finally:
            if self.source=='microphone': self.segmenter.flush()
