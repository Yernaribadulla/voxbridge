"""Compact Windows overlay. Presentation never decides audio routing priority."""

import sys
from pathlib import Path
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QSystemTrayIcon,
    QMenu,
    QStyle,
    QPushButton,
    QMessageBox,
    QFrame,
    QGraphicsOpacityEffect,
    QDialog,
)
from app.audio.engine import AudioEngine, TranscriptResult
from app.config import Settings, load, save
from app.core.state import AudioRouter, State
from app.core.results import ResultGate
from app.input_hook import MouseButtonHook
from app.ui.settings import SettingsDialog
from app.ui.widgets import TwoLineLabel


class Overlay(QWidget):
    hotkey_toggle = Signal()
    hotkey_pause = Signal()

    def __init__(self, *, preview=False):
        super().__init__()
        self.preview = preview
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("VoxBridge · Preview" if preview else "VoxBridge")
        self.setFont(QFont("Segoe UI", 10))
        self.setMinimumSize(640, 360)
        self.resize(880, 360)
        self.setFixedHeight(360)
        self.setStyleSheet(
            Path(__file__).with_name("theme.qss").read_text(encoding="utf-8-sig")
        )
        self.settings = (
            Settings(mic_device="preview-mic", system_device="preview-speaker")
            if preview
            else load()
        )
        self.setWindowOpacity(1.0 if preview else self.settings.opacity)
        self._drag = None
        self._last_generation = -1
        self._retired = []
        self._closed = False
        self.router = AudioRouter()
        self.engine = self._new_engine()
        self._result_gate = ResultGate(self.engine.id)
        self.hook = None
        self._build_ui()
        self._wire_engine()
        self.fade_timer = QTimer(self)
        self.fade_timer.setSingleShot(True)
        self.fade_timer.setInterval(6500)
        self.fade_timer.timeout.connect(self._fade_text)
        self.fade_animation = QPropertyAnimation(self.text_effect, b"opacity", self)
        self.fade_animation.setDuration(500)
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.15)
        self.fade_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.retire_timer = QTimer(self)
        self.retire_timer.setInterval(300)
        self.retire_timer.timeout.connect(self._collect_retired)
        self.hotkey_toggle.connect(self.toggle_visible)
        self.hotkey_pause.connect(self.start_or_pause)
        self._connect_ptt()
        self.start_btn.clicked.connect(self.start_or_pause)
        self.settings_btn.clicked.connect(self.open_settings)
        self.hide_btn.clicked.connect(self.close if preview else self.hide)
        if preview:
            self.hide_btn.setText("×")
            self.hide_btn.setAccessibleName("Закрыть preview")
            self.hide_btn.setToolTip("Закрыть preview")
        self._apply_font()
        if preview:
            self.original.set_full_text(
                "Hold the bridge. I’m on my way — let’s move together."
            )
            self.translation.set_full_text(
                "Удерживай мост. Я уже иду — давай двигаться вместе."
            )
            self.state_label.setText("ДЕМОНСТРАЦИЯ")
            self.status.setText(
                "Preview · звук не захватывается, модели не загружаются"
            )
        else:
            self._start_hook()
        self._update_controls()

    def _build_ui(self):
        self.panel = QWidget(self)
        self.panel.setObjectName("panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.panel)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)
        header = QHBoxLayout()
        self.brand = QLabel("VOXBRIDGE")
        self.brand.setObjectName("brand")
        self.state_label = QLabel("ГОТОВ К НАСТРОЙКЕ")
        self.state_label.setObjectName("state")
        header.addWidget(self.brand)
        header.addSpacing(12)
        header.addWidget(self.state_label)
        header.addStretch(1)
        self.start_btn = QPushButton("Запустить")
        self.start_btn.setAccessibleName("Запуск или пауза")
        self.settings_btn = QPushButton("Настройки")
        self.hide_btn = QPushButton("—")
        self.hide_btn.setFixedWidth(36)
        self.hide_btn.setAccessibleName("Скрыть в трей")
        self.hide_btn.setToolTip("Скрыть · Ctrl+Shift+V вернёт окно")
        for button in (self.start_btn, self.settings_btn, self.hide_btn):
            header.addWidget(button)
        layout.addLayout(header)
        self.content = QWidget()
        text_layout = QVBoxLayout(self.content)
        text_layout.setContentsMargins(0, 2, 0, 2)
        text_layout.setSpacing(5)
        self.original_meta = QLabel("СОБЕСЕДНИК  /  EN")
        self.original_meta.setObjectName("caption")
        self.translation_meta = QLabel("ПЕРЕВОД  /  RU")
        self.translation_meta.setObjectName("caption")
        self.original = TwoLineLabel()
        self.original.setObjectName("sourceText")
        self.original.setAccessibleName("Исходная речь")
        self.translation = TwoLineLabel()
        self.translation.setObjectName("translationText")
        self.translation.setAccessibleName("Перевод речи")
        self.original.setMinimumHeight(55)
        self.translation.setMinimumHeight(62)
        self.original.set_full_text("Здесь появится речь собеседника.")
        self.translation.set_full_text(
            "Перевод будет рядом — без переключения из игры."
        )
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        text_layout.addWidget(self.original_meta)
        text_layout.addWidget(self.original, 1)
        text_layout.addWidget(divider)
        text_layout.addWidget(self.translation_meta)
        text_layout.addWidget(self.translation, 1)
        self.text_effect = QGraphicsOpacityEffect(self.content)
        self.content.setGraphicsEffect(self.text_effect)
        layout.addWidget(self.content, 1)
        self.status = QLabel("Выберите устройства и модель LM Studio в настройках.")
        self.status.setObjectName("status")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.ptt_btn = QPushButton()
        self.ptt_btn.setObjectName("ptt")
        self.ptt_btn.setMinimumHeight(46)
        self.ptt_btn.setProperty("active", False)
        self.ptt_btn.setAccessibleName("Удерживать для ответа")
        layout.addWidget(self.ptt_btn)
        self._set_ptt_active(False)

    def _new_engine(self):
        return AudioEngine(self.router, self.settings)

    def _wire_engine(self):
        engine = self.engine
        engine.ptt_requested.connect(engine.begin_ptt)
        engine.ptt_released.connect(engine.finish_ptt)
        engine.signals.status.connect(self._on_status)
        engine.signals.route.connect(self._on_route)
        engine.signals.error.connect(self._on_error)
        engine.signals.transcript.connect(self.show_transcript)

    def _connect_ptt(self):
        self.ptt_btn.pressed.connect(self.engine.request_ptt)
        self.ptt_btn.released.connect(self.engine.request_release)

    def _start_hook(self):
        self.hook = MouseButtonHook(
            self.engine.request_ptt,
            self.engine.request_release,
            self.settings.ptt_button,
            self.hotkey_toggle.emit,
            self.hotkey_pause.emit,
        )
        try:
            self.hook.start()
        except Exception:
            self.status.setText(
                "Глобальные клавиши недоступны. Используйте кнопки окна."
            )

    def _apply_font(self):
        self.original.setStyleSheet(f"font-size:{self.settings.font_size}px")
        self.translation.setStyleSheet(f"font-size:{self.settings.font_size}px")

    def _update_controls(self):
        state = self.router.decision().state
        loading = (
            self.engine.started and not self.engine.ready and state is not State.ERROR
        )
        active = state in (
            State.LISTENING_PARTNER,
            State.PUSH_TO_TALK,
            State.FINALIZING_USER_SPEECH,
        )
        self.start_btn.setText(
            "Загрузка…"
            if loading
            else (
                "Пауза"
                if active
                else ("Продолжить" if state is State.PAUSED else "Запустить")
            )
        )
        self.start_btn.setEnabled(
            not self.preview and not loading and not self._retired
        )
        self.ptt_btn.setEnabled(
            not self.preview
            and self.engine.ready
            and state not in (State.PAUSED, State.ERROR, State.STOPPING)
        )

    @Slot()
    def start_or_pause(self):
        if self.preview or self._closed or self._retired:
            return
        state = self.router.decision().state
        if state is State.PAUSED:
            self.engine.resume()
        elif state in (
            State.LISTENING_PARTNER,
            State.PUSH_TO_TALK,
            State.FINALIZING_USER_SPEECH,
        ):
            self.engine.pause()
        elif not self.engine.started:
            self.start_processing()
        self._update_controls()

    def start_processing(self):
        if (
            not self.settings.mic_device
            or not self.settings.system_device
            or not self.settings.translation_model
        ):
            QMessageBox.information(
                self,
                "Первый запуск",
                "Выберите микрофон, системный звук и ID модели LM Studio.",
            )
            self.open_settings()
            return
        if (
            QMessageBox.question(
                self,
                "Запуск Whisper",
                "При первом запуске выбранная модель Whisper скачивается на ПК. Продолжить?",
            )
            == QMessageBox.Yes
        ):
            self.engine.start()
            self._update_controls()

    def _current(self, event):
        return (
            not self._closed
            and event.engine_id == self.engine.id
            and event.generation == self.router.decision().generation
        )

    @Slot(object)
    def _on_status(self, event):
        if self._current(event):
            self.status.setText(event.message)
            self.status.setToolTip(event.message)
            self._update_controls()

    @Slot(object)
    def _on_error(self, event):
        if self._current(event):
            self.status.setText(event.message)
            self.status.setToolTip(event.message)
            self._update_controls()

    @Slot(str)
    def _on_route(self, engine_id):
        if self._closed or engine_id != self.engine.id:
            return
        route = self.router.decision()
        states = {
            State.STARTING: "ЗАПУСК",
            State.LISTENING_PARTNER: "СЛУШАЮ СОБЕСЕДНИКА",
            State.PUSH_TO_TALK: "ВАШ МИКРОФОН",
            State.FINALIZING_USER_SPEECH: "ЗАВЕРШАЮ ОТВЕТ",
            State.PAUSED: "ПАУЗА",
            State.ERROR: "ОШИБКА",
            State.STOPPING: "ОСТАНОВЛЕНО",
        }
        self.state_label.setText(states[route.state])
        user = route.state is State.PUSH_TO_TALK
        if route.generation != self._last_generation:
            self._last_generation = route.generation
            self.fade_timer.stop()
            self.fade_animation.stop()
            self.text_effect.setOpacity(1.0)
            self.original.set_full_text(
                "Говорите по-русски…" if user else "Ожидаю следующую реплику…"
            )
            self.translation.set_full_text("")
        self.original_meta.setText("ВЫ  /  RU" if user else "СОБЕСЕДНИК  /  EN")
        self.translation_meta.setText("ПЕРЕВОД  /  EN" if user else "ПЕРЕВОД  /  RU")
        self._set_ptt_active(user)
        self._update_controls()

    def _set_ptt_active(self, active):
        button = "Mouse 4" if self.settings.ptt_button == "x1" else "Mouse 5"
        self.ptt_btn.setProperty("active", active)
        self.ptt_btn.style().unpolish(self.ptt_btn)
        self.ptt_btn.style().polish(self.ptt_btn)
        self.ptt_btn.setText(
            f"●  МИКРОФОН АКТИВЕН   ·   Отпустите {button}, чтобы закончить"
            if active
            else f"🎙  Удерживайте {button} или эту кнопку   ·   RU → EN"
        )

    @Slot(object)
    def show_transcript(self, event: TranscriptResult):
        if self._closed or not self._result_gate.accept(event, self.router):
            return
        self.fade_animation.stop()
        self.text_effect.setOpacity(1.0)
        self.original_meta.setText(
            "СОБЕСЕДНИК  /  EN" if event.source == "partner" else "ВЫ  /  RU"
        )
        self.translation_meta.setText(
            "ПЕРЕВОД  /  RU" if event.source == "partner" else "ПЕРЕВОД  /  EN"
        )
        self.original.set_full_text(event.text)
        self.translation.set_full_text(
            event.translated
            or (
                "Перевод недоступен"
                if event.status.startswith("Перевод недоступен")
                else "Перевожу…"
            )
        )
        self.status.setText(event.status)
        self.status.setToolTip(event.status)
        self.fade_timer.start()

    def _fade_text(self):
        self.fade_animation.setStartValue(self.text_effect.opacity())
        self.fade_animation.start()

    @Slot()
    def open_settings(self):
        dialog = SettingsDialog(self.settings, self, preview=self.preview)
        if (
            dialog.exec() != QDialog.Accepted
            or dialog.result_settings is None
            or self.preview
        ):
            return
        try:
            save(dialog.result_settings)
        except OSError as exc:
            QMessageBox.warning(self, "Не удалось сохранить", str(exc))
            return
        old = self.engine
        old.close()
        if self.hook:
            self.hook.stop()
        self._retired.append(old)
        self.settings = dialog.result_settings
        self.router = AudioRouter()
        self.engine = self._new_engine()
        self._result_gate = ResultGate(self.engine.id)
        self._wire_engine()
        self.ptt_btn.pressed.disconnect()
        self.ptt_btn.released.disconnect()
        self._connect_ptt()
        self._last_generation = -1
        self.setWindowOpacity(self.settings.opacity)
        self._apply_font()
        self._start_hook()
        self._on_route(self.engine.id)
        self.status.setText("Настройки сохранены. Нажмите «Запустить».")
        self.retire_timer.start()
        self._collect_retired()

    def _collect_retired(self):
        keep = []
        for engine in self._retired:
            if engine.quiescent:
                engine.release_resources()
                engine.deleteLater()
            else:
                keep.append(engine)
        self._retired = keep
        if not keep:
            self.retire_timer.stop()
            if self.router.decision().state is State.STARTING:
                self.status.setText("Настройки сохранены. Нажмите «Запустить».")
        else:
            self.status.setText(
                "Завершаю прежние задачи. Запуск станет доступен после их завершения."
            )
        self._update_controls()

    @Slot()
    def toggle_visible(self):
        self.hide() if self.isVisible() else self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 62:
            self._drag = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event):
        self._drag = None

    def closeEvent(self, event):
        self._closed = True
        self.fade_timer.stop()
        self.retire_timer.stop()
        if self.hook:
            self.hook.stop()
        self.engine.close()
        for engine in self._retired:
            engine.close()
        event.accept()

    def safe_exit(self):
        self.close()
        QApplication.quit()


def run():
    import argparse

    parser = argparse.ArgumentParser(
        description="VoxBridge · локальный голосовой переводчик"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Показать демо без аудио, хуков и моделей",
    )
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("VoxBridge")
    app.setQuitOnLastWindowClosed(args.preview)
    overlay = Overlay(preview=args.preview)
    tray = None
    if not args.preview and QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(app.style().standardIcon(QStyle.SP_ComputerIcon), app)
        menu = QMenu()
        menu.addAction("Показать / скрыть", overlay.toggle_visible)
        menu.addAction("Запуск / пауза", overlay.start_or_pause)
        menu.addAction("Настройки", overlay.open_settings)
        menu.addSeparator()
        menu.addAction("Выход", overlay.safe_exit)
        tray.setContextMenu(menu)
        tray.setToolTip("VoxBridge · Ctrl+Shift+V")
        tray.show()
    elif not args.preview:
        overlay.hide_btn.hide()
        app.setQuitOnLastWindowClosed(True)
    app.aboutToQuit.connect(overlay.close)
    overlay.show()
    return app.exec()
