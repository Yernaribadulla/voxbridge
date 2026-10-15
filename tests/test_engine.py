from threading import Event
import pytest
from PySide6.QtCore import Qt
from app.audio.engine import AudioEngine
from app.config import Settings
from app.core.state import AudioRouter, State


class FakeCapture:
    def __init__(self, source, device, generation, router, submit, error):
        self.source, self.generation, self.error = source, generation, error
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def is_alive(self):
        return self.running


class Recognizer:
    def __init__(self):
        self.entered = Event()
        self.proceed = Event()
        self.block = False
        self.calls = []

    def load(self):
        return self

    def transcribe(self, audio, language):
        self.calls.append(language)
        self.entered.set()
        if self.block:
            assert self.proceed.wait(2)
        return str(audio)


class Translator:
    def translate(self, text, direction):
        return direction + ":" + text


@pytest.fixture
def engine():
    router = AudioRouter()
    recognizer = Recognizer()
    value = AudioEngine(
        router,
        Settings(
            mic_device="fake-mic",
            system_device="fake-speaker",
            translation_model="fixture",
        ),
        recognizer=recognizer,
        translator=Translator(),
        capture_factory=FakeCapture,
    )
    ready = Event()
    value.signals.route.connect(lambda engine_id: ready.set(), Qt.DirectConnection)
    value.ptt_requested.connect(value.begin_ptt, Qt.DirectConnection)
    value.ptt_released.connect(value.finish_ptt, Qt.DirectConnection)
    value.start()
    assert ready.wait(2)
    yield value, recognizer
    recognizer.proceed.set()
    value.close()
    if value._loader:
        value._loader.join(2)
    for worker in value._workers:
        worker.join(2)
    assert value.quiescent
    value.release_resources()


def test_pipeline_translates_both_directions_and_keeps_partner_capture(engine):
    value, recognizer = engine
    results = []
    partner_done, mic_done = Event(), Event()

    def receive(event):
        results.append(event)
        if event.translated:
            (mic_done if event.source == "microphone" else partner_done).set()

    value.signals.transcript.connect(receive, Qt.DirectConnection)
    generation = value.router.decision().generation
    assert value._submit("partner", generation, "hello")
    assert partner_done.wait(2)
    value.request_ptt()
    current = value.router.decision().generation
    assert value._submit("microphone", current, "привет")
    value.request_release()
    assert mic_done.wait(2)
    assert value._capture.is_alive()
    assert value.router.decision().state is State.LISTENING_PARTNER
    assert {"en_ru:hello", "ru_en:привет"} <= {event.translated for event in results}
    assert recognizer.calls == ["en", "ru"]


def test_partner_inference_completing_after_ptt_never_publishes(engine):
    value, recognizer = engine
    recognizer.block = True
    results = []
    done = Event()

    def receive(event):
        results.append(event)
        if event.translated:
            done.set()

    value.signals.transcript.connect(receive, Qt.DirectConnection)
    assert value._submit("partner", value.router.decision().generation, "old partner")
    assert recognizer.entered.wait(2)
    value.request_ptt()
    generation = value.router.decision().generation
    assert value._submit("microphone", generation, "new microphone")
    recognizer.proceed.set()
    assert done.wait(2)
    assert results and all(event.source == "microphone" for event in results)


def test_pause_rejects_late_results_and_resume_keeps_capture(engine):
    value, recognizer = engine
    generation = value.router.decision().generation
    value.pause()
    assert not value._submit("partner", generation, "old")
    value.resume()
    assert value.router.decision().state is State.LISTENING_PARTNER
    assert value._capture.is_alive()


def test_failed_capture_can_be_restarted_explicitly(engine):
    value, recognizer = engine
    old = value._capture
    old.stop()
    old.error("device disconnected")
    assert value.router.decision().state is State.PAUSED
    value.resume()
    assert value._capture is not old and value._capture.is_alive()


def test_close_prevents_new_work_and_does_not_resurrect(engine):
    value, recognizer = engine
    value.close()
    value.close()
    value.resume()
    value.request_ptt()
    assert value.router.decision().state is State.STOPPING
    assert not value._submit("microphone", 0, "discard")
    assert not value.ready


def test_concurrent_ptt_requests_only_start_one_microphone(engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    value, recognizer = engine
    barrier = Barrier(4)
    signals = []
    value.ptt_requested.connect(signals.append, Qt.DirectConnection)

    def press(index):
        barrier.wait(timeout=2)
        value.request_ptt()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(press, range(4)))
    assert len(signals) == 1
    assert value.router.utterance == 1


def test_idle_engine_does_not_load_models_or_open_devices():
    class IdleRecognizer:
        def load(self):
            raise AssertionError("No model loading before explicit start")

    def forbidden_capture(*args):
        raise AssertionError("No capture before explicit start")

    value = AudioEngine(
        AudioRouter(),
        Settings(),
        recognizer=IdleRecognizer(),
        translator=Translator(),
        capture_factory=forbidden_capture,
    )
    assert not value.started and not value.ready
    assert value._workers == [] and value._captures == []
    value.close()
    assert value.release_resources()
