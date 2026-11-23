"""Executar com DR Studio aberto. Transcreve uma locução sintética real."""
import json
import time
from pathlib import Path
import requests
root='http://127.0.0.1:8765'
with Path('tests/fixtures/auditoria.mp4').open('rb') as f:
    r=requests.post(root+'/api/validacao/upload',data=f,headers={'X-Filename':'auditoria_teste.mp4','X-Termos':'Golden%20Brain','X-Idioma':'en','X-Motor':'mlx'})
r.raise_for_status();jid=r.json()['id'];print('JOB',jid,flush=True)
for i in range(240):
    j=requests.get(root+'/api/ml/job/'+jid).json()
    if j['status'] in ('erro','cancelado','concluido'):break
    time.sleep(1)
assert j['status']=='concluido',j
v=j['result']['validacao']
print(json.dumps({'pitch':v['pitch'],'resquicios':v['resquicios'],'exports':v['exports']},ensure_ascii=False),flush=True)
assert len(v['resquicios'])==2,v
assert v['pitch'] is not None,v
for ext,name in v['exports'].items():assert requests.get(root+'/media/out/'+name).status_code==200
Path('tests/fixtures/ultimo_resultado.json').write_text(json.dumps(j,ensure_ascii=False,indent=2))
