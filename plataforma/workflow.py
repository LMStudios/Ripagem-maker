"""Estado verificável do fluxo. Navegar ou aprovar texto não autoriza pular a conferência."""
import json,re
from pathlib import Path
from . import trocas as T

def state(out):
    from . import ml_core as M
    active=next((j for j in list(M.JOBS.values()) if j.kind=='vozes' and j.status in ('na_fila','executando') and Path(j.params.get('out','')).resolve()==Path(out).resolve()),None)
    plan=T.load(out);rows=plan['itens'];selected=[r for r in rows if r.get('aprovado')];issues=[];missing=[];listen=[]
    for index,row in enumerate(rows,1):
        if not row.get('aprovado'):continue
        audio=row.get('audio',{});reason=''
        if row.get('speaker_pendente') or row.get('speaker')=='A_CONFIRMAR':reason='Confirme o speaker.'
        elif row.get('forma_pendente') and not row.get('forma_confirmada'):reason='Adapte e confirme o modo de uso.'
        elif not audio.get('fit') or not (Path(out)/audio['fit']).is_file():reason='Gere ou importe o áudio.';missing.append(row['id'])
        elif audio.get('texto_hash')!=T.digest([row['novo'],row['speaker']]):reason='O texto ou speaker mudou. Gere novamente o áudio.';missing.append(row['id'])
        elif audio.get('modo_duracao','fixo')!=plan.get('modo_duracao','fixo'):reason='Prepare a duração e aprove novamente.';missing.append(row['id'])
        elif not audio.get('aprovado'):reason='Ouça e aprove o áudio.';listen.append(row['id'])
        if reason:issues.append({'id':row['id'],'frase':index,'motivo':reason})
    if active:issues.append({'motivo':'Aguarde a geração de áudios terminar antes de preparar os takes.'})
    if not selected:issues.append({'motivo':'Selecione e salve os textos que serão alterados.'})
    # Conta ocorrências literais na transcrição, sem confundir frases/arquivos com menções.
    raw=json.loads((Path(out)/'transcricao_bruta.json').read_text());text=' '.join(str(w.get('text','')) for w in raw.get('words',[]))
    aliases=[] if plan.get('somente_valores') else [plan['produto']]+re.split(r'[,;\n]',str(plan.get('produto_aliases',''))+','+plan.get('editorial',{}).get('aliases',''))
    from .validacao import norm
    words=norm(text).split();occupied=set();mentions=0
    for alias in sorted(set(norm(a) for a in aliases if norm(a)),key=len,reverse=True):
        parts=alias.split()
        for i in range(len(words)-len(parts)+1):
            if words[i:i+len(parts)]==parts and not any(j in occupied for j in range(i,i+len(parts))):occupied.update(range(i,i+len(parts)));mentions+=1
    if not plan.get('somente_valores'):
        from . import conferencia_mencoes as CM
        mentions=sum(r['status']!='descartada' for r in CM.scan(out,plan)['itens'])
    usage=not plan.get('somente_valores') and bool(plan.get('forma',{}).get('ativo'));coverage=raw.get('recorte_transcricao');partial=bool(coverage and coverage.get('segunda_metade', True))
    stage='gerando' if active else 'textos_pendentes' if not selected else 'revisar_textos' if any(r.get('forma_pendente') and not r.get('forma_confirmada') or r.get('speaker_pendente') for r in selected) else 'pronto_para_gerar' if missing else 'aguardando_conferencia' if listen else 'pronto_para_takes'
    return {'estado':stage,'takes_liberados':bool(selected) and not issues,'pendencias':issues,'resumo':{'somente_valores':bool(plan.get('somente_valores')),'produto_antigo':plan['produto'],'produto_novo':plan['produto_novo'],'duracao_s':plan['duracao_s'],'mencoes':mentions,'frases':len(rows),'selecionadas':len(selected),'geradas':sum(bool(r.get('audio',{}).get('fit') and (Path(out)/r['audio']['fit']).is_file()) for r in selected),'sem_audio':len(missing),'para_ouvir':len(listen),'aprovadas':sum(bool(r.get('audio',{}).get('aprovado')) for r in selected),'modo_uso':usage,'complexidade':'Complexa' if usage and mentions>60 else 'Simples','transcricao_parcial':partial,'cobertura':coverage or 'Transcrição disponível'}}

def require_takes(out):
    result=state(out)
    if not result['takes_liberados']:
        detail=result['pendencias'][0];raise ValueError('Conclua a conferência dos áudios antes dos takes. '+('Frase '+str(detail['frase'])+': ' if detail.get('frase') else '')+detail['motivo'])
    return result
