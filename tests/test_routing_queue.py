from dataclasses import dataclass
from queue import Empty
from threading import Event, Thread
import pytest
from app.core.jobs import PriorityWorkQueue, QueueClosed
from app.core.state import AudioRouter, State
from app.core.results import ResultGate


@dataclass
class Job:
    source: str
    sequence: int
    generation: int = 0
    engine_id: str = "current"


def test_ptt_cannot_start_during_model_loading_or_after_stop():
    router = AudioRouter()
    assert router.press().state is State.STARTING
    router.start()
    router.stop()
    assert router.start().state is State.STOPPING
    assert router.press().state is State.STOPPING
    assert router.pause().state is State.STOPPING


def test_final_microphone_result_survives_release_but_not_next_press():
    router = AudioRouter()
    router.start()
    current = router.press().generation
    router.release()
    router.partner_resumed()
    assert router.accepts_result("microphone", current)
    router.press()
    assert not router.accepts_result("microphone", current)


def test_paused_and_error_routes_reject_results():
    router = AudioRouter()
    router.start()
    for transition in (router.pause, router.fail, router.stop):
        decision = transition()
        for source in ("partner", "microphone"):
            assert not router.accepts_result(source, decision.generation)


def test_priority_and_fifo():
    queue = PriorityWorkQueue(4)
    for job in (
        Job("partner", 1),
        Job("microphone", 2),
        Job("partner", 3),
        Job("microphone", 4),
    ):
        assert queue.put(job)
    assert [queue.get().sequence for _ in range(4)] == [2, 4, 1, 3]


def test_overload_never_evicts_microphone_to_admit_partner():
    queue = PriorityWorkQueue(2)
    queue.put(Job("microphone", 1))
    queue.put(Job("microphone", 2))
    assert not queue.put(Job("partner", 3))
    assert [queue.get().sequence, queue.get().sequence] == [1, 2]


def test_microphone_evicts_oldest_partner_not_another_microphone():
    queue = PriorityWorkQueue(3)
    for job in (Job("partner", 1), Job("microphone", 2), Job("partner", 3)):
        queue.put(job)
    assert queue.put(Job("microphone", 4))
    assert [queue.get().sequence for _ in range(3)] == [2, 4, 3]


def test_recent_work_replaces_oldest_on_overload():
    queue = PriorityWorkQueue(2)
    for sequence in range(4):
        queue.put(Job("partner", sequence))
    assert [queue.get().sequence, queue.get().sequence] == [2, 3]
    assert queue.dropped == 2


def test_discard_and_timeout():
    queue = PriorityWorkQueue()
    queue.put(Job("partner", 1))
    queue.put(Job("microphone", 2))
    queue.discard(lambda job: job.source == "partner")
    assert queue.get().source == "microphone"
    with pytest.raises(Empty):
        queue.get(timeout=0)


def test_close_wakes_worker_and_rejects_new_jobs():
    queue = PriorityWorkQueue()
    done = Event()

    def worker():
        with pytest.raises(QueueClosed):
            queue.get()
        done.set()

    thread = Thread(target=worker, daemon=True)
    thread.start()
    queue.close()
    assert done.wait(1)
    thread.join(1)
    assert not queue.put(Job("microphone", 1))


def test_gui_delivery_gate_rejects_old_engine_generation_and_sequence():
    router = AudioRouter()
    router.start()
    gate = ResultGate("current")
    assert gate.accept(Job("partner", 10), router)
    assert not gate.accept(Job("partner", 9), router)
    assert not gate.accept(Job("partner", 100, engine_id="retired"), router)
    decision = router.press()
    assert not gate.accept(Job("partner", 11), router)
    assert gate.accept(Job("microphone", 11, generation=decision.generation), router)
    # Reconfiguring an engine restarts its sequence at zero.
    new = ResultGate("replacement")
    assert new.accept(
        Job("microphone", 0, generation=decision.generation, engine_id="replacement"),
        router,
    )
