class WhisperRecognizer:
    """Lazy faster-whisper wrapper; model is reused and never loaded in callbacks."""
    def __init__(self,model='base',device='cpu',compute_type='int8'):
        self.model_name=model; self.device=device; self.compute_type=compute_type; self._model=None
    def load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model=WhisperModel(self.model_name,device=self.device,compute_type=self.compute_type)
        return self
    def transcribe(self,audio,language=None):
        self.load(); segments,_=self._model.transcribe(audio,language=language,vad_filter=True,beam_size=1)
        return ' '.join(s.text.strip() for s in segments if s.text.strip())
