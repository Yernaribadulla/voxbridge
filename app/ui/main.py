import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QLabel,QVBoxLayout,QWidget,QSystemTrayIcon,QMenu,QStyle
from app.core.state import AudioRouter
class Overlay(QWidget):
    def __init__(self):
        super().__init__(flags=Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.Tool); self.setWindowTitle('VoxBridge'); self.setMinimumSize(420,140); self.setStyleSheet('QWidget{background:#16181d;color:#f2f4f8;border:1px solid #444;border-radius:8px} QLabel{padding:6px}'); self.direction=QLabel('STARTING'); self.original=QLabel(''); self.translation=QLabel(''); self.translation.setStyleSheet('font-size:20px;font-weight:bold'); l=QVBoxLayout(self); l.addWidget(self.direction); l.addWidget(self.original); l.addWidget(self.translation); self._drag=None
    def mousePressEvent(self,e): self._drag=e.globalPosition().toPoint()-self.frameGeometry().topLeft()
    def mouseMoveEvent(self,e):
        if self._drag is not None: self.move(e.globalPosition().toPoint()-self._drag)
def run():
    app=QApplication(sys.argv); app.setQuitOnLastWindowClosed(False); overlay=Overlay(); router=AudioRouter(); router.start(); overlay.direction.setText('PARTNER · EN → RU'); overlay.show(); tray=QSystemTrayIcon(app.style().standardIcon(QStyle.SP_ComputerIcon),app); menu=QMenu(); menu.addAction('Show',overlay.show); menu.addAction('Exit',app.quit); tray.setContextMenu(menu); tray.show(); return app.exec()
