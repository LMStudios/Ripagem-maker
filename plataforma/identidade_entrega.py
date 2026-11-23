"""Identificação do XML, independente da edição e da geração de áudio."""
import json,math,re
from pathlib import Path

def normalize(data):
    if not isinstance(data,dict):raise ValueError('Dados da nomenclatura inválidos.')
    number=str(data.get('numero_vsl','')).strip()
    if number and (not re.fullmatch(r'\d{1,3}',number) or not 1<=int(number)<=999):raise ValueError('Use um número de VSL entre 1 e 999.')
    result={'numero_vsl':str(int(number)).zfill(2) if number else ''}
    for key in ('copy','editor'):
        value=data.get(key,'')
        if not isinstance(value,str) or len(value)>80:raise ValueError('Copy e editor devem ter até 80 caracteres.')
        if re.search(r'[\x00-\x1f\x7f]',value):raise ValueError('Copy e editor não podem conter quebras de linha ou controles.')
        result[key]=re.sub(r'\s+',' ',value).strip().upper()
    manual=str(data.get('pitch_manual','')).strip().replace('_',':')
    if manual:
        parts=manual.split(':')
        if len(parts) not in (2,3) or not all(p.isdigit() for p in parts) or any(int(p)>=60 for p in parts[1:]) or len(parts[0])>3:raise ValueError('Pitch manual inválido. Use mm:ss ou hh:mm:ss.')
        total=sum(int(p)*60**i for i,p in enumerate(reversed(parts)))
        manual=clock(total)
    result['pitch_manual']=manual
    if data.get('editor_origem') in ('perfil','manual'):
        result['editor_origem']=data['editor_origem']
    return result

def for_new_project(data, profile):
    config = normalize(data)
    if profile:
        default = profile['codigo']
        config['editor'] = config['editor'] or default
        config['editor_origem'] = 'perfil' if config['editor'] == default else 'manual'
    return config


def clock(seconds):
    total=int(float(seconds));return f'{total//60:02d}:{total%60:02d}'

def read(out):
    file=Path(out)/'nomenclatura.json'
    return normalize(json.loads(file.read_text()) if file.exists() else {})

def pitch(plan,config):
    if config['pitch_manual']:return config['pitch_manual'],'manual_confirmado'
    found=(plan.get('revisao') or {}).get('pitch')
    if isinstance(found,dict) and found.get('status')=='contexto_6_potes':
        time=found.get('tempo')
        if isinstance(time,(int,float)) and not isinstance(time,bool) and math.isfinite(time) and time>=0:return clock(time),'audio_final_6_potes'
    return 'A IDENTIFICAR','pendente'

def identity(plan,out=None,config=None):
    config=normalize(config if config is not None else plan.get('nomenclatura',read(out) if out else {}))
    when,origin=pitch(plan,config)
    if origin=='pendente' and out and plan.get('pitch_transcricao'):
        from .experiencia import mapped_pitch
        candidate=mapped_pitch(plan,out)
        if candidate and not candidate.get('confirmar'):when,origin=clock(candidate['tempo']),'transcricao_6_potes_mapeado'
    product=re.sub(r'\s+',' ',str(plan.get('produto_novo') or '')).strip().upper() or 'PRODUTO A DEFINIR'
    name=f"FUNIL VSL {config['numero_vsl'] or 'XX'} MOD - {product} - {config['copy'] or 'COPY A DEFINIR'} - {config['editor'] or 'EDITOR A DEFINIR'} - PITCH {when}"
    return {'config':config,'nome_sequencia':name,'pitch':when,'origem_pitch':origin}

def save(out,data):
    from . import trocas as T
    config=normalize(data)
    with T.LOCK:
        try:
            previous = read(out)
        except (OSError, ValueError):
            previous = {}
        if previous.get('editor_origem'):
            config['editor_origem'] = previous['editor_origem'] if previous['editor'] == config['editor'] else 'manual'
        T.write(Path(out)/'nomenclatura.json',config)
        if T.plan_path(out).exists():
            plan=T.load(out);plan['nomenclatura']=config;T.write(T.plan_path(out),plan)
        else:plan={}
    return identity(plan,out,config)

def signature(plan,out):
    from .trocas import digest
    return digest(identity(plan,out)['nome_sequencia'])
