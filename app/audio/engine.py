from __future__ import annotations
import itertools
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from PySide6.QtCore import QObject, Signal
from app.audio.capture import CaptureThread
from app.speech.whisper import WhisperRecognizer
from app.translation.lmstudio import LMStudioProvider

class EngineSignals(QObject):
    status=Signal(str)
    route=Signal(str)
    transcript=Signal(int,str,str,str,str)
    error=Signal(str)

@dataclass
class SpeechJob:
    source:str
    generation:int
    audio:object
    sequence:int

class AudioEngine(QObject):
    ptt_requested=Signal(int)
    ptt_released=Signal(int)
    """Owns capture, single-model speech inference, and asynchronous local translation."""
    def __init__(self,router,settings):
        super().__init__(); self.router=router; self.settings=settings; self.signals=EngineSignals()
        self._jobs=queue.PriorityQueue(maxsize=24); self._sequence=itertools.count(); self._job_sequence=itertools.count()
        self._capture=None; self._mic_capture=None; self._mic_generation=None; self._started=False; self._ready=False; self._closing=threading.Event()
        self._recognizer=WhisperRecognizer(settings.user_model,settings.compute_device,settings.compute_type)
        self._translator=LMStudioProvider(settings.translation_url,settings.translation_model,timeout=8)
        self._translation_pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='voxbridge-translate')
        self._processor=threading.Thread(target=self._process,name='voxbridge-recognition',daemon=True); self._processor.start()
        self._last_translation_failure=0.0
    def start(self):
        if self._started: return
        self._started=True; self.signals.status.emit(f"Загрузка Whisper {self.settings.user_model}. При первом запуске модель скачивается локально.")
        threading.Thread(target=self._load_and_listen,name='voxbridge-model-load',daemon=True).start()
    def _load_and_listen(self):
        try:
            self._recognizer.load()
            if self._closing.is_set(): return
            self._ready=True
            if self.router.decision().state.name=='STARTING': self.router.start()
            self._capture=CaptureThread('partner',self.settings.system_device,self.router.decision().generation,self.router,self._submit,self.signals.error.emit)
            self._capture.start(); self.signals.route.emit('PARTNER · EN → RU'); self.signals.status.emit('Слушаю системный звук. Удерживайте Mouse 5 для ответа.')
        except Exception as exc:
            self.signals.error.emit(f'Не удалось загрузить Whisper: {exc}')
    def request_ptt(self):
        if not self._ready: return
        before=self.router.decision()
        decision=self.router.press()
        if decision.state.name=='PUSH_TO_TALK' and before.state.name!='PUSH_TO_TALK': self.ptt_requested.emit(decision.generation)
    def begin_ptt(self,generation):
        if self.router.decision().generation!=generation or self.router.decision().state.name!='PUSH_TO_TALK': return
        if self._mic_capture: self._mic_capture.stop()
        self._mic_capture=None; self._mic_generation=generation
        self.signals.route.emit('YOU · RU → EN · ПРИОРИТЕТ МИКРОФОНА')
        self.signals.status.emit('Микрофон активен. Говорите по-русски…')
        if self.settings.mic_device:
            self._mic_capture=CaptureThread('microphone',self.settings.mic_device,generation,self.router,self._submit,self.signals.error.emit)
            self._mic_capture.start()
        else: self.signals.error.emit('Микрофон не выбран. Откройте настройки VoxBridge.')
    def request_release(self):
        decision=self.router.release()
        if decision.state.name=='FINALIZING_USER_SPEECH': self.ptt_released.emit(decision.generation)
    def finish_ptt(self,generation):
        if self._mic_generation==generation:
            mic=self._mic_capture; self._mic_capture=None; self._mic_generation=None
            if mic: mic.stop()
        route=self.router.decision()
        if route.generation==generation and route.state.name=='FINALIZING_USER_SPEECH':
            self.router.partner_resumed(); self.signals.route.emit('PARTNER · EN → RU'); self.signals.status.emit('Снова слушаю системный звук.')
    def pause(self):
        if self._mic_capture: self._mic_capture.stop(); self._mic_capture=None
        self.router.pause(); self.signals.route.emit('ПАУЗА'); self.signals.status.emit('Обработка аудио приостановлена.')
    def resume(self):
        self.router.start(); self.signals.route.emit('PARTNER · EN → RU'); self.signals.status.emit('Слушаю системный звук.')
    def _submit(self,source,generation,audio):
        if self._closing.is_set() or not self.router.accepts_result(source,generation): return
        job=SpeechJob(source,generation,audio,next(self._job_sequence))
        # PriorityQueue uses lower values first. Mic jobs outrank queued partner work.
        try: self._jobs.put_nowait((0 if source=='microphone' else 1,next(self._sequence),job))
        except queue.Full:
            if source=='microphone':
                try: self._jobs.get_nowait(); self._jobs.put_nowait((0,next(self._sequence),job))
                except (queue.Empty,queue.Full): self.signals.error.emit('Очередь распознавания занята; фрагмент микрофона пропущен.')
    def _process(self):
        while not self._closing.is_set():
            try: _,_,job=self._jobs.get(timeout=.25)
            except queue.Empty: continue
            if not self.router.accepts_result(job.source,job.generation): continue
            try:
                self.signals.status.emit('Распознаю речь…')
                language='ru' if job.source=='microphone' else 'en'
                text=self._recognizer.transcribe(job.audio,language=language)
                if not text or not self.router.accepts_result(job.source,job.generation): continue
                direction='ru_en' if job.source=='microphone' else 'en_ru'
                self.signals.transcript.emit(job.sequence,job.source,text,'','Распознано · перевод…')
                self._translation_pool.submit(self._translate,job,direction,text)
            except Exception as exc:
                self.signals.error.emit(f'Ошибка распознавания: {exc}')
    def _translate(self,job,direction,text):
        if not self.router.accepts_result(job.source,job.generation): return
        if not self.settings.translation_model:
            self.signals.transcript.emit(job.sequence,job.source,text,'','Укажите ID модели LM Studio в настройках.')
            return
        try:
            translated=self._translator.translate(text,direction)
            if not self.router.accepts_result(job.source,job.generation): return
            if not translated: raise ValueError('LM Studio вернула пустой перевод')
            self.signals.transcript.emit(job.sequence,job.source,text,translated,'Переведено')
        except Exception as exc:
            if self.router.accepts_result(job.source,job.generation): self.signals.transcript.emit(job.sequence,job.source,text,'',f'Ошибка перевода: {exc}')
    def close(self):
        self._closing.set(); self.router.stop()
        if self._capture: self._capture.stop()
        if self._mic_capture: self._mic_capture.stop()
        self._translation_pool.shutdown(wait=False,cancel_futures=True)
