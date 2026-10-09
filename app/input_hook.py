class MouseButtonHook:
    """Lightweight global hook adapter; callbacks should enqueue events only."""
    def __init__(self,on_press,on_release,button_name='x2'): self.on_press=on_press; self.on_release=on_release; self.button_name=button_name; self._listener=None
    def start(self):
        from pynput import mouse
        button=getattr(mouse.Button,self.button_name,mouse.Button.x2)
        def press(b):
            if b==button: self.on_press()
        def release(b):
            if b==button: self.on_release()
        self._listener=mouse.Listener(on_click=lambda b,pressed: press(b) if pressed else release(b)); self._listener.start()
    def stop(self):
        if self._listener: self._listener.stop(); self._listener=None
