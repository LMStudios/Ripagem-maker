"""Pastas configuráveis, com acesso aos trabalhos anteriores sem movê-los."""
import json
import tempfile
import threading
from pathlib import Path

PROJECT=Path(__file__).resolve().parent.parent
CONFIG=PROJECT/'plataforma/workspace/ajustes.json'
LOCK=threading.RLock()
MAINTENANCE=False
LEGACY={'fatiador':PROJECT/'saidas','montagens':PROJECT/'plataforma/workspace/saidas','videos':PROJECT/'plataforma/workspace/videos','ferramentas':PROJECT/'plataforma/workspace/ferramentas'}
SUB={'fatiador':'Fatiador','montagens':'Montagens','videos':'Biblioteca','ferramentas':'Ferramentas'}
# Pastas criadas antes das ferramentas avulsas não têm a subpasta Ferramentas; ela nasce quando for usada.
CREATE_ON_SAVE=('fatiador','montagens','videos')
DEFAULT_VISUAL_MARGIN_MS=1500

def read():
    if not CONFIG.exists():return {'pasta_principal':'','anteriores':[]}
    return json.loads(CONFIG.read_text())

def current(kind):
    root=read().get('pasta_principal','')
    return Path(root)/SUB[kind] if root else LEGACY[kind]

def roots(kind):
    cfg=read();paths=[current(kind)]+[Path(p)/SUB[kind] for p in cfg.get('anteriores',[]) if p]+[LEGACY[kind]]
    # Projetos movidos individualmente para outra pasta continuam abríveis pelo nome.
    if kind=='fatiador':paths+=[Path(p) for p in cfg.get('pastas_projetos',[]) if p]
    return list(dict.fromkeys(p.resolve() for p in paths))

def resolve(kind,relative,fallback=None):
    rel=Path(relative)
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('Caminho inválido.')
    candidates=([Path(fallback).resolve()] if fallback else [])+roots(kind)
    for root in dict.fromkeys(candidates):
        path=(root/rel).resolve()
        if path.is_relative_to(root) and path.exists():return path
    return (candidates[0]/rel).resolve()

def job_folder(name,fallback=None):
    if len(Path(name).parts)!=1 or name in ('','.','..'):raise ValueError('Trabalho inválido.')
    return resolve('fatiador',name,fallback)

def is_job(path,fallback=None):
    allowed=roots('fatiador')+([Path(fallback).resolve()] if fallback else [])
    return Path(path).resolve().parent in allowed and Path(path).is_dir()

def write_config(cfg):
    """Grava em arquivo temporário e troca de uma vez: uma gravação interrompida não corrompe os ajustes."""
    with LOCK:
        CONFIG.parent.mkdir(parents=True,exist_ok=True)
        tmp=CONFIG.with_name(CONFIG.name+'.'+__import__('uuid').uuid4().hex+'.tmp')
        try:tmp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2));tmp.replace(CONFIG)
        finally:tmp.unlink(missing_ok=True)

def add_project_root(path):
    with LOCK:
        cfg=read();path=str(Path(path).resolve());extra=[p for p in cfg.get('pastas_projetos',[]) if p]
        if path not in extra and Path(path) not in [Path(p) for p in roots('fatiador')]:extra.append(path)
        cfg['pastas_projetos']=extra;write_config(cfg)

def tool_folder(name):
    """Pasta das ferramentas avulsas dentro da pasta principal (ou do app, se ainda não houver uma)."""
    from datetime import datetime
    base=current('ferramentas')/name/datetime.now().strftime('%Y-%m-%d_%H%M%S')
    target=base;n=2
    while target.exists():target=Path(f'{base}_{n}');n+=1
    target.mkdir(parents=True);return target

def tool_relative(folder):
    folder=Path(folder).resolve()
    for root in roots('ferramentas'):
        if folder.is_relative_to(root):return folder.relative_to(root).as_posix()
    raise ValueError('Pasta fora das ferramentas do app.')

AUTO_DEFAULT={'ativa':False,'temporarios':True,'caches':True,'projetos_antigos':False,'dias':90}
TREAT_DEFAULT={'silencio':True,'margem_inicio_ms':80,'margem_fim_ms':200,'ruido':False,'intensidade':35}

def cleanup_settings():return AUTO_DEFAULT|read().get('limpeza_auto',{})
def treatment_settings():return TREAT_DEFAULT|read().get('tratamento_audio',{})

def save_cleanup_settings(value):
    if not isinstance(value,dict):raise ValueError('Ajustes de limpeza inválidos.')
    clean={k:bool(value.get(k,AUTO_DEFAULT[k])) for k in ('ativa','temporarios','caches','projetos_antigos')}
    days=value.get('dias',AUTO_DEFAULT['dias'])
    if isinstance(days,bool) or not isinstance(days,int) or not 7<=days<=3650:raise ValueError('Use um período entre 7 e 3650 dias.')
    clean['dias']=days
    with LOCK:cfg=read();cfg['limpeza_auto']=clean;write_config(cfg)
    return clean

def save_treatment_settings(value):
    from .tratamento_audio import normalize
    clean=normalize(value)
    with LOCK:cfg=read();cfg['tratamento_audio']=clean;write_config(cfg)
    return clean

def status():
    cfg=read()
    return {'pastas_projetos':cfg.get('pastas_projetos',[]),'limpeza_auto':cleanup_settings(),'tratamento_audio':treatment_settings(),'configuracao_inicial':bool(cfg.get('pasta_principal')),'pasta_disponivel':Path(cfg['pasta_principal']).is_dir() if cfg.get('pasta_principal') else False,'pasta_principal':cfg.get('pasta_principal',''),'pastas':{k:str(current(k)) for k in SUB},'anteriores':cfg.get('anteriores',[]),'margem_fala_ms':cfg.get('margem_fala_ms',200),'margem_visual_ms':cfg.get('margem_visual_ms',DEFAULT_VISUAL_MARGIN_MS)}

def save_margin(value):
    if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=500:raise ValueError('Use uma margem inteira entre 0 e 500 ms.')
    with LOCK:
        cfg=read();cfg['margem_fala_ms']=value;CONFIG.parent.mkdir(parents=True,exist_ok=True)
        tmp=CONFIG.with_suffix('.tmp');tmp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2));tmp.replace(CONFIG)
        return status()

def visual_margin_ms():return read().get('margem_visual_ms',DEFAULT_VISUAL_MARGIN_MS)

def save_visual_margin(value):
    if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=3000:raise ValueError('Use uma margem visual entre 0 e 3000 ms.')
    with LOCK:
        cfg=read();cfg['margem_visual_ms']=value;CONFIG.parent.mkdir(parents=True,exist_ok=True)
        tmp=CONFIG.with_suffix('.tmp');tmp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2));tmp.replace(CONFIG)
        return status()

def save(value):
    with LOCK:
        raw=str(value).strip();new=''
        if raw:
            path=Path(raw).expanduser()
            if not path.is_absolute():raise ValueError('Escolha uma pasta ou informe um caminho absoluto.')
            path=path.resolve();path.mkdir(parents=True,exist_ok=True)
            for kind in CREATE_ON_SAVE:(path/SUB[kind]).mkdir(exist_ok=True)
            for directory in [path]+[path/SUB[kind] for kind in CREATE_ON_SAVE]:
                with tempfile.TemporaryFile(dir=directory):pass
            new=str(path)
        cfg=read();old=cfg.get('pasta_principal','');previous=list(cfg.get('anteriores',[]))
        if old and old!=new and old not in previous:previous.append(old)
        CONFIG.parent.mkdir(parents=True,exist_ok=True)
        tmp=CONFIG.with_suffix('.tmp');tmp.write_text(json.dumps(cfg|{'pasta_principal':new,'anteriores':previous},ensure_ascii=False,indent=2));tmp.replace(CONFIG)
        return status()
