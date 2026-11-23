"""Preparação do áudio e timestamps sempre relativos à VSL completa."""
import copy
import json
import math
import subprocess
from pathlib import Path


def prepare(src,ffmpeg,ffprobe,second_half=True):
    r=subprocess.run([ffprobe,'-v','error','-show_format','-show_streams','-of','json',str(src)],capture_output=True,text=True,check=True)
    data=json.loads(r.stdout)
    if not any(s.get('codec_type')=='audio' for s in data.get('streams',[])):raise ValueError('Este arquivo não contém áudio para transcrever.')
    duration=float(data.get('format',{}).get('duration',0))
    if not math.isfinite(duration) or duration<=0:raise ValueError('Não foi possível ler a duração do arquivo.')
    start=duration/2 if second_half else 0
    target=Path(src).with_suffix('.transcricao.mp3')
    subprocess.run([ffmpeg,'-y','-v','error','-ss',f'{start:.6f}','-i',str(src),'-t',f'{duration-start:.6f}','-vn','-ac','1','-ar','24000','-c:a','libmp3lame','-b:a','64k',str(target)],check=True)
    return target,{'inicio_ms':round(start*1000),'fim_ms':round(duration*1000),'duracao_original_s':duration,'duracao_enviada_s':duration-start,'segunda_metade':bool(second_half)}


def restore_times(raw,selection):
    data=copy.deepcopy(raw);offset=selection['inicio_ms'];seen=set()
    def shift(item):
        if id(item) in seen:return
        seen.add(id(item))
        for key in ('start','end'):
            if key in item:item[key]+=offset
    for word in data.get('words',[]):shift(word)
    for utterance in data.get('utterances',[]) or []:
        shift(utterance)
        for word in utterance.get('words',[]):shift(word)
    data['recorte_transcricao']=selection
    data['audio_duration']=selection['duracao_original_s']
    return data


def metrics(phrases,duration):
    if not phrases:return {'primeira_mencao_ms':None,'janela_troca_ms':None,'duracao_vsl_ms':round(duration*1000),'quantidade':0}
    first=min(p.get('primeira_mencao_ms',p['start']) for p in phrases)
    return {'primeira_mencao_ms':first,'janela_troca_ms':max(0,round(duration*1000)-first),'duracao_vsl_ms':round(duration*1000),'quantidade':len(phrases),'soma_frases_ms':sum(max(0,p['end']-p['start']) for p in phrases)}
