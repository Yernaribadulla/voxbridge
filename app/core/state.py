from dataclasses import dataclass
from enum import Enum, auto
class State(Enum):
    STARTING=auto(); LISTENING_PARTNER=auto(); PUSH_TO_TALK=auto(); FINALIZING_USER_SPEECH=auto(); PAUSED=auto(); ERROR=auto(); STOPPING=auto()
@dataclass(frozen=True)
class RouteDecision:
    state: State; generation: int; accept_partner: bool; accept_microphone: bool
class AudioRouter:
    def __init__(self): self.state=State.STARTING; self.generation=0; self.utterance=0
    def start(self): self.state=State.LISTENING_PARTNER; return self.decision()
    def press(self):
        if self.state in (State.STOPPING,State.ERROR): return self.decision()
        self.generation+=1; self.utterance+=1; self.state=State.PUSH_TO_TALK; return self.decision()
    def release(self):
        if self.state is State.PUSH_TO_TALK: self.generation+=1; self.state=State.FINALIZING_USER_SPEECH
        return self.decision()
    def partner_resumed(self):
        if self.state is State.FINALIZING_USER_SPEECH: self.state=State.LISTENING_PARTNER
        return self.decision()
    def pause(self): self.state=State.PAUSED; self.generation+=1; return self.decision()
    def stop(self): self.state=State.STOPPING; self.generation+=1; return self.decision()
    def decision(self): return RouteDecision(self.state,self.generation,self.state is State.LISTENING_PARTNER,self.state is State.PUSH_TO_TALK)
    def accepts(self,source,generation): return generation==self.generation and ((source=='partner' and self.decision().accept_partner) or (source=='microphone' and self.decision().accept_microphone))
