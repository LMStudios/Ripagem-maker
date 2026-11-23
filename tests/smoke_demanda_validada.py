import functools
import http.server
import json
import threading
import time
from pathlib import Path
import requests
root='http://127.0.0.1:8765'
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory='tests/fixtures'))
threading.Thread(target=server.serve_forever,daemon=True).start()
url=f'http://127.0.0.1:{server.server_port}/auditoria.mp4'
plan={'base_url':url,'corte_original':'00:01','variacoes':[{'url':url,'fim':'00:02','ml':'1'}],'validacao':{'ativo':True,'termos':'Golden Brain','motor':'mlx','idioma':'en'},'nomenclatura':{'produto':'TESTE','tipo':'mod_ml','vsl':'1','copy':'C20','editor':'EV8'}}
r=requests.post(root+'/api/demanda/executar',json=plan);r.raise_for_status();jid=r.json()['id'];print(jid,flush=True)
for i in range(180):
    j=requests.get(root+'/api/ml/job/'+jid).json()
    if j['status'] in ('concluido','erro','cancelado'):break
    time.sleep(1)
assert j['status']=='concluido',j
v=j['result']['versoes'][0]
assert v['status_validacao']=='concluida',v
assert v['validacao']['pitch'],v
assert 'PENDENTE' not in v['nomenclatura'],v
assert requests.get(root+'/media/out/'+v['arquivo']).status_code==200,v
for ext,name in v['validacao']['exports'].items(): assert requests.get(root+'/media/out/'+name).status_code==200
print(json.dumps({'nome':v['nomenclatura'],'arquivo':v['arquivo'],'pitch':v['pitch_detectado'],'resquicios':len(v['validacao']['resquicios'])},ensure_ascii=False),flush=True)
server.shutdown()
