"""Global input adapter. No GUI, audio I/O or inference in input callbacks."""


class MouseButtonHook:
    def __init__(
        self, on_press, on_release, button_name="x2", on_toggle=None, on_pause=None
    ):
        self.on_press = on_press
        self.on_release = on_release
        self.button_name = button_name
        self.on_toggle = on_toggle
        self.on_pause = on_pause
        self._listener = None
        self._keys = None
        self._held = False

    def start(self):
        if self._listener is not None:
            return
        from pynput import mouse, keyboard

        button = getattr(mouse.Button, self.button_name, mouse.Button.x2)

        def on_click(x, y, clicked, pressed, *extra):
            if clicked != button:
                return
            if pressed and not self._held:
                self._held = True
                self.on_press()
            elif not pressed and self._held:
                self._held = False
                self.on_release()

        try:
            self._listener = mouse.Listener(on_click=on_click)
            self._listener.start()
            hotkeys = {}
            if self.on_toggle:
                hotkeys["<ctrl>+<shift>+v"] = self.on_toggle
            if self.on_pause:
                hotkeys["<ctrl>+<shift>+p"] = self.on_pause
            if hotkeys:
                self._keys = keyboard.GlobalHotKeys(hotkeys)
                self._keys.start()
        except Exception:
            self.stop()
            raise

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
        if self._keys:
            self._keys.stop()
            self._keys = None
        if self._held:
            self._held = False
            self.on_release()
