"""Inspect Qt's registered receiver metadata; do not create an app or a window."""

from app.ui.main import Overlay
from app.ui.settings import SettingsDialog


def test_cross_thread_gui_receivers_are_registered_slots():
    assert Overlay.staticMetaObject.indexOfSlot("toggle_visible()") >= 0
    assert Overlay.staticMetaObject.indexOfSlot("start_or_pause()") >= 0
    assert SettingsDialog.staticMetaObject.indexOfSlot("_show_test(QString)") >= 0
