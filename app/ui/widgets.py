"""Small presentation widgets; transcript text is always rendered as plain text."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QTextLayout, QTextOption
from PySide6.QtWidgets import QLabel


class TwoLineLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setTextFormat(Qt.PlainText)
        self.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.setAccessibleName("Текст речи")

    def set_full_text(self, text):
        self._full_text = " ".join((text or "").split())
        self.setToolTip(self._full_text)
        self._layout_text()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_text()

    def changeEvent(self, event):
        super().changeEvent(event)
        self._layout_text()

    def _layout_text(self):
        if not hasattr(self, "_full_text"):
            return
        text = self._full_text
        width = max(1, self.contentsRect().width())
        if not text:
            self.setText("")
            return
        layout = QTextLayout(text, self.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        layout.beginLayout()
        first = layout.createLine()
        first.setLineWidth(width)
        second = layout.createLine()
        if not second.isValid():
            rendered = text
        else:
            second.setLineWidth(width)
            remaining = text[second.textStart() :]
            last = QFontMetrics(self.font()).elidedText(remaining, Qt.ElideRight, width)
            rendered = text[: first.textLength()].rstrip() + "\n" + last
        layout.endLayout()
        self.setText(rendered)
