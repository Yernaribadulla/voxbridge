from app.audio.buffer import BoundedAudioBuffer
from app.translation.lmstudio import PROMPTS
def test_buffer_bounded():
 b=BoundedAudioBuffer(2); [b.add(i) for i in range(5)]; assert len(b)==2 and b.pop_all()==[3,4]
def test_prompts_directions(): assert 'Russian' in PROMPTS['en_ru'] and 'English' in PROMPTS['ru_en']
