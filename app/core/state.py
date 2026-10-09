from dataclasses import dataclass
from enum import Enum, auto
from threading import RLock
class State(Enum):
    STARTING=auto(); LISTENING_PARTNER=auto(); PUSH_TO_TALK=auto(); FINALIZING_USER_SPEECH=auto(); PAUSED=auto(); ERROR=auto(); STOPPING=auto()
@dataclass(frozen=True)
class RouteDecision:
    state: State; generation: int; accept_partner: bool; accept_microphone: bool
class AudioRouter:
    def __init__(self): self.state=State.STARTING; self.generation=0; self.utterance=0; self._lock=RLock()
    def start(self):
        with self._lock: self.state=State.LISTENING_PARTNER; return self.decision()
    def press(self):
        with self._lock:
            if self.state in (State.STOPPING,State.ERROR,State.PAUSED) or self.state is State.PUSH_TO_TALK: return self.decision()
            self.generation+=1; self.utterance+=1; self.state=State.PUSH_TO_TALK; return self.decision()
    def release(self):
        with self._lock:
            if self.state is State.PUSH_TO_TALK: self.state=State.FINALIZING_USER_SPEECH
            return self.decision()
    def partner_resumed(self):
        with self._lock:
            if self.state is State.FINALIZING_USER_SPEECH: self.state=State.LISTENING_PARTNER
            return self.decision()
    def pause(self):
        with self._lock: self.state=State.PAUSED; self.generation+=1; return self.decision()
    def stop(self):
        with self._lock: self.state=State.STOPPING; self.generation+=1; return self.decision()
    def decision(self):
        with self._lock: return RouteDecision(self.state,self.generation,self.state is State.LISTENING_PARTNER,self.state is State.PUSH_TO_TALK)
    def accepts_capture(self,source,generation):
        with self._lock: return generation==self.generation and ((source=='partner' and self.state is State.LISTENING_PARTNER) or (source=='microphone' and self.state is State.PUSH_TO_TALK))
    def accepts_result(self,source,generation):
        with self._lock:
            if generation!=self.generation: return False
            if source=='partner': return self.state not in (State.PUSH_TO_TALK,State.PAUSED,State.STOPPING,State.ERROR)
            return source=='microphone' and self.state in (State.PUSH_TO_TALK,State.FINALIZING_USER_SPEECH,State.LISTENING_PARTNER)
    def accepts(self,source,generation): return self.accepts_capture(source,generation)
