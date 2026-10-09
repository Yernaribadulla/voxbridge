import threading
from dataclasses import replace
from PySide6.QtCore import QObject,Signal
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QLineEdit,QComboBox,
    QDialogButtonBox,QPushButton,QLabel,QHBoxLayout)
from app.audio.capture import input_devices,output_devices
from app.config import Settings
from app.translation.lmstudio import LMStudioProvider

class _TestResult(QObject): finished=Signal(str)

class SettingsDialog(QDialog):
    def __init__(self,current,parent=None):
        super().__init__(parent); self._current=current; self.setWindowTitle('Настройки VoxBridge'); self.resize(520,300); self.result_settings=None
        root=QVBoxLayout(self); form=QFormLayout(); root.addLayout(form)
        self.endpoint=QLineEdit(current.translation_url); self.model=QLineEdit(current.translation_model); self.model.setPlaceholderText('ID модели из списка LM Studio')
        self.mic=self._devices(input_devices,current.mic_device,'Микрофон недоступен')
        self.speaker=self._devices(output_devices,current.system_device,'Выходное устройство недоступно')
        self.whisper=QComboBox(); self.whisper.addItem('base — быстрее, мультиязычная','base'); self.whisper.addItem('small — точнее, требует больше ресурсов','small'); self.whisper.setCurrentIndex(max(0,self.whisper.findData(current.user_model)))
        self.device=QComboBox(); self.device.addItem('CPU','cpu'); self.device.addItem('NVIDIA CUDA','cuda'); self.device.setCurrentIndex(max(0,self.device.findData(current.compute_device)))
        self.compute=QComboBox(); self.compute.addItem('int8','int8'); self.compute.addItem('float16','float16'); self.compute.addItem('int8_float16','int8_float16'); self.compute.setCurrentIndex(max(0,self.compute.findData(current.compute_type)))
        self.button=QComboBox(); self.button.addItem('Mouse 5 / X2','x2'); self.button.addItem('Mouse 4 / X1','x1'); self.button.setCurrentIndex(max(0,self.button.findData(current.ptt_button)))
        form.addRow('LM Studio API',self.endpoint); form.addRow('ID модели перевода',self.model); form.addRow('Микрофон',self.mic); form.addRow('Системный звук',self.speaker); form.addRow('Whisper (русский + английский)',self.whisper); form.addRow('Устройство вычислений',self.device); form.addRow('Тип вычислений',self.compute); form.addRow('Кнопка push-to-talk',self.button)
        self.result=_TestResult(); self.result.finished.connect(self._show_test); self.test_status=QLabel(''); test_row=QHBoxLayout(); self.test_btn=QPushButton('Проверить LM Studio'); self.test_btn.clicked.connect(self.test_connection); test_row.addWidget(self.test_btn); test_row.addWidget(self.test_status,1); root.addLayout(test_row)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
    @staticmethod
    def _devices(loader,selected,missing):
        combo=QComboBox()
        try:
            rows=loader()
            for name,device_id in rows: combo.addItem(name,device_id)
        except Exception: pass
        if combo.count()==0: combo.addItem(missing,'')
        index=combo.findData(selected)
        if index>=0: combo.setCurrentIndex(index)
        return combo
    def test_connection(self):
        self.test_btn.setEnabled(False); self.test_status.setText('Подключаюсь…')
        endpoint=self.endpoint.text().strip(); model=self.model.text().strip(); signals=self.result
        def work():
            try:
                ids=LMStudioProvider(endpoint,model,timeout=5).test_connection()
                msg=('Модель найдена' if model and model in ids else 'Сервер доступен, модель не найдена. ID: '+', '.join(ids[:5]))
            except Exception as exc: msg=f'Ошибка: {exc}'
            signals.finished.emit(msg)
        threading.Thread(target=work,name='voxbridge-connection-test',daemon=True).start()
    def _show_test(self,message): self.test_status.setText(message); self.test_btn.setEnabled(True)
    def accept(self):
        if not self.endpoint.text().strip(): self.test_status.setText('Укажите API endpoint.'); return
        self.result_settings=replace(self._current,translation_url=self.endpoint.text().strip(),translation_model=self.model.text().strip(),mic_device=self.mic.currentData() or '',system_device=self.speaker.currentData() or '',user_model=self.whisper.currentData(),partner_model=self.whisper.currentData(),compute_device=self.device.currentData(),compute_type=self.compute.currentData(),ptt_button=self.button.currentData())
        super().accept()
