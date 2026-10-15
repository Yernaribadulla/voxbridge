"""Bounded, microphone-first queues shared by recognition and translation."""

from collections import deque
from queue import Empty
from threading import Condition
from time import monotonic


class QueueClosed(Exception):
    pass


class PriorityWorkQueue:
    def __init__(self, capacity=8):
        if capacity < 1:
            raise ValueError("Queue capacity must be positive.")
        self.capacity = capacity
        self._mic = deque()
        self._partner = deque()
        self._condition = Condition()
        self._closed = False
        self.dropped = 0

    def put(self, job):
        """Prefer recent work on overload; partner work never evicts microphone work."""
        with self._condition:
            if self._closed:
                return False
            if len(self._mic) + len(self._partner) >= self.capacity:
                if self._partner:
                    self._partner.popleft()
                elif job.source == "microphone":
                    self._mic.popleft()
                else:
                    self.dropped += 1
                    return False
                self.dropped += 1
            (self._mic if job.source == "microphone" else self._partner).append(job)
            self._condition.notify()
            return True

    def get(self, timeout=None):
        deadline = None if timeout is None else monotonic() + timeout
        with self._condition:
            while not self._mic and not self._partner:
                if self._closed:
                    raise QueueClosed
                remaining = None if deadline is None else deadline - monotonic()
                if remaining is not None and remaining <= 0:
                    raise Empty
                self._condition.wait(remaining)
            return (self._mic if self._mic else self._partner).popleft()

    def discard(self, predicate):
        with self._condition:
            for jobs in (self._mic, self._partner):
                keep = [job for job in jobs if not predicate(job)]
                jobs.clear()
                jobs.extend(keep)

    def close(self):
        with self._condition:
            self._closed = True
            self._mic.clear()
            self._partner.clear()
            self._condition.notify_all()

    def __len__(self):
        with self._condition:
            return len(self._mic) + len(self._partner)
