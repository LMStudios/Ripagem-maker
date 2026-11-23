"""Perfis reutilizáveis sem chaves, consentimentos ou áudios de outros trabalhos."""
import json
import re
import threading
import uuid
from pathlib import Path
from . import trocas as T
PATH=Path(__file__).resolve().parent/'workspace/perfis.json'
LOCK=threading.RLock()
def read():
    with LOCK:return json.loads(PATH.read_text()) if PATH.exists() else []
def save(body):
    with LOCK:
        name=str(body.get('nome','')).strip()
        if not name or len(name)>100:raise ValueError('Dê um nome ao perfil (até 100 caracteres).')
        data=body.get('dados',{});clean={}
        for key in ('produto','novo','aliases','pasta','provider','model'):
            value=str(data.get(key,'')).strip()
            if len(value)>2000:raise ValueError('Campo do perfil muito longo.')
            clean[key]=value
        clean['vozes']={str(k):str(v) for k,v in data.get('vozes',{}).items() if re.fullmatch(r'[A-Za-z0-9_-]{1,256}',str(v))}
        for key in ('precos','kits'):
            clean[key]={str(k):str(v) for k,v in data.get(key,{}).items() if len(str(k))<100 and re.fullmatch(r'\d+(?:[.,]\d+)?',str(v))}
        rows=read();rid=body.get('id')
        if rid and not any(r['id']==rid for r in rows):raise ValueError('Perfil não encontrado.')
        row={'id':rid or uuid.uuid4().hex,'nome':name,'dados':clean}
        rows=[r for r in rows if r['id']!=row['id']]+[row]
        T.write(PATH,rows);return row
