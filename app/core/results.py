"""Presentation ordering guard, independent of Qt and worker threads."""


class ResultGate:
    def __init__(self, engine_id):
        self.engine_id = engine_id
        self.last_sequence = -1

    def accept(self, event, router):
        if event.engine_id != self.engine_id or not router.accepts_result(
            event.source, event.generation
        ):
            return False
        if event.sequence < self.last_sequence:
            return False
        self.last_sequence = event.sequence
        return True
