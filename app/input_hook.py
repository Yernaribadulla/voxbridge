class MouseButtonHook:
    """Lightweight global hook adapter; callbacks should enqueue events only."""
    def __init__(self,on_press,on_release,button_name='x2',on_toggle=None,on_pause=None): self.on_press=on_press; self.on_release=on_release; self.button_name=button_name; self.on_toggle=on_toggle; self.on_pause=on_pause; self._listener=None; self._keys=None
    def start(self):
        from pynput import mouse
        button=getattr(mouse.Button,self.button_name,mouse.Button.x2)
        def press(b):
            if b==button: self.on_press()
        def release(b):
            if b==button: self.on_release()
        self._listener=mouse.Listener(on_click=lambda b,pressed: press(b) if pressed else release(b)); self._listener.start()
        if self.on_toggle or self.on_pause:
            from pynput import keyboard
            hotkeys={}
            if self.on_toggle: hotkeys['<ctrl>+<shift>+v']=self.on_toggle
            if self.on_pause: hotkeys['<ctrl>+<shift>+p']=self.on_pause
            self._keys=keyboard.GlobalHotKeys(hotkeys); self._keys.start()
    def stop(self):
        if self._listener: self._listener.stop(); self._listener=None
        if self._keys: self._keys.stop(); self._keys=None
