"""Preferências sem segredos, consentimento por amostra e pitch sem retranscrição."""
import hashlib,json
from pathlib import Path
from . import trocas as T

def sample_scope(out,plan,provider,voices):
    speakers=sorted({r['speaker'] for r in plan['itens'] if r.get('aprovado')})
    records=[]
    for speaker in speakers:
        voice=voices.get(speaker,'');sample=plan.get('samples',{}).get(speaker,{})
        file=(Path(out)/sample.get('arquivo','')).resolve()
        fingerprint=hashlib.sha256(file.read_bytes()).hexdigest() if not voice and file.is_relative_to(Path(out).resolve()) and file.is_file() else ''
        records.append([speaker,voice,fingerprint])
    return T.digest([provider,records])

def preferences(out,body=None):
    from . import vozes as V,armazenamento as S
    with T.LOCK:
        plan=T.load(out);saved=plan.get('preferencias_voz',{});defaults=S.read().get('preferencias_voz',{})
        if body is not None:
            provider=body.get('provider');model=body.get('model');voices=body.get('voices',{})
            if provider not in V.MODELS or model not in V.MODELS[provider]:raise ValueError('Serviço ou modelo de voz inválido.')
            if not isinstance(voices,dict) or any(k not in plan['speakers'] or not isinstance(v,str) or len(v)>200 for k,v in voices.items()):raise ValueError('Mapeamento de vozes inválido.')
            saved={k:body.get(k) is True for k in ('autoriza_envio','autoriza_clonagem','excluir_clones','autofit')}
            saved.update(provider=provider,model=model,voices=voices,escopo=sample_scope(out,plan,provider,voices))
            plan['preferencias_voz']=saved;T.write(T.plan_path(out),plan)
            with S.LOCK:
                cfg=S.read();cfg['preferencias_voz']={k:saved[k] for k in ('provider','model','excluir_clones','autofit')};S.CONFIG.parent.mkdir(parents=True,exist_ok=True)
                tmp=S.CONFIG.with_suffix('.tmp');tmp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2));tmp.replace(S.CONFIG)
        result=dict(defaults,**saved)
        if saved.get('escopo')!=sample_scope(out,plan,result.get('provider','elevenlabs'),result.get('voices',{})):
            result.update(autoriza_envio=False,autoriza_clonagem=False)
        return result

def ensure_samples(out):
    from . import ml_core as M
    plan=T.load(out);wanted={r['speaker'] for r in plan['itens'] if r.get('aprovado') and r['speaker']!='A_CONFIRMAR'}
    samples=plan.get('samples',{})
    missing=[s for s in wanted if not samples.get(s) or not (Path(out)/samples[s]['arquivo']).is_file()]
    if not missing:return {'pronto':True,'samples':samples}
    with T.LOCK:
        active=next((j for j in list(M.JOBS.values()) if j.kind=='amostras' and j.status in ('na_fila','executando') and Path(j.params.get('out','')).resolve()==Path(out).resolve()),None)
        return {'pronto':False,'job':(active or M.submit('amostras','Preparar amostras locais',T.sample_job,'render',out=str(out))).to_dict()}

def cached_pitch(out):
    from . import validacao as V
    file=Path(out)/'transcricao_bruta.json';signature=hashlib.sha256(file.read_bytes()).hexdigest()
    with T.LOCK:
        plan=T.load(out);cache=plan.get('pitch_transcricao',{})
        if cache.get('assinatura')!=signature:
            raw=json.loads(file.read_text());words=[{'w':w['text'],'s':w['start']/1000,'e':w['end']/1000} for w in raw.get('words',[])]
            report=V.analyze(words,[]);cache={'assinatura':signature,'pitch':report['pitch'],'candidatos':report['candidatos_pitch']};plan['pitch_transcricao']=cache;T.write(T.plan_path(out),plan)
    return cache

def mapped_pitch(plan,out):
    from . import montagem as MT,fechamento as F
    found=(plan.get('pitch_transcricao') or {}).get('pitch')
    if not found:return None
    rows=sorted([r for r in plan['itens'] if r.get('aprovado') and r.get('audio',{}).get('fit')],key=lambda r:r['inicio_ms'])
    if any(not (Path(out)/r['audio']['fit']).is_file() for r in rows):return dict(found,confirmar=True)
    # Dentro de uma fala regravada não há alinhamento palavra a palavra: pedir confirmação.
    if any(r['inicio_ms']<=found['tempo']*1000<r['fim_ms'] for r in rows):return dict(found,confirmar=True)
    changes=MT.edits(out,rows,{'fps':plan['fps']});cuts=F.windows(changes,plan['fps']);frame=MT.shift(round(found['tempo']*plan['fps']),changes)
    return dict(found,tempo=F.position(frame,cuts)/plan['fps'],confirmar=False)
