"""Capture, one shared Whisper model and bounded asynchronous translation workers."""

from __future__ import annotations
import itertools
import threading
import uuid
from dataclasses import dataclass
from PySide6.QtCore import QObject, Signal, Slot
from app.audio.capture import CaptureThread
from app.core.jobs import PriorityWorkQueue, QueueClosed
from app.core.state import State
from app.speech.whisper import WhisperRecognizer
from app.translation.lmstudio import LMStudioProvider


@dataclass(frozen=True)
class SpeechJob:
    source: str
    generation: int
    audio: object
    sequence: int


@dataclass(frozen=True)
class TranslationJob:
    source: str
    generation: int
    sequence: int
    text: str
    direction: str


@dataclass(frozen=True)
class EngineMessage:
    engine_id: str
    generation: int
    message: str


@dataclass(frozen=True)
class TranscriptResult:
    engine_id: str
    generation: int
    sequence: int
    source: str
    text: str
    translated: str
    status: str


class EngineSignals(QObject):
    status = Signal(object)
    route = Signal(str)
    transcript = Signal(object)
    error = Signal(object)


class AudioEngine(QObject):
    ptt_requested = Signal(int)
    ptt_released = Signal(int)

    def __init__(
        self,
        router,
        settings,
        *,
        recognizer=None,
        translator=None,
        capture_factory=CaptureThread,
    ):
        super().__init__()
        self.id = uuid.uuid4().hex
        self.router, self.settings = router, settings
        self.signals = EngineSignals()
        self._jobs = PriorityWorkQueue(8)
        self._translations = PriorityWorkQueue(8)
        self._sequence = itertools.count()
        self._capture = self._mic_capture = None
        self._mic_generation = None
        self._started = self._ready = False
        self._closing = threading.Event()
        self._lifecycle = threading.RLock()
        self._input_lock = threading.Lock()
        self._recognizer = recognizer or WhisperRecognizer(
            settings.user_model, settings.compute_device, settings.compute_type
        )
        self._translator = translator or LMStudioProvider(
            settings.translation_url, settings.translation_model
        )
        self._capture_factory = capture_factory
        self._workers = []
        self._loader = None
        self._captures = []

    @property
    def ready(self):
        return self._ready and not self._closing.is_set()

    @property
    def started(self):
        return self._started

    @property
    def quiescent(self):
        threads = (
            self._workers + self._captures + ([self._loader] if self._loader else [])
        )
        return not any(thread.is_alive() for thread in threads)

    def _status(self, message, error=False, generation=None):
        if not self._closing.is_set():
            event = EngineMessage(
                self.id,
                self.router.decision().generation if generation is None else generation,
                message,
            )
            (self.signals.error if error else self.signals.status).emit(event)

    def _route(self):
        if not self._closing.is_set():
            self.signals.route.emit(self.id)

    def start(self):
        with self._lifecycle:
            if self._started or self._closing.is_set():
                return
            self._started = True
        self._status(
            f"Загрузка Whisper {self.settings.user_model}… Первый запуск может потребовать скачивания."
        )
        self._loader = threading.Thread(
            target=self._load_and_listen, name="voxbridge-model-load", daemon=True
        )
        self._loader.start()

    def _load_and_listen(self):
        try:
            self._recognizer.load()
            with self._lifecycle:
                if self._closing.is_set():
                    return
                self._ready = True
                self.router.start()
                if not self._workers:
                    for target, name in (
                        (self._process, "recognition"),
                        (self._translate_loop, "translate-1"),
                        (self._translate_loop, "translate-2"),
                    ):
                        worker = threading.Thread(
                            target=target, name=f"voxbridge-{name}", daemon=True
                        )
                        self._workers.append(worker)
                        worker.start()
                self._capture = self._make_capture(
                    "partner",
                    self.settings.system_device,
                    self.router.decision().generation,
                )
                self._capture.start()
            self._route()
            route = self.router.decision()
            if route.state is State.LISTENING_PARTNER:
                self._status(
                    "Слушаю собеседника. Удерживайте Mouse 5 для ответа.",
                    generation=route.generation,
                )
        except Exception as exc:
            with self._lifecycle:
                if self._closing.is_set():
                    return
                self._started = self._ready = False
                self.router.fail()
            self._status(f"Не удалось запустить аудио: {exc}", error=True)
            self._route()

    def _make_capture(self, source, device, generation):
        with self._lifecycle:
            capture = self._capture_factory(
                source,
                device,
                generation,
                self.router,
                self._submit,
                lambda message: self._capture_error(source, generation, message),
            )
            self._captures = [thread for thread in self._captures if thread.is_alive()]
            self._captures.append(capture)
            return capture

    def _capture_error(self, source, generation, message):
        if self._closing.is_set():
            return
        if source == "partner":
            self.pause()
        elif self.router.decision().generation == generation:
            self.request_release()
        else:
            return
        self._status(message, error=True)

    def _discard_stale(self):
        invalid = lambda job: not self.router.accepts_result(job.source, job.generation)
        self._jobs.discard(invalid)
        self._translations.discard(invalid)

    def request_ptt(self):
        if not self.ready:
            return
        with self._input_lock:
            before = self.router.decision()
            decision = self.router.press()  # Priority changes before work reaches Qt.
        if (
            decision.state is State.PUSH_TO_TALK
            and before.state is not State.PUSH_TO_TALK
        ):
            self._discard_stale()
            self.ptt_requested.emit(decision.generation)

    @Slot(int)
    def begin_ptt(self, generation):
        route = self.router.decision()
        if (
            route.generation != generation
            or route.state is not State.PUSH_TO_TALK
            or not self.ready
        ):
            return
        if self._mic_capture:
            self._mic_capture.stop()
        self._mic_generation = generation
        if self.settings.mic_device:
            self._mic_capture = self._make_capture(
                "microphone", self.settings.mic_device, generation
            )
            self._mic_capture.start()
        else:
            self._status("Микрофон не выбран. Откройте настройки.", error=True)
        self._route()
        self._status("Микрофон активен. Говорите по-русски…")

    def request_release(self):
        with self._input_lock:
            before = self.router.decision()
            decision = self.router.release()
        if before.state is State.PUSH_TO_TALK:
            self.ptt_released.emit(decision.generation)

    @Slot(int)
    def finish_ptt(self, generation):
        if self._mic_generation == generation:
            if self._mic_capture:
                self._mic_capture.stop()
            self._mic_capture = None
            self._mic_generation = None
        route = self.router.decision()
        if (
            route.generation == generation
            and route.state is State.FINALIZING_USER_SPEECH
        ):
            self.router.partner_resumed()
            self._route()
            self._status("Слушаю собеседника. Ваш ответ переводится в фоне.")

    def pause(self):
        self.router.pause()
        if self._mic_capture:
            self._mic_capture.stop()
            self._mic_capture = None
        self._discard_stale()
        self._route()
        self._status("Пауза. Новые фрагменты не обрабатываются.")

    def resume(self):
        if self.ready:
            self.router.start()
            if self._capture is None or not self._capture.is_alive():
                self._capture = self._make_capture(
                    "partner",
                    self.settings.system_device,
                    self.router.decision().generation,
                )
                self._capture.start()
            self._route()
            self._status("Слушаю собеседника.")

    def _submit(self, source, generation, audio):
        if self._closing.is_set() or not self.router.accepts_result(source, generation):
            return False
        return self._jobs.put(
            SpeechJob(source, generation, audio, next(self._sequence))
        )

    def _emit_transcript(self, job, text, translated, status):
        if not self._closing.is_set() and self.router.accepts_result(
            job.source, job.generation
        ):
            self.signals.transcript.emit(
                TranscriptResult(
                    self.id,
                    job.generation,
                    job.sequence,
                    job.source,
                    text,
                    translated,
                    status,
                )
            )

    def _process(self):
        while not self._closing.is_set():
            try:
                job = self._jobs.get()
            except QueueClosed:
                return
            if not self.router.accepts_result(job.source, job.generation):
                continue
            try:
                self._status("Распознаю речь…", generation=job.generation)
                text = self._recognizer.transcribe(
                    job.audio, language="ru" if job.source == "microphone" else "en"
                )
                if not text or not self.router.accepts_result(
                    job.source, job.generation
                ):
                    continue
                self._emit_transcript(job, text, "", "Перевожу…")
                direction = "ru_en" if job.source == "microphone" else "en_ru"
                self._translations.put(
                    TranslationJob(
                        job.source, job.generation, job.sequence, text, direction
                    )
                )
            except Exception as exc:
                if self.router.accepts_result(job.source, job.generation):
                    self._status(
                        f"Ошибка распознавания: {exc}",
                        error=True,
                        generation=job.generation,
                    )

    def _translate_loop(self):
        while not self._closing.is_set():
            try:
                job = self._translations.get()
            except QueueClosed:
                return
            if not self.router.accepts_result(job.source, job.generation):
                continue
            try:
                text = self._translator.translate(job.text, job.direction)
                self._emit_transcript(job, job.text, text, "Переведено")
            except Exception as exc:
                self._emit_transcript(job, job.text, "", f"Перевод недоступен: {exc}")

    def close(self):
        with self._lifecycle:
            if self._closing.is_set():
                return
            self._closing.set()
            self.router.stop()
            self._jobs.close()
            self._translations.close()
            if self._capture:
                self._capture.stop()
            if self._mic_capture:
                self._mic_capture.stop()
            for capture in self._captures:
                capture.stop()

    def release_resources(self):
        """Release model references only after native inference/capture has returned."""
        if not self._closing.is_set() or not self.quiescent:
            return False
        self._recognizer = self._translator = None
        self._capture = self._mic_capture = self._loader = None
        self._captures.clear()
        self._workers.clear()
        return True
