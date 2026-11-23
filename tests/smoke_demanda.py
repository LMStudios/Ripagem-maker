"""Verificação real de download HTTP e montagem ffmpeg com fontes sintéticas."""
import functools
import http.server
import json
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
import requests

root='http://127.0.0.1:8765'
with tempfile.TemporaryDirectory() as temp:
    for name,color,t in [('base','blue',5),('lead','red',3)]:
        subprocess.run(['/opt/homebrew/bin/ffmpeg','-y','-v','error','-f','lavfi','-i',f'color={color}:s=160x90:r=25:d={t}','-f','lavfi','-i',f'sine=frequency=440:duration={t}','-c:v','libx264','-c:a','aac','-shortest',str(Path(temp)/f'{name}.mp4')],check=True)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=temp))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    host=f'http://127.0.0.1:{server.server_port}'
    plan={'base_url':host+'/base.mp4','corte_original':'00:02','titulo':'TESTE_AUTOMATICO','variacoes':[{'url':host+'/lead.mp4','fim':'00:01'},{'url':host+'/lead.mp4','fim':'00:02'}]}
    r=requests.post(root+'/api/demanda/executar',json=plan);r.raise_for_status(); jid=r.json()['id']
    for _ in range(120):
        j=requests.get(root+'/api/ml/job/'+jid).json()
        if j['status'] in ('concluido','erro','cancelado'): break
        time.sleep(.25)
    assert j['status']=='concluido',j
    for result,expected in zip(j['result']['versoes'],[4,5]):
        assert abs(result['duracao_s']-expected)<.12,result
        assert result['dif_av_ms']<100,result
        assert requests.get(root+'/media/out/'+result['arquivo']).status_code==200
    # Confere imagens antes/depois da emenda: vermelho da ML, azul do body.
    output=Path('plataforma/workspace/saidas')/j['result']['versoes'][0]['arquivo']
    def pixel(t):
        raw=subprocess.check_output(['/opt/homebrew/bin/ffmpeg','-v','error','-ss',str(t),'-i',str(output),'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','-'])
        return list(raw[:3])
    red,blue=pixel(.5),pixel(1.5)
    assert red[0]>200 and red[2]<30,red
    assert blue[2]>200 and blue[0]<30,blue
    print(json.dumps({'status':j['status'],'duracoes':[v['duracao_s'] for v in j['result']['versoes']],'cores':[red,blue]},ensure_ascii=False))
    server.shutdown()
