import numpy as np
import pytest
from app.audio.capture import SpeechSegmenter, CaptureThread, SAMPLE_RATE
from app.core.state import AudioRouter

VOICE = np.full(1024, 0.1, dtype=np.float32)
SILENCE = np.zeros(1024, dtype=np.float32)


def test_segment_voice_followed_by_silence_and_flush_once():
    result = []
    segmenter = SpeechSegmenter(result.append)
    for _ in range(6):
        segmenter.feed(VOICE)
    for _ in range(9):
        segmenter.feed(SILENCE)
    segmenter.flush()
    assert len(result) == 1
    assert result[0].dtype == np.float32
    assert segmenter.samples == 0


def test_short_noise_and_nonfinite_input_do_not_form_speech():
    result = []
    segmenter = SpeechSegmenter(result.append)
    segmenter.feed(VOICE)
    segmenter.feed(np.array([np.nan, np.inf, -np.inf]))
    segmenter.flush()
    assert result == []


def test_continuous_speech_is_bounded():
    result = []
    segmenter = SpeechSegmenter(result.append, max_seconds=1.0)
    for _ in range(32):
        segmenter.feed(VOICE)
    segmenter.flush()
    assert len(result) == 2
    assert max(map(len, result)) <= SAMPLE_RATE + len(VOICE)


def test_consumer_failure_does_not_leave_old_audio():
    def fail(audio):
        raise RuntimeError("consumer unavailable")

    segmenter = SpeechSegmenter(fail)
    for _ in range(6):
        segmenter.feed(VOICE)
    with pytest.raises(RuntimeError):
        segmenter.flush()
    assert segmenter.samples == 0 and not segmenter.frames


def test_partner_block_crossing_ptt_is_discarded():
    router = AudioRouter()
    router.start()
    result = []
    capture = CaptureThread(
        "partner",
        "fake",
        0,
        router,
        lambda *args: result.append(args),
        lambda message: None,
    )
    before = router.decision()
    for _ in range(6):
        capture.accept_block(VOICE, before, before)
    after = router.press()
    capture.accept_block(VOICE, before, after)
    capture.segmenter.flush()
    assert result == []


def test_partner_old_buffer_is_not_retagged_after_unobserved_pause():
    router = AudioRouter()
    router.start()
    result = []
    capture = CaptureThread(
        "partner",
        "fake",
        0,
        router,
        lambda *args: result.append(args),
        lambda message: None,
    )
    old = router.decision()
    for _ in range(6):
        capture.accept_block(VOICE, old, old)
    router.pause()
    current = router.start()
    capture.accept_block(VOICE, current, current)
    capture.segmenter.flush()
    assert result == []  # New generation has only one short block.


def test_final_microphone_block_is_kept_after_release():
    router = AudioRouter()
    router.start()
    before = router.press()
    result = []
    capture = CaptureThread(
        "microphone",
        "fake",
        before.generation,
        router,
        lambda *args: result.append(args),
        lambda message: None,
    )
    for _ in range(5):
        capture.accept_block(VOICE, before, before)
    after = router.release()
    capture.accept_block(VOICE, before, after)
    capture.segmenter.flush()
    assert len(result) == 1
    assert result[0][1] == before.generation
    assert len(result[0][2]) == 6 * len(VOICE)
