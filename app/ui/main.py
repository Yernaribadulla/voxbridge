import sys
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import (QApplication,QLabel,QVBoxLayout,QHBoxLayout,QWidget,
    QSystemTrayIcon,QMenu,QStyle,QPushButton,QMessageBox)
from app.audio.engine import AudioEngine
from app.config import load,save
from app.core.state import AudioRouter
from app.input_hook import MouseButtonHook
from app.ui.settings import SettingsDialog

class Overlay(QWidget):
    hotkey_toggle=Signal()
    hotkey_pause=Signal()
    def __init__(self):
        super().__init__(); self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.Tool)
        self.setWindowTitle('VoxBridge'); self.setMinimumSize(460,205); self.resize(500,225)
        self.setStyleSheet('QWidget{background:#16181d;color:#f2f4f8;border:1px solid #444;border-radius:8px} QLabel{padding:5px} QPushButton{background:#292d35;color:#f2f4f8;border:1px solid #484e59;border-radius:5px;padding:6px 10px} QPushButton:hover{background:#383e49}')
        self.direction=QLabel('VOXBRIDGE · ОСТАНОВЛЕНО'); self.direction.setStyleSheet('font-weight:bold;color:#9db7ff')
        self.original=QLabel('Распознанный текст появится здесь'); self.original.setWordWrap(True)
        self.translation=QLabel('Перевод'); self.translation.setWordWrap(True); self.translation.setStyleSheet('font-size:20px;font-weight:bold;color:#fff')
        self.status=QLabel('Настройте LM Studio и нажмите «Запустить».'); self.status.setWordWrap(True); self.status.setStyleSheet('color:#a9afba')
        self.start_btn=QPushButton('Запустить'); self.pause_btn=QPushButton('Пауза'); self.settings_btn=QPushButton('Настройки'); self.ptt_btn=QPushButton('Удерживать для ответа · RU → EN')
        row=QHBoxLayout(); row.addWidget(self.start_btn); row.addWidget(self.pause_btn); row.addWidget(self.settings_btn)
        layout=QVBoxLayout(self); layout.addWidget(self.direction); layout.addWidget(self.original); layout.addWidget(self.translation); layout.addWidget(self.status); layout.addLayout(row); layout.addWidget(self.ptt_btn)
        self._drag=None; self._last_sequence=-1; self.settings=load(); self.setWindowOpacity(self.settings.opacity)
        self.router=AudioRouter(); self.engine=self._new_engine(); self._wire_engine(self.engine)
        self.start_btn.clicked.connect(self.start_processing); self.pause_btn.clicked.connect(self.toggle_pause); self.settings_btn.clicked.connect(self.open_settings)
        self.ptt_btn.pressed.connect(self.engine.request_ptt); self.ptt_btn.released.connect(self.engine.request_release)
        self.hotkey_toggle.connect(self.toggle_visible); self.hotkey_pause.connect(self.toggle_pause)
        self.hook=MouseButtonHook(self.engine.request_ptt,self.engine.request_release,self.settings.ptt_button,self.hotkey_toggle.emit,self.hotkey_pause.emit)
        try: self.hook.start(); self.status.setText('Глобальная кнопка Mouse 5 подключена. Для старта нажмите «Запустить».')
        except Exception as exc: self.status.setText(f'Глобальный хук недоступен: {exc}. Можно удерживать кнопку в этом окне.')
    def _new_engine(self): return AudioEngine(self.router,self.settings)
    def _wire_engine(self,engine):
        engine.ptt_requested.connect(engine.begin_ptt); engine.ptt_released.connect(engine.finish_ptt)
        engine.signals.status.connect(self.status.setText); engine.signals.route.connect(self.direction.setText)
        engine.signals.error.connect(self.show_error); engine.signals.transcript.connect(self.show_transcript)
    def start_processing(self):
        if not self.settings.mic_device or not self.settings.system_device or not self.settings.translation_model:
            QMessageBox.information(self,'Нужно настроить VoxBridge','Выберите микрофон и системный звук, укажите ID загруженной модели LM Studio, затем сохраните настройки.')
            self.open_settings(); return
        answer=QMessageBox.question(self,'Запуск VoxBridge','При первом запуске Whisper может скачать выбранную модель. Продолжить?')
        if answer!=QMessageBox.Yes: return
        self.start_btn.setEnabled(False); self.engine.start()
    def toggle_pause(self):
        state=self.router.decision().state.name
        if state=='PAUSED': self.engine.resume(); self.pause_btn.setText('Пауза')
        elif state in ('LISTENING_PARTNER','PUSH_TO_TALK'): self.engine.pause(); self.pause_btn.setText('Продолжить')
    def open_settings(self):
        dialog=SettingsDialog(self.settings,self)
        if dialog.exec()!=dialog.Accepted or dialog.result_settings is None: return
        was_started=self.engine._started
        self.engine.close(); self.hook.stop(); self.settings=dialog.result_settings; save(self.settings)
        self.router=AudioRouter(); self.engine=self._new_engine(); self._wire_engine(self.engine)
        self.ptt_btn.pressed.disconnect(); self.ptt_btn.released.disconnect()
        self.ptt_btn.pressed.connect(self.engine.request_ptt); self.ptt_btn.released.connect(self.engine.request_release)
        self.hook=MouseButtonHook(self.engine.request_ptt,self.engine.request_release,self.settings.ptt_button,self.hotkey_toggle.emit,self.hotkey_pause.emit)
        try: self.hook.start()
        except Exception as exc: self.show_error(f'Хук кнопки мыши: {exc}')
        self.start_btn.setEnabled(True); self.start_btn.setText('Запустить снова' if was_started else 'Запустить')
        if was_started: self.start_btn.click()
    def show_transcript(self,sequence,source,text,translated,state):
        if sequence<self._last_sequence: return
        is_new=sequence>self._last_sequence; self._last_sequence=sequence
        self.original.setText(('Собеседник: ' if source=='partner' else 'Вы: ')+text)
        if is_new or translated: self.translation.setText(translated or 'Перевожу…')
        self.status.setText(state)
    def show_error(self,message):
        self.status.setText(message)
        if not self.engine._ready: self.start_btn.setEnabled(True)
    def toggle_visible(self): self.hide() if self.isVisible() else self.show()
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and event.position().y()<42: self._drag=event.globalPosition().toPoint()-self.frameGeometry().topLeft()
    def mouseMoveEvent(self,event):
        if self._drag is not None and event.buttons() & Qt.LeftButton: self.move(event.globalPosition().toPoint()-self._drag)
    def mouseReleaseEvent(self,event): self._drag=None
    def closeEvent(self,event):
        self.hook.stop(); self.engine.close(); event.accept()
    def safe_exit(self): self.close(); QApplication.quit()

def run():
    app=QApplication(sys.argv); app.setQuitOnLastWindowClosed(False); overlay=Overlay(); tray=QSystemTrayIcon(app.style().standardIcon(QStyle.SP_ComputerIcon),app)
    menu=QMenu(); menu.addAction('Показать / скрыть',overlay.toggle_visible); menu.addAction('Пауза / продолжить',overlay.toggle_pause); menu.addAction('Настройки',overlay.open_settings); menu.addSeparator(); menu.addAction('Выход',overlay.safe_exit); tray.setContextMenu(menu); tray.show(); overlay.show()
    return app.exec()
