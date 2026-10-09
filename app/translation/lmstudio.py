import requests
PROMPTS={'en_ru':'Translate the source text into natural Russian. Preserve meaning, names, gaming terms, slang, tone, and conversational intent. Return only the translation. Do not answer, explain, summarize, or invent context.','ru_en':'Translate the source text into natural conversational English. Preserve intended meaning and tone. Return only the translation. Do not answer, explain, summarize, or invent context.'}
class LMStudioProvider:
    def __init__(self,base_url='http://localhost:1234/v1',model='',timeout=20): self.base_url=base_url.rstrip('/'); self.model=model; self.timeout=timeout
    def translate(self,text,direction):
        if not text.strip(): return ''
        r=requests.post(self.base_url+'/chat/completions',json={'model':self.model,'temperature':.1,'max_tokens':256,'messages':[{'role':'system','content':PROMPTS[direction]},{'role':'user','content':text}]},timeout=self.timeout); r.raise_for_status(); return r.json()['choices'][0]['message']['content'].strip()
    def test_connection(self):
        r=requests.get(self.base_url+'/models',timeout=5); r.raise_for_status(); return [x.get('id','') for x in r.json().get('data',[])]
