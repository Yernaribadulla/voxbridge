from collections import deque
class BoundedAudioBuffer:
    def __init__(self,max_frames=50): self._q=deque(maxlen=max_frames)
    def add(self,frame): self._q.append(frame)
    def pop_all(self): out=list(self._q); self._q.clear(); return out
    def __len__(self): return len(self._q)
