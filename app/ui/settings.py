"""Settings UI; all network testing is explicit and runs outside the GUI thread."""

import threading
from dataclasses import replace
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QDialogButtonBox,
    QPushButton,
    QLabel,
    QHBoxLayout,
    QDoubleSpinBox,
    QSpinBox,
)
from app.audio.capture import input_devices, output_devices
from app.config import validate_endpoint
from app.translation.lmstudio import LMStudioProvider


class _TestResult(QObject):
    finished = Signal(str)


class SettingsDialog(QDialog):
    def __init__(self, current, parent=None, *, preview=False):
        super().__init__(parent)
        self._current = current
        self.preview = preview
        self.result_settings = None
        self.setWindowTitle("Настройки VoxBridge")
        self.setMinimumSize(600, 550)
        self.resize(680, 620)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)
        title = QLabel("Ваш голос. Ваши настройки.")
        title.setStyleSheet("font-size:22px;font-weight:600")
        root.addWidget(title)
        note = QLabel(
            "Whisper распознаёт речь на ПК. Текст получает только указанный ниже сервер перевода."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#b4bfd0")
        root.addWidget(note)
        form = QFormLayout()
        form.setSpacing(12)
        root.addLayout(form)
        self.endpoint = QLineEdit(current.translation_url)
        self.model = QLineEdit(current.translation_model)
        self.model.setPlaceholderText("ID загруженной модели LM Studio")
        self.mic = self._devices(
            (lambda: [("Демо микрофон", "preview-mic")]) if preview else input_devices,
            current.mic_device,
        )
        self.speaker = self._devices(
            (lambda: [("Демо системный звук", "preview-speaker")])
            if preview
            else output_devices,
            current.system_device,
        )
        self.whisper = self._combo(
            [("base · быстрее", "base"), ("small · точнее", "small")],
            current.user_model,
        )
        self.device = self._combo(
            [("CPU", "cpu"), ("NVIDIA CUDA", "cuda")], current.compute_device
        )
        self.compute = self._combo(
            [
                ("int8", "int8"),
                ("float16", "float16"),
                ("int8_float16", "int8_float16"),
            ],
            current.compute_type,
        )
        self.button = self._combo(
            [("Mouse 5 / X2", "x2"), ("Mouse 4 / X1", "x1")], current.ptt_button
        )
        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0.35, 1.0)
        self.opacity.setSingleStep(0.05)
        self.opacity.setValue(current.opacity)
        self.font_size = QSpinBox()
        self.font_size.setRange(14, 28)
        self.font_size.setSuffix(" px")
        self.font_size.setValue(current.font_size)
        for name, widget in [
            ("LM Studio API", self.endpoint),
            ("Модель перевода", self.model),
            ("Микрофон", self.mic),
            ("Системный звук", self.speaker),
            ("Whisper · RU + EN", self.whisper),
            ("Вычисления", self.device),
            ("Точность вычислений", self.compute),
            ("Push-to-talk", self.button),
            ("Непрозрачность", self.opacity),
            ("Размер субтитров", self.font_size),
        ]:
            widget.setAccessibleName(name)
            form.addRow(name, widget)
        self.device.currentIndexChanged.connect(self._compute_options)
        self._compute_options()
        self._test_result = _TestResult()
        self._test_result.finished.connect(self._show_test)
        self.test_status = QLabel(
            "Preview: настройки не сохраняются." if preview else ""
        )
        self.test_status.setTextFormat(Qt.PlainText)
        self.test_status.setWordWrap(True)
        self.test_btn = QPushButton("Проверить соединение")
        self.test_btn.setEnabled(not preview)
        self.test_btn.clicked.connect(self.test_connection)
        row = QHBoxLayout()
        row.addWidget(self.test_btn)
        row.addWidget(self.test_status, 1)
        root.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def _combo(items, selected):
        combo = QComboBox()
        for name, value in items:
            combo.addItem(name, value)
        combo.setCurrentIndex(max(0, combo.findData(selected)))
        return combo

    @staticmethod
    def _devices(loader, selected):
        combo = QComboBox()
        combo.addItem("Выберите устройство", "")
        try:
            for name, device_id in loader():
                combo.addItem(name, device_id)
        except Exception:
            combo.setToolTip(
                "Не удалось получить список устройств. Проверьте аудиодрайвер."
            )
        index = combo.findData(selected)
        if selected and index < 0:
            combo.addItem("Сохранённое устройство недоступно", selected)
            index = combo.count() - 1
        combo.setCurrentIndex(max(0, index))
        return combo

    def _compute_options(self):
        cpu = self.device.currentData() == "cpu"
        if cpu:
            self.compute.setCurrentIndex(self.compute.findData("int8"))
        self.compute.setEnabled(not cpu)

    def test_connection(self):
        try:
            endpoint = validate_endpoint(self.endpoint.text().strip())
        except ValueError as exc:
            self.test_status.setText(str(exc))
            return
        self.test_btn.setEnabled(False)
        self.test_status.setText("Подключаюсь…")
        model, signals = self.model.text().strip(), self._test_result

        def work():
            try:
                ids = LMStudioProvider(endpoint, model, timeout=5).test_connection()
                message = (
                    "Модель найдена. Можно запускать."
                    if model and model in ids
                    else "Сервер доступен. Выберите ID: " + ", ".join(ids[:5])
                )
            except Exception as exc:
                message = str(exc)
            signals.finished.emit(message)

        threading.Thread(
            target=work, name="voxbridge-connection-test", daemon=True
        ).start()

    def _show_test(self, message):
        self.test_status.setText(message)
        self.test_btn.setEnabled(True)

    def accept(self):
        try:
            endpoint = validate_endpoint(self.endpoint.text().strip())
        except ValueError as exc:
            self.test_status.setText(str(exc))
            return
        self.result_settings = replace(
            self._current,
            translation_url=endpoint,
            translation_model=self.model.text().strip(),
            mic_device=self.mic.currentData() or "",
            system_device=self.speaker.currentData() or "",
            user_model=self.whisper.currentData(),
            partner_model=self.whisper.currentData(),
            compute_device=self.device.currentData(),
            compute_type=self.compute.currentData(),
            ptt_button=self.button.currentData(),
            opacity=self.opacity.value(),
            font_size=self.font_size.value(),
        )
        super().accept()
