from types import SimpleNamespace
import sys
import pytest
from app.input_hook import MouseButtonHook


class Listener:
    def __init__(self, **callbacks):
        self.callbacks = callbacks
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def fake_pynput(monkeypatch, fail_keyboard=False):
    created = []

    def listener(**kwargs):
        value = Listener(**kwargs)
        created.append(value)
        return value

    class Keys(Listener):
        def __init__(self, values):
            super().__init__()
            self.values = values

        def start(self):
            if fail_keyboard:
                raise RuntimeError("keyboard unavailable")
            super().start()

    package = SimpleNamespace(
        mouse=SimpleNamespace(
            Button=SimpleNamespace(x2="x2", x1="x1"), Listener=listener
        ),
        keyboard=SimpleNamespace(GlobalHotKeys=Keys),
    )
    monkeypatch.setitem(sys.modules, "pynput", package)
    return created


def test_real_callback_signature_deduplication_and_rebinding(monkeypatch):
    created = fake_pynput(monkeypatch)
    events = []
    hook = MouseButtonHook(
        lambda: events.append("down"), lambda: events.append("up"), "x1"
    )
    hook.start()
    hook.start()
    assert len(created) == 1
    callback = created[0].callbacks["on_click"]
    callback(100, 200, "x2", True)
    callback(100, 200, "x1", True)
    callback(100, 200, "x1", True, False)
    callback(100, 200, "x1", False)
    assert events == ["down", "up"]
    hook.stop()
    hook.stop()
    assert created[0].stopped


def test_hook_stop_releases_held_button(monkeypatch):
    created = fake_pynput(monkeypatch)
    events = []
    hook = MouseButtonHook(lambda: events.append("down"), lambda: events.append("up"))
    hook.start()
    created[0].callbacks["on_click"](0, 0, "x2", True)
    hook.stop()
    assert events == ["down", "up"]


def test_keyboard_failure_rolls_back_mouse_listener(monkeypatch):
    created = fake_pynput(monkeypatch, fail_keyboard=True)
    hook = MouseButtonHook(lambda: None, lambda: None, on_toggle=lambda: None)
    with pytest.raises(RuntimeError):
        hook.start()
    assert created[0].stopped
    assert hook._listener is None and hook._keys is None
