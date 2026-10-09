import json,os
from dataclasses import dataclass,asdict
from pathlib import Path
@dataclass
class Settings:
    translation_url:str='http://localhost:1234/v1'; translation_model:str=''; mic_device:str=''; system_device:str=''; partner_model:str='tiny.en'; user_model:str='base'; compute_device:str='cpu'; compute_type:str='int8'; opacity:float=.9; font_size:int=14; history_length:int=20; persistent_history:bool=False; ptt_button:str='x2'
def path(): return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'VoxBridge'/'settings.json'
def load():
    try: return Settings(**{**asdict(Settings()),**json.loads(path().read_text(encoding='utf8'))})
    except (OSError,ValueError,TypeError): return Settings()
def save(s): path().parent.mkdir(parents=True,exist_ok=True); path().write_text(json.dumps(asdict(s),indent=2),encoding='utf8')
