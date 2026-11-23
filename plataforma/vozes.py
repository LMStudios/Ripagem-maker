"""Adaptadores de voz. Chaves ficam somente na memória do processo, nunca nos jobs."""
import re
import threading
import uuid
from pathlib import Path
import requests
from . import ml_core as M
from . import trocas as T
from . import credenciais as C
from . import editorial as E

KEYS={};KEY_LOCK=threading.Lock()
MODELS={'elevenlabs':{'eleven_multilingual_v2','eleven_turbo_v2_5','eleven_v3'},'minimax':{'speech-2.8-hd','speech-2.8-turbo'}}

def configure(provider,key):
    if provider not in MODELS:raise ValueError('Escolha ElevenLabs ou MiniMax.')
    C.save(key,provider)
    with KEY_LOCK:KEYS[provider]=key.strip()
    return {'configurado':True,'servico':provider,'armazenamento':'Cofre do sistema; permanece após fechar e atualizar.'}

def forget():
    for provider in MODELS:C.remove(provider)
    with KEY_LOCK:KEYS.clear()
    return {'configurado':False}


def response_ok(response,key):
    if not response.ok:
        raise ValueError(f'Falha no serviço de voz (HTTP {response.status_code}). Confira chave, permissões, créditos e disponibilidade do modelo.')
    return response

def minimax_ok(response,key):
    data=response_ok(response,key).json()
    if data.get('base_resp',{}).get('status_code',0)!=0:
        code=data['base_resp']['status_code']
        raise ValueError(f'MiniMax recusou a solicitação (código {code}). Confira permissões, créditos e voz/modelo selecionados.')
    return data

def clone(provider,key,path,label):
    if provider=='elevenlabs':
        with open(path,'rb') as fp:r=requests.post('https://api.elevenlabs.io/v1/voices/add',headers={'xi-api-key':key},data={'name':label},files=[('files',(Path(path).name,fp,'audio/mpeg'))],timeout=(20,180))
        data=response_ok(r,key).json();voice=data.get('voice_id')
        if not voice:raise ValueError('ElevenLabs não retornou o identificador da voz.')
        return voice,bool(data.get('requires_verification'))
    if T.probe(path)['duration']<10:raise ValueError('MiniMax exige pelo menos 10 segundos de amostra deste speaker. Use um ID de voz existente ou outro trecho.')
    headers={'Authorization':'Bearer '+key}
    with open(path,'rb') as fp:r=requests.post('https://api.minimax.io/v1/files/upload',headers=headers,data={'purpose':'voice_clone'},files={'file':(Path(path).name,fp,'audio/mpeg')},timeout=(20,180))
    fileid=minimax_ok(r,key).get('file',{}).get('file_id')
    if not fileid:raise ValueError('MiniMax não retornou o identificador da amostra.')
    voice='DRStudio'+uuid.uuid4().hex
    r=requests.post('https://api.minimax.io/v1/voice_clone',headers=headers,json={'file_id':fileid,'voice_id':voice,'need_noise_reduction':False,'need_volume_normalization':False},timeout=(20,180))
    minimax_ok(r,key);return voice,False

def delete_created(provider,key,voice):
    if provider=='elevenlabs':r=requests.delete('https://api.elevenlabs.io/v1/voices/'+voice,headers={'xi-api-key':key},timeout=(20,60));response_ok(r,key)
    else:
        r=requests.post('https://api.minimax.io/v1/delete_voice',headers={'Authorization':'Bearer '+key},json={'voice_type':'voice_cloning','voice_id':voice},timeout=(20,60));minimax_ok(r,key)

def speech(provider,key,voice,text,model,previous='',following=''):
    if provider=='elevenlabs':
        body={'text':text,'model_id':model}
        if model!='eleven_v3':body.update(previous_text=previous[-300:],next_text=following[:300])
        r=requests.post('https://api.elevenlabs.io/v1/text-to-speech/'+voice,params={'output_format':'mp3_44100_128'},headers={'xi-api-key':key},json=body,timeout=(20,180))
        return response_ok(r,key).content
    r=requests.post('https://api.minimax.io/v1/t2a_v2',headers={'Authorization':'Bearer '+key},json={'model':model,'text':text,'stream':False,'output_format':'hex','language_boost':'auto','voice_setting':{'voice_id':voice,'speed':1,'vol':1,'pitch':0},'audio_setting':{'sample_rate':32000,'bitrate':128000,'format':'mp3','channel':1}},timeout=(20,180))
    data=minimax_ok(r,key);encoded=data.get('data',{}).get('audio')
    if not encoded:raise ValueError('MiniMax não retornou áudio.')
    try:return bytes.fromhex(encoded)
    except ValueError:raise ValueError('Resposta de áudio inesperada do MiniMax.')

def selected_rows(plan,options,out=None):
    if 'row_ids' in options:
        ids=options['row_ids']
        if not isinstance(ids,list) or not ids or any(not isinstance(v,str) or not v for v in ids) or len(set(ids))!=len(ids):
            raise ValueError('Informe as frases que devem ser geradas novamente.')
        by_id={r['id']:r for r in plan['itens']}
        if any(rid not in by_id for rid in ids):raise ValueError('Uma das frases não existe mais. Atualize a lista e tente novamente.')
        if any(not by_id[rid]['aprovado'] for rid in ids):raise ValueError('Selecione e aprove o texto desta frase antes de regenerar o áudio.')
        # Pendências de outras frases não ampliam nem bloqueiam esta solicitação.
        plan=dict(plan,itens=[r for r in plan['itens'] if r['id'] in set(ids)])
    rows=T.approved(plan)
    if options.get('somente_pendentes'):
        rows=[r for r in rows if not r.get('audio',{}).get('fit') or r.get('audio',{}).get('texto_hash')!=T.digest([r['novo'],r['speaker']]) or (out is not None and not (Path(out)/r['audio']['fit']).exists())]
        if not rows:raise ValueError('Nenhuma frase precisa de geração. Os áudios prontos foram preservados.')
    return rows

def validate(out,options):
    provider=options.get('provider');model=options.get('model')
    if provider not in MODELS or model not in MODELS[provider]:raise ValueError('Serviço ou modelo inválido.')
    if not options.get('autoriza_envio'):raise ValueError('Confirme o envio das frases e o consumo de créditos do serviço selecionado.')
    try:key=C.key(provider)
    except RuntimeError as error:raise ValueError(str(error)) from None
    plan=T.load(out);rows=selected_rows(plan,options,out);mapping=options.get('voices',{})
    speakers={r['speaker'] for r in rows}
    if any(not str(mapping.get(s,'')).strip() for s in speakers):
        if not options.get('autoriza_clonagem'):raise ValueError('Confirme que tem autorização para clonar e que ouviu as amostras dos speakers.')
        if any(not mapping.get(s) and s not in plan.get('samples',{}) for s in speakers):raise ValueError('Prepare e ouça as amostras antes de clonar, ou informe um ID de voz para cada speaker.')
    for voice in mapping.values():
        if voice and not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',str(voice)):raise ValueError('ID de voz inválido.')
    return key

def submit(out,options):
    key=validate(out,options)
    rows=selected_rows(T.load(out),options,out)
    # O segredo é capturado pela função, não colocado nos parâmetros serializados.
    snapshot=T.digest([[r['id'],r['novo'],r['speaker']] for r in rows])
    def run(job,out=out):
        if 'row_ids' in options and T.digest([[r['id'],r['novo'],r['speaker']] for r in selected_rows(T.load(out),options,out)])!=snapshot:
            raise ValueError('A frase mudou enquanto aguardava na fila. Confira o texto e tente regenerar novamente.')
        return generate(job,out,options,key)
    return M.submit('vozes','Regenerar áudio de uma frase' if options.get('row_ids') else 'Gerar falas aprovadas por speaker',run,'render',dedupe_key=T.digest([str(Path(out).resolve()),options,[[r['id'],r['novo'],r['speaker']] for r in rows]]),out=str(out))

def generate(job,out,options,key):
    provider=options['provider'];model=options['model'];plan=T.load(out);rows=selected_rows(plan,options,out)
    mapping={s:str(v).strip() for s,v in options.get('voices',{}).items()};created=[];results=[];warnings=[];blocked={}
    folder=Path(out)/'trocas'/'gerados';folder.mkdir(parents=True,exist_ok=True)
    def progress(stage,row=None):
        job.pct=len(results)/len(rows)
        job.progress={'tipo':'vozes','fase':stage,'processadas':len(results),'total':len(rows),
            'frase':next((n for n,r in enumerate(plan['itens'],1) if row and r['id']==row['id']),None),
            'speaker':row['speaker'] if row else '',
            'erros':sum('erro' in r for r in results),'reutilizadas':sum(r.get('status')=='reutilizado' for r in results)}
    progress('Preparando geração')
    try:
        for i,row in enumerate(rows):
            if job.cancel:raise M.Cancelled()
            spoken=E.pronunciation(plan,row['novo'])
            fingerprint=T.digest([row['novo'],spoken,row['speaker'],provider,model,options.get('voices',{}).get(row['speaker'],''),bool(options.get('autofit',True))])
            audio=row.get('audio',{})
            if not options.get('regenerar') and audio.get('assinatura')==fingerprint and audio.get('fit') and (Path(out)/audio['fit']).exists():
                results.append({'id':row['id'],'status':'reutilizado'});progress('Áudio reutilizado',row);continue
            try:
                speaker=row['speaker']
                if speaker in blocked:raise ValueError(blocked[speaker])
                voice=mapping.get(speaker)
                if not voice:
                    sample=plan['samples'][speaker];job.step='Clonando speaker '+speaker;progress('Criando voz do speaker',row)
                    voice,verification=clone(provider,key,Path(out)/sample['arquivo'],'DR Studio · Speaker '+speaker+' · '+job.id)
                    created.append(voice);mapping[speaker]=voice
                    if verification:
                        blocked[speaker]='Esta voz exige verificação no ElevenLabs. Confira sua conta e informe o ID de uma voz verificada.'
                        raise ValueError(blocked[speaker])
                job.step=f'Gerando frase {i+1} de {len(rows)} · Speaker {speaker}';progress('Gerando áudio',row)
                # Frases selecionadas podem estar minutos distantes: não enviar vizinhos como contexto.
                data=speech(provider,key,voice,spoken,model)
                if job.cancel:raise M.Cancelled()
                path=T.audio_path(out,row,'GERADO','.mp3');path.write_bytes(data);progress('Conferindo duração e ajustando áudio',row)
                audio=T.fit(job,out,row,path,options.get('autofit',True));audio.update(assinatura=fingerprint,provider=provider,model=model,voice_id=voice,texto_enviado=spoken,contexto_usado=False)
                T.record_audio(out,row['id'],audio);results.append({'id':row['id'],'status':audio['status']})
            except M.Cancelled:raise
            except Exception as error:
                message=str(error).replace(key,'[chave omitida]')
                results.append({'id':row['id'],'speaker':row['speaker'],'erro':message})
            progress('Frase processada',row)
            job.result={'resultados':results,'avisos':warnings}
    finally:
        progress('Finalizando vozes')
        if options.get('excluir_clones'):
            for voice in created:
                try:delete_created(provider,key,voice)
                except Exception:warnings.append('Não foi possível excluir um clone criado nesta geração. Confira a lista de vozes na sua conta: '+voice)
        elif created:warnings.append('Clones criados nesta geração foram mantidos na sua conta: '+', '.join(created))
    job.step='Geração concluída — ouça e aprove os áudios' if not any('erro' in r for r in results) else 'Geração encerrada com frases pendentes — confira os erros'
    progress('Concluído' if not any('erro' in r for r in results) else 'Concluído com pendências')
    return {'resultados':results,'avisos':warnings,'cobranca':'As gerações usam créditos da conta; novas tentativas podem ser cobradas.'}


def sample(out,options):
    provider=options.get('provider');model=options.get('model');voice=str(options.get('voice','')).strip()
    if provider not in MODELS or model not in MODELS[provider]:raise ValueError('Escolha serviço e modelo válidos.')
    if not options.get('autoriza_envio'):raise ValueError('Autorize o consumo de créditos para gerar a amostra.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',voice):raise ValueError('Informe um ID de voz existente para o teste de pronúncia.')
    plan=T.load(out);text=str(options.get('texto','')).strip() or plan['produto_novo']
    if len(text)>250:raise ValueError('A amostra deve ter até 250 caracteres.')
    spoken=E.pronunciation(plan,text)
    try:key=C.key(provider)
    except RuntimeError as error:raise ValueError(str(error)) from None
    def run(job):
        target=Path(out)/'trocas'/'amostras'/('PRONUNCIA_'+uuid.uuid4().hex[:8]+'.mp3');target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(speech(provider,key,voice,spoken,model))
        with T.LOCK:
            current=T.load(out);current['voz_teste']={'arquivo':str(target.relative_to(out)),'texto':text,'texto_enviado':spoken,'provider':provider,'voice_id':voice};T.write(T.plan_path(out),current)
        job.step='Amostra pronta — ouça antes de gerar o lote';return {'arquivo':str(target.relative_to(out))}
    return M.submit('pronuncia','Testar pronúncia com créditos',run,'render')
