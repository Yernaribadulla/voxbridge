from app.core.state import AudioRouter,State
def test_initial_and_start():
 r=AudioRouter(); assert r.state is State.STARTING; assert r.start().accept_partner
def test_ptt_exclusive_and_release():
 r=AudioRouter(); r.start(); d=r.press(); assert d.state is State.PUSH_TO_TALK and d.accept_microphone and not d.accept_partner; assert r.accepts('microphone',d.generation); assert not r.accepts('partner',d.generation); assert r.release().state is State.FINALIZING_USER_SPEECH; assert r.partner_resumed().accept_partner
def test_stale_results_and_rapid_presses():
 r=AudioRouter(); r.start(); old=r.decision().generation; r.press(); assert not r.accepts('partner',old); r.release(); r.partner_resumed(); d=r.press(); assert d.accept_microphone; assert not r.accepts('microphone',old)
def test_pause_stop():
 r=AudioRouter(); r.start(); assert r.pause().state is State.PAUSED; assert r.stop().state is State.STOPPING
