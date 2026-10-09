import sys
from PySide6.QtCore import Qt,Signal,QTimer,QPropertyAnimation,QEasingCurve
from PySide6.QtGui import QFontMetrics,QFont
from PySide6.QtWidgets import (QApplication,QLabel,QVBoxLayout,QHBoxLayout,QWidget,
    QSystemTrayIcon,QMenu,QStyle,QPushButton,QMessageBox,QFrame,QGraphicsOpacityEffect)
from app.audio.engine import AudioEngine
from app.config import load,save
from app.core.state import AudioRouter
from app.input_hook import MouseButtonHook
from app.ui.settings import SettingsDialog

class TwoLineLabel(QLabel):
    """Wrap arbitrary text to at most two complete lines with an ellipsis."""
    def __init__(self,parent=None):
        super().__init__(parent); self._full_text=''; self.setWordWrap(False); self.setAlignment(Qt.AlignVCenter|Qt.AlignLeft)
    def set_full_text(self,text): self._full_text=text or ''; self._layout_text()
    def resizeEvent(self,event): super().resizeEvent(event); self._layout_text()
    def changeEvent(self,event): super().changeEvent(event); self._layout_text()
    def _layout_text(self):
        if not hasattr(self,'_full_text'): return
        text=self._full_text; width=max(1,self.contentsRect().width()); metrics=QFontMetrics(self.font())
        if not text: self.setText(''); return
        words=text.split(); lines=[]; line=''; overflow=False
        if not words: self.setText(''); return
        for index,word in enumerate(words):
            candidate=(line+' '+word).strip()
            if metrics.horizontalAdvance(candidate)<=width:
                line=candidate; continue
            if line: lines.append(line); line=''
            if len(lines)>=2:
                overflow=True; break
            if metrics.horizontalAdvance(word)>width:
                word=metrics.elidedText(word,Qt.ElideRight,width); overflow=True
            line=word
            if overflow: break
        if line and len(lines)<2: lines.append(line)
        if index<len(words)-1: overflow=True
        if overflow and lines: lines[-1]=metrics.elidedText(lines[-1]+'…',Qt.ElideRight,width)
        self.setText('\n'.join(lines[:2]))

class Overlay(QWidget):
    hotkey_toggle=Signal()
    hotkey_pause=Signal()
    def __init__(self):
        super().__init__(); self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground,True); self.setWindowTitle('VoxBridge')
        self.setFont(QFont('Segoe UI',10))
        self.setMinimumSize(650,330); self.resize(900,330); self.setFixedHeight(330)
        self.setStyleSheet('''
            QWidget#panel{background:rgba(15,19,27,238);color:#f1f3f8;border:1px solid #78889d;border-radius:17px}
            QLabel{border:0;background:transparent}
            QPushButton{background:transparent;color:#d5dbea;border:0;border-radius:8px;padding:4px 9px}
            QPushButton:hover{background:rgba(255,255,255,24)}
            QLabel#heading{font-size:18px;font-weight:700;letter-spacing:1px;color:#aebbd0}
            QLabel#meta{font-size:15px;color:#a9b2c2}
            QLabel#body{font-size:23px;color:#f2f3f7}
            QFrame#divider{background:rgba(177,190,210,75);border:0;max-height:1px}
            QPushButton#ptt{font-size:17px;color:#aeb8c9;text-align:left;padding-left:15px;border-top:1px solid rgba(177,190,210,65);border-radius:0}
            QPushButton#ptt[active="true"]{background:rgba(36,190,105,48);color:#63f29a;border-top:2px solid #43e987;font-weight:700}
        ''')
        self.panel=QWidget(self); self.panel.setObjectName('panel')
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.addWidget(self.panel)
        layout=QVBoxLayout(self.panel); layout.setContentsMargins(21,12,21,9); layout.setSpacing(5)
        header=QHBoxLayout(); header.setSpacing(9)
        self.led=QLabel('●'); self.led.setStyleSheet('color:#727b89;font-size:17px;border:0;background:transparent')
        self.heading=QLabel('VOXBRIDGE · ОСТАНОВЛЕНО'); self.heading.setObjectName('heading')
        header.addWidget(self.led); header.addWidget(self.heading); header.addStretch(1)
        self.start_btn=QPushButton('▶'); self.start_btn.setToolTip('Запустить / пауза'); self.start_btn.setFixedSize(36,34)
        self.settings_btn=QPushButton('⚙'); self.settings_btn.setToolTip('Настройки'); self.settings_btn.setFixedSize(38,34)
        header.addWidget(self.start_btn); header.addWidget(self.settings_btn); layout.addLayout(header)

        self.content=QWidget(); self.content.setStyleSheet('background:transparent;border:0')
        content_layout=QVBoxLayout(self.content); content_layout.setContentsMargins(2,3,2,3); content_layout.setSpacing(5)
        original_head=QHBoxLayout(); original_head.addStretch(1)
        self.original_meta=QLabel('▂▅▇▅▃   EN · Собеседник'); self.original_meta.setObjectName('meta'); original_head.addWidget(self.original_meta)
        self.original=TwoLineLabel(); self.original.setObjectName('body'); self.original.setFixedHeight(58)
        content_layout.addLayout(original_head); content_layout.addWidget(self.original)
        divider=QFrame(); divider.setObjectName('divider'); divider.setFixedHeight(1); content_layout.addWidget(divider)
        translation_head=QHBoxLayout(); translation_head.addStretch(1)
        self.translation_meta=QLabel('RU · Перевод'); self.translation_meta.setObjectName('meta'); translation_head.addWidget(self.translation_meta)
        self.translation=TwoLineLabel(); self.translation.setObjectName('body'); self.translation.setFixedHeight(58)
        content_layout.addLayout(translation_head); content_layout.addWidget(self.translation)
        self.text_effect=QGraphicsOpacityEffect(self.content); self.content.setGraphicsEffect(self.text_effect); layout.addWidget(self.content,1)

        self.status=QLabel('Настройте аудио и модель перевода, затем запустите.'); self.status.setStyleSheet('color:#abb5c4;font-size:12px;background:transparent;border:0'); self.status.setMaximumHeight(18); layout.addWidget(self.status)
        self.ptt_btn=QPushButton('🎙   Mouse 5: удержание для ответа (RU → EN)'); self.ptt_btn.setObjectName('ptt'); self.ptt_btn.setFixedHeight(52); self.ptt_btn.setProperty('active',False); layout.addWidget(self.ptt_btn)

        self._drag=None; self._last_sequence=-1; self._running=False; self.settings=load(); self.setWindowOpacity(self.settings.opacity)
        self.fade_timer=QTimer(self); self.fade_timer.setSingleShot(True); self.fade_timer.setInterval(6500); self.fade_timer.timeout.connect(self._fade_text)
        self.fade_animation=QPropertyAnimation(self.text_effect,b'opacity',self); self.fade_animation.setDuration(700); self.fade_animation.setStartValue(1.0); self.fade_animation.setEndValue(0.0); self.fade_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.router=AudioRouter(); self.engine=self._new_engine(); self._wire_engine(self.engine)
        self.start_btn.clicked.connect(self.start_or_pause); self.settings_btn.clicked.connect(self.open_settings)
        self.ptt_btn.pressed.connect(self.engine.request_ptt); self.ptt_btn.released.connect(self.engine.request_release)
        self.hotkey_toggle.connect(self.toggle_visible); self.hotkey_pause.connect(self.start_or_pause)
        self.hook=MouseButtonHook(self.engine.request_ptt,self.engine.request_release,self.settings.ptt_button,self.hotkey_toggle.emit,self.hotkey_pause.emit)
        try: self.hook.start(); self.status.setText('Mouse 5 подключена · настройте перевод и нажмите ▶')
        except Exception as exc: self.status.setText(f'Глобальный хук недоступен: {exc}; используйте кнопку внизу.')
    def _new_engine(self): return AudioEngine(self.router,self.settings)
    def _wire_engine(self,engine):
        engine.ptt_requested.connect(engine.begin_ptt); engine.ptt_released.connect(engine.finish_ptt)
        engine.signals.status.connect(self.status.setText); engine.signals.route.connect(self.set_route)
        engine.signals.error.connect(self.show_error); engine.signals.transcript.connect(self.show_transcript)
    def start_or_pause(self):
        state=self.router.decision().state.name
        if state=='PAUSED':
            self.engine.resume(); self._running=True; self.start_btn.setText('Ⅱ'); self.start_btn.setToolTip('Приостановить')
        elif state in ('LISTENING_PARTNER','PUSH_TO_TALK'):
            self.engine.pause(); self._running=False; self.start_btn.setText('▶'); self.start_btn.setToolTip('Продолжить')
        elif self.engine._started and not self.engine._ready: return
        else: self.start_processing()
    def start_processing(self):
        if not self.settings.mic_device or not self.settings.system_device or not self.settings.translation_model:
            QMessageBox.information(self,'Нужно настроить VoxBridge','Выберите микрофон и системный звук, укажите ID загруженной модели LM Studio, затем сохраните настройки.')
            self.open_settings(); return
        answer=QMessageBox.question(self,'Запуск VoxBridge','При первом запуске Whisper может скачать выбранную модель. Продолжить?')
        if answer!=QMessageBox.Yes: return
        self._running=True; self.start_btn.setText('…'); self.start_btn.setEnabled(False); self.engine.start()
    def set_route(self,label):
        if label.startswith('YOU'):
            self.heading.setText('VOXBRIDGE · ВАШ ГОЛОС'); self.heading.setStyleSheet('color:#65ef9d;font-size:18px;font-weight:700;letter-spacing:1px;border:0;background:transparent'); self.led.setStyleSheet('color:#45e987;font-size:17px;border:0;background:transparent')
            self.original_meta.setText('▂▅▇▅▃   RU · Вы'); self.translation_meta.setText('EN · Перевод'); self._set_ptt_active(True)
        elif label=='ПАУЗА':
            self.heading.setText('VOXBRIDGE · ПАУЗА'); self.heading.setStyleSheet('color:#e1b858;font-size:18px;font-weight:700;letter-spacing:1px;border:0;background:transparent'); self.led.setStyleSheet('color:#e1b858;font-size:17px;border:0;background:transparent'); self._set_ptt_active(False)
        else:
            self.heading.setText('VOXBRIDGE · АКТИВЕН' if self.engine._ready else 'VOXBRIDGE · ЗАПУСК')
            self.heading.setStyleSheet('color:#65ef9d;font-size:18px;font-weight:700;letter-spacing:1px;border:0;background:transparent')
            self.led.setStyleSheet('color:#47e985;font-size:17px;border:0;background:transparent'); self.original_meta.setText('▂▅▇▅▃   EN · Собеседник'); self.translation_meta.setText('RU · Перевод'); self._set_ptt_active(False)
        self.start_btn.setEnabled(True); self.start_btn.setText('Ⅱ' if self.router.decision().state.name!='PAUSED' else '▶')
    def _set_ptt_active(self,active):
        self.ptt_btn.setProperty('active',bool(active)); self.ptt_btn.style().unpolish(self.ptt_btn); self.ptt_btn.style().polish(self.ptt_btn)
        if active: self.ptt_btn.setText('🎙   ИДЁТ ЗАПИСЬ · Mouse 5 удерживается')
        else: self.ptt_btn.setText('🎙   Mouse 5: удержание для ответа (RU → EN)')
    def show_transcript(self,sequence,source,text,translated,state):
        if sequence<self._last_sequence: return
        is_new=sequence>self._last_sequence; self._last_sequence=sequence
        self.fade_animation.stop(); self.text_effect.setOpacity(1.0)
        self.original_meta.setText('▂▅▇▅▃   EN · Собеседник' if source=='partner' else '▂▅▇▅▃   RU · Вы')
        self.translation_meta.setText('RU · Перевод' if source=='partner' else 'EN · Перевод')
        self.original.set_full_text(text)
        if is_new or translated: self.translation.set_full_text(translated or 'Перевожу…')
        self.status.setText(state); self.fade_timer.start()
    def _fade_text(self):
        self.fade_animation.stop(); self.fade_animation.setStartValue(self.text_effect.opacity()); self.fade_animation.start()
    def show_error(self,message):
        self.status.setText(message)
        if not self.engine._ready:
            self._running=False; self.start_btn.setEnabled(True); self.start_btn.setText('▶'); self.heading.setText('VOXBRIDGE · ОШИБКА'); self.led.setStyleSheet('color:#ff6874;font-size:17px;border:0;background:transparent')
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
        self._running=False; self.start_btn.setEnabled(True); self.start_btn.setText('▶'); self.heading.setText('VOXBRIDGE · ОСТАНОВЛЕНО'); self.led.setStyleSheet('color:#727b89;font-size:17px;border:0;background:transparent')
        if was_started: self.start_processing()
    def toggle_visible(self): self.hide() if self.isVisible() else self.show()
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and event.position().y()<48: self._drag=event.globalPosition().toPoint()-self.frameGeometry().topLeft()
    def mouseMoveEvent(self,event):
        if self._drag is not None and event.buttons() & Qt.LeftButton: self.move(event.globalPosition().toPoint()-self._drag)
    def mouseReleaseEvent(self,event): self._drag=None
    def closeEvent(self,event): self.hook.stop(); self.engine.close(); event.accept()
    def safe_exit(self): self.close(); QApplication.quit()

def run():
    app=QApplication(sys.argv); app.setQuitOnLastWindowClosed(False); overlay=Overlay(); tray=QSystemTrayIcon(app.style().standardIcon(QStyle.SP_ComputerIcon),app)
    menu=QMenu(); menu.addAction('Показать / скрыть',overlay.toggle_visible); menu.addAction('Запуск / пауза',overlay.start_or_pause); menu.addAction('Настройки',overlay.open_settings); menu.addSeparator(); menu.addAction('Выход',overlay.safe_exit); tray.setContextMenu(menu); tray.show(); overlay.show()
    return app.exec()
