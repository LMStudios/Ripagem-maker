"""Rotas locais do fluxo de troca; nenhum segredo é persistido nos parâmetros da fila."""
import json
import uuid
import threading
from pathlib import Path
from . import ml_core as M
from . import armazenamento as S
from . import trocas as T
from . import vozes as V
from . import visuais as VIS
from . import perfis as P
from . import editorial as E, automatico as AUTO

_UPLOAD_GUARD=threading.Lock()
_UPLOADS=set()

def handle(h,path,root):
    if not path.startswith('/fatiador/trocas/'):return False
    upload_lease=None
    try:
        if path in {'/fatiador/trocas/trilha-upload','/fatiador/trocas/amostra-upload','/fatiador/trocas/audio-upload'}:
            from urllib.parse import unquote
            from . import projetos as PR
            out=S.job_folder(unquote(h.headers.get('X-Folder','')),root)
            if not S.is_job(out,root):raise ValueError('Trabalho não encontrado.')
            with _UPLOAD_GUARD:
                key=str(out.resolve())
                if key in _UPLOADS:raise ValueError('Já há um envio de áudio neste projeto. Aguarde terminar.')
                _UPLOADS.add(key);upload_lease=key
            if PR.moving(out):raise ValueError('Aguarde a movimentação do projeto antes de importar arquivos.')
            if any(j.kind in {'vozes','amostras','duracao'} and j.status in ('na_fila','executando') and
                   Path(j.params.get('out','')).resolve()==out.resolve() for j in list(M.JOBS.values())):
                raise ValueError('Aguarde o preparo de áudios deste projeto terminar antes de importar outro arquivo.')
        if path=='/fatiador/trocas/trilha-upload':
            from urllib.parse import unquote
            out=S.job_folder(unquote(h.headers.get('X-Folder','')),root)
            if not S.is_job(out,root):raise ValueError('Trabalho não encontrado.')
            if AUTO.active(out):raise ValueError('Pause a execução automática antes de importar arquivos neste projeto.')
            size=int(h.headers.get('Content-Length','0'))
            if not 0<size<=300*1024*1024:raise ValueError('Envie uma trilha de até 300 MB.')
            suffix=Path(unquote(h.headers.get('X-Filename',''))).suffix.lower()
            if suffix not in {'.mp3','.wav','.m4a','.aac','.ogg','.flac','.aiff'}:raise ValueError('Escolha um arquivo de áudio.')
            target=out/'trocas'/'trilhas'/(uuid.uuid4().hex+suffix);target.parent.mkdir(parents=True,exist_ok=True)
            try:
                from .uploads import receive
                receive(h.rfile,size,target)
                if T.probe(target)['duration']<=0:raise ValueError('Trilha sem duração válida.')
                with T.LOCK:
                    plan=T.load(out);plan['trilha']={'modo':'separada','arquivo':str(target.relative_to(out)),'nome':Path(unquote(h.headers.get('X-Filename',''))).name,'ganho_db':-18,'repetir':False};plan['revisao']=None;plan.pop('previa',None);T.write(T.plan_path(out),plan)
                result=plan['trilha']
            except Exception:
                target.unlink(missing_ok=True);raise
        elif path=='/fatiador/trocas/amostra-upload':
            from urllib.parse import unquote
            from . import projetos as PR
            out=S.job_folder(unquote(h.headers.get('X-Folder','')),root)
            if not S.is_job(out,root):raise ValueError('Trabalho não encontrado.')
            if AUTO.active(out) or PR.moving(out):raise ValueError('Pause o trabalho automático ou aguarde a movimentação do projeto.')
            speaker=unquote(h.headers.get('X-Speaker',''))
            if speaker not in T.load(out)['speakers'] or speaker=='A_CONFIRMAR':raise ValueError('Speaker inválido.')
            if any(j.kind in {'vozes','amostras'} and j.status in ('na_fila','executando') and
                   Path(j.params.get('out','')).resolve()==out.resolve() for j in list(M.JOBS.values())):
                raise ValueError('Aguarde a tarefa de voz ou amostra terminar antes de substituir a gravação.')
            size=int(h.headers.get('Content-Length','0'))
            if not 0<size<=50*1024*1024:raise ValueError('Escolha um áudio de até 50 MB e 2 minutos.')
            name=Path(unquote(h.headers.get('X-Filename','amostra'))).name
            suffix=Path(name).suffix.lower()
            if suffix not in {'.mp3','.wav','.m4a','.aac','.ogg','.flac','.aiff','.aif','.webm'}:
                raise ValueError('Escolha um arquivo de áudio.')
            target=out/'trocas/amostras/importadas'/(uuid.uuid4().hex+suffix)
            target.parent.mkdir(parents=True,exist_ok=True)
            try:
                from .uploads import receive
                receive(h.rfile,size,target)
                result=M.submit('amostras','Substituir amostra do speaker '+speaker,T.replace_sample_job,'render',
                                out=str(out),speaker=speaker,uploaded=str(target),name=name).to_dict()
            except Exception:
                target.unlink(missing_ok=True);raise
        elif path=='/fatiador/trocas/audio-upload':
            from urllib.parse import unquote
            out=S.job_folder(unquote(h.headers.get('X-Folder','')),root)
            if not S.is_job(out,root):raise ValueError('Trabalho não encontrado.')
            plan=T.load(out);rid=h.headers.get('X-Row','');row=next((r for r in plan['itens'] if r['id']==rid),None)
            if not row:raise ValueError('Trecho não encontrado.')
            if AUTO.active(out):raise ValueError('Pause a execução automática antes de importar arquivos neste projeto.')
            size=int(h.headers.get('Content-Length','0'))
            if size<=0 or size>50*1024*1024:raise ValueError('Envie um áudio de até 50 MB.')
            suffix=Path(unquote(h.headers.get('X-Filename',''))).suffix.lower()
            if suffix not in {'.mp3','.wav','.m4a','.aac','.ogg','.flac','.aiff','.aif','.mp4','.webm'}:raise ValueError('Escolha um arquivo de áudio compatível.')
            target=out/'trocas'/'importados'/(uuid.uuid4().hex+suffix);target.parent.mkdir(parents=True,exist_ok=True)
            from .uploads import receive
            receive(h.rfile,size,target)
            def run(job,out):
                out=Path(out)
                try:
                    audio=T.fit(job,out,row,target,True);audio['provider']='arquivo_importado';T.record_audio(out,rid,audio)
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
                job.step='Áudio importado — confira a duração e ouça';return audio
            try:result=M.submit('vozes','Conferir áudio importado',run,'render',out=str(out)).to_dict()
            except Exception:
                target.unlink(missing_ok=True);raise
        else:
            n=int(h.headers.get('Content-Length','0'))
            if not 0<=n<=2_000_000:raise ValueError('Solicitação muito grande.')
            body=json.loads(h.rfile.read(n) or b'{}')
            if path=='/fatiador/trocas/chave':result=V.configure(body.get('provider'),body.get('key',''))
            elif path=='/fatiador/trocas/esquecer-chave':result=V.forget()
            elif path=='/fatiador/trocas/perfis':result=P.read()
            elif path=='/fatiador/trocas/perfil-salvar':result=P.save(body)
            elif path=='/fatiador/trocas/chave-status':
                from . import credenciais as C
                result={'configurados':[p for p in V.MODELS if C.status(p)['configurada'] or p in V.KEYS]}
            else:
                out=S.job_folder(body.get('folder',''),root)
                if not S.is_job(out,root):raise ValueError('Trabalho não encontrado.')
                from . import projetos as PR
                if PR.moving(out) and not path.endswith(('-estado','/plano','/fluxo-estado','/perfis')):raise ValueError('Este projeto está sendo movido para outra pasta. Aguarde a conclusão para continuar editando.')
                action=path.rsplit('/',1)[1]
                read_only=action.endswith('-estado') or action in {'estado','pasta-audios','pitch-transcricao','workflow','preflight','studio-tempo','studio-resumo'}
                read_only=read_only or action=='plano' and not body.get('rebuild') or action=='preferencias-voz' and body.get('salvar') is not True
                read_only = read_only or action=='nomenclatura' and body.get('salvar') is not True
                read_only = read_only or action=='otimizacao' and 'ativar' not in body
                if AUTO.active(out) and not read_only and action not in {'automatico-parar','automatico-continuar'}:
                    raise ValueError('Pause a execução automática antes de editar este projeto.')
                from . import workflow as W
                review_xml=action=='entrega-rapida' and body.get('revisao_pendencias') is True
                if not review_xml and path in {'/fatiador/trocas/visual-preencher-aleatorio','/fatiador/trocas/visual-automatico','/fatiador/trocas/visual-sortear','/fatiador/trocas/visual-preparar','/fatiador/trocas/visual-exportar','/fatiador/trocas/entrega-rapida'}:W.require_takes(out)
                if action=='automatico-estado':result=AUTO.view(out)
                elif action=='automatico-continuar':result=AUTO.submit(out).to_dict()
                elif action=='automatico-parar':result=AUTO.pause(out)
                elif path in ('/fatiador/trocas/studio-tempo', '/fatiador/trocas/studio-resumo'):
                    from . import studio
                    plan = T.load(out)
                    if path.endswith('studio-tempo') and 'xml_salvo' in body:
                        result = studio.confirm_xml_save(out, body['xml_salvo'], plan, download=body.get('copiar_para_downloads'))
                        if getattr(h, 'editor_profile', None):
                            from . import equipe_api, identidade_entrega
                            editor = identidade_entrega.identity(plan, out)['config']['editor']
                            equipe_api.xml_saved(out, h.editor_profile, result, editor)
                    else:
                        if path.endswith('studio-tempo'):
                            studio.heartbeat(out, body.get('pausado'), plan, body.get('encerrar') is True)
                        result = studio.summary(out, plan)
                elif path=='/fatiador/trocas/nomenclatura':
                    from . import identidade_entrega as ID
                    result=ID.save(out,body.get('config',{})) if body.get('salvar') is True else ID.identity(T.load(out),out)
                    if body.get('salvar') is True:result['plano']=T.load(out)
                elif path.startswith('/fatiador/trocas/finalizacao-'):
                    from . import finalizacao as F
                    if path.endswith('estado'): result=F.state(out)
                    elif path.endswith('confirmar'): result=F.confirm(out,body.get('conferida'))
                    elif path.endswith('entregar'):
                        if body.get('sem_previa') and body.get('autoriza_sem_previa') is not True: raise ValueError('Confirme a entrega sem prévia.')
                        result=M.submit('entrega_completa','Preparar entrega completa com legenda',F.deliver,'render',out=str(out),sem_previa=body.get('sem_previa') is True,assinatura=body.get('assinatura')).to_dict()
                    else: raise ValueError('Ação de finalização inválida.')
                elif path=='/fatiador/trocas/pasta-audios':result={'pasta':str((out/'trocas/encaixados').resolve())}
                elif path=='/fatiador/trocas/preferencias-voz':
                    from . import experiencia as X
                    result=X.preferences(out,body.get('config') if body.get('salvar') is True else None)
                elif path=='/fatiador/trocas/amostras-automaticas':
                    from . import experiencia as X
                    result=X.ensure_samples(out)
                elif path=='/fatiador/trocas/pitch-transcricao':
                    from . import experiencia as X
                    result=X.cached_pitch(out);result=dict(result,atual=X.mapped_pitch(T.load(out),out))
                elif path.startswith('/fatiador/trocas/fala-visual-'):
                    from . import falas_visuais as FV
                    if action=='fala-visual-estado':result=FV.view(out)
                    elif action=='fala-visual-revisar':result=FV.review(out,body)
                    elif action=='fala-visual-autorizar-todas':result=FV.authorize_all(out,body)
                    elif action=='fala-visual-audio':result=M.submit('conferencia_fala_visual','Conferir áudio do trecho visual',FV.recheck,'asr',dedupe_key=str(out)+':'+str(body.get('id')),out=str(out),candidate_id=body.get('id'),expected=body.get('base')).to_dict()
                    else:raise ValueError('Ação de conferência inválida.')
                elif path in ('/fatiador/trocas/deteccao-estado','/fatiador/trocas/deteccao-config','/fatiador/trocas/deteccao-analisar','/fatiador/trocas/deteccao-revisar','/fatiador/trocas/deteccao-automatico'):
                    from . import deteccao_visual as DV
                    if path.endswith('automatico'):
                        result=DV.automatic(out,body.get('automatico'))
                        result['estado']=DV.view(out)
                    elif path.endswith('estado'):result=DV.view(out)
                    elif path.endswith('config'):result=DV.config(out,body)
                    elif path.endswith('revisar'):result=DV.review(out,body)
                    else:
                        DV.config(out,body)
                        result=M.submit('deteccao_visual','Procurar o produto antigo na imagem',DV.analyze_job,'visual',dedupe_key=str(out),out=str(out)).to_dict()
                elif path.startswith('/fatiador/trocas/deteccao-referencia') or path=='/fatiador/trocas/deteccao-manual':
                    from . import deteccao_visual as DV, referencias_visuais as RV
                    action=path.rsplit('/',1)[1]
                    if action=='deteccao-referencias':result=RV.view(out)
                    elif action=='deteccao-referencia-quadro':result=RV.frame(out,body)
                    elif action=='deteccao-referencia-salvar':result=RV.add(out,body,replace=body.get('substituir') or None)
                    elif action=='deteccao-referencia-remover':result=RV.remove(out,str(body.get('id','')))
                    elif action=='deteccao-manual':result=DV.add_manual(out,body)
                    else:raise ValueError('Ação de referência desconhecida.')
                elif path.startswith('/fatiador/trocas/legendas-video-'):
                    from . import legendas_video as LV
                    action=path.rsplit('legendas-video-',1)[1]
                    if action=='estado':result=LV.view(out)
                    elif action=='estilo':result=LV.save_style(out,body.get('estilo') or {})
                    elif action=='preset-salvar':result=LV.save_preset(body.get('nome',''),body.get('estilo') or {})
                    elif action=='preset-excluir':result=LV.delete_preset(body.get('nome',''))
                    elif action=='previa':
                        LV.save_style(out,body.get('estilo') or {})
                        result=M.submit('legendas_previa','Prévia do vídeo com legendas',LV.preview_job,'render',dedupe_key=str(out),out=str(out),inicio=body.get('inicio')).to_dict()
                    elif action=='render':
                        LV.save_style(out,body.get('estilo') or {})
                        result=M.submit('legendas_render','Renderizar vídeo com legendas',LV.render_job,'render',dedupe_key=str(out),out=str(out)).to_dict()
                    else:raise ValueError('Ação de legenda desconhecida.')
                elif path=='/fatiador/trocas/legendas-preparar-base':
                    from . import legendas as LG
                    if not W.state(out)['takes_liberados']:
                        raise ValueError('Aprove os áudios antes de preparar a base da legenda.')
                    result=M.submit('legendas_base','Preparar base da legenda',LG.prepare_base_job,'asr',
                                    dedupe_key=str(out),out=str(out)).to_dict()
                elif path in ('/fatiador/trocas/legendas-estado','/fatiador/trocas/legendas-gerar'):
                    from . import legendas as LG
                    if path.endswith('estado'):result=LG.view(out)
                    else:result=M.submit('legendas','Gerar legendas da montagem',LG.generate_job,'asr',dedupe_key=str(out),out=str(out),config=body.get('config') or {}).to_dict()
                elif path=='/fatiador/trocas/workflow':result=W.state(out)
                elif path=='/fatiador/trocas/renomear-entrega':result=T.rename_delivery(out)
                elif path=='/fatiador/trocas/localizar-entrega':
                    from . import sistema
                    result=sistema.localizar_entrega(out,body.get('arquivo',''))
                elif path=='/fatiador/trocas/abrir-entrega':
                    from . import sistema
                    result=sistema.revelar_entrega(out,body.get('arquivo',''))
                elif path=='/fatiador/trocas/visual-marcar-manual':result=VIS.mark_manual(out,body.get('mentions',[]),body.get('autorizado'))
                elif path=='/fatiador/trocas/visual-frestas':result=VIS.gap_report(out)
                elif path=='/fatiador/trocas/visual-frestas-marcar':result=VIS.mark_gaps(out,[str(i) for i in body.get('ids',[])],body.get('autorizado'))
                elif path=='/fatiador/trocas/visual-frestas-desmarcar':result=VIS.unmark_gaps(out,[str(i) for i in body.get('ids',[])])
                elif path=='/fatiador/trocas/visual-frestas-repreparar':result=M.submit('visual_fresta','Refazer takes do intervalo',VIS.reprepare_gap_job,'render',dedupe_key=str(out),out=str(out),ids=[str(i) for i in body.get('ids',[])]).to_dict()
                elif path=='/fatiador/trocas/conferencia-final-estado':
                    from . import conferencia_final as CF
                    result=CF.view(out)
                elif path=='/fatiador/trocas/conferencia-final':
                    from . import conferencia_final as CF
                    video=CF.check_path(body.get('caminho'))
                    result=M.submit('conferencia_final','Conferência final do vídeo exportado',CF.check_job,'asr',dedupe_key=str(out)+':final',out=str(out),caminho=str(video)).to_dict()
                elif path=='/fatiador/trocas/broll-estado':
                    from . import broll as BR
                    result=BR.view(out)
                elif path=='/fatiador/trocas/broll-buscar':
                    from . import broll as BR
                    result=M.submit('broll','Buscar b-roll para a frase',BR.search_job,'visual',dedupe_key=str(out)+':broll:'+str(body.get('frase','')),out=str(out),frase=str(body.get('frase','')),consulta=str(body.get('consulta','')),quantidade=max(2,min(10,int(body.get('quantidade') or 6)))).to_dict()
                elif path=='/fatiador/trocas/broll-link':
                    from . import broll as BR
                    BR.source_of(body.get('url'))
                    result=M.submit('broll','Adicionar vídeo de b-roll pelo link',BR.link_job,'visual',dedupe_key=str(out)+':broll-link:'+str(body.get('url','')),out=str(out),frase=str(body.get('frase','')),url=str(body.get('url',''))).to_dict()
                elif path=='/fatiador/trocas/broll-links':
                    from . import broll as BR
                    urls=[str(u) for u in (body.get('urls') or [])][:20]
                    for u in urls:BR.source_of(u)
                    result=M.submit('broll','Baixar b-roll coletado',BR.links_job,'visual',dedupe_key=str(out)+':broll:'+str(body.get('frase','')),out=str(out),frase=str(body.get('frase','')),urls=urls,consulta=str(body.get('consulta',''))[:120],fonte=str(body.get('fonte',''))[:20]).to_dict()
                elif path=='/fatiador/trocas/broll-escolher':
                    from . import broll as BR
                    result=BR.choose(out,str(body.get('frase','')),str(body.get('candidato') or ''))
                elif path=='/fatiador/trocas/visual-conferencia':
                    from . import conferencia_visual as CV
                    result=CV.summary(out)
                elif path=='/fatiador/trocas/visual-aparicao-takes':
                    from . import conferencia_visual as CV
                    result=CV.takes_for(out,str(body.get('id','')))
                elif path=='/fatiador/trocas/visual-estado':result=VIS.current_state(out)
                elif path=='/fatiador/trocas/visual-biblioteca':result=M.submit('visual_biblioteca','Ler materiais dos potes',VIS.scan,'render',out=str(out),root=body.get('root','')).to_dict()
                elif path=='/fatiador/trocas/visual-adicionar':result=VIS.add(out,body)
                elif path=='/fatiador/trocas/visual-detectar':result=VIS.detect(out)
                elif path=='/fatiador/trocas/visual-salvar':result=VIS.save(out,body)
                elif path=='/fatiador/trocas/visual-automatico':result=M.submit('visual_automatico','Preparar takes automaticamente',VIS.automatic,'render',out=str(out),root=body.get('root',''),max_clip_s=body.get('max_clip_s',6)).to_dict()
                elif path=='/fatiador/trocas/visual-preencher-aleatorio':
                    if body.get('autorizado') is not True:raise ValueError('Autorize o uso de potes aleatórios para as janelas pendentes.')
                    ids=body.get('mentions')
                    if not isinstance(ids,list) or not all(isinstance(v,str) for v in ids):raise ValueError('Informe as janelas pendentes.')
                    result=M.submit('visual_aleatorio','Preencher pendências com potes aleatórios',VIS.fill_random_job,'render',out=str(out),mentions=ids,expected=VIS.signature(VIS.load(out))).to_dict()
                elif path=='/fatiador/trocas/visual-trocar-take':result=VIS.replace_segment(out,body)
                elif path=='/fatiador/trocas/visual-sortear':result=M.submit('visual_distribuicao','Distribuir takes',VIS.schedule_job,'render',out=str(out)).to_dict()
                elif path=='/fatiador/trocas/visual-preparar':result=M.submit('visual_preparo','Preparar sobreposições V2',VIS.prepare,'render',out=str(out)).to_dict()
                elif path=='/fatiador/trocas/visual-previa':result=M.submit('visual_previa','Prévia de sobreposição',VIS.preview,'render',out=str(out),mention=body.get('mention','')).to_dict()
                elif path=='/fatiador/trocas/visual-exportar':result=T.export_xml(out,visual_only=True)
                elif path in ('/fatiador/trocas/ofertas-estado','/fatiador/trocas/ofertas-adaptar'):
                    from . import ofertas as O, valores as VAL
                    if path.endswith('estado'):
                        file=Path(out)/'trocas/ofertas.json'
                        result=json.loads(file.read_text()) if file.exists() else {}
                    else:
                        result=O.apply(out,O.preview(out,body,VAL.RX_PRICE,VAL.price_key))
                elif path=='/fatiador/trocas/otimizacao':
                    from . import otimizacao as OT
                    result=OT.state(out,body)
                elif path=='/fatiador/trocas/plano':
                    from . import otimizacao as OT
                    optimize=OT.active(out);prices=body.get('precos',False) or optimize;only=optimize
                    if body.get('rebuild') or not T.plan_path(out).exists():result=T.build(out,body.get('product',''),prices,only_prices=only)
                    else:
                        result=T.load(out)
                        if result['produto']!=body.get('product') or result.get('somente_valores',False)!=only:result=T.build(out,body.get('product',''),prices,only_prices=only)
                elif path=='/fatiador/trocas/forma':
                    from . import otimizacao as OT
                    if OT.active(out):raise ValueError('Este trabalho altera somente preços e kits, sem adaptar o modo de uso.')
                    plan=T.load(out);result=T.build(out,plan['produto'],plan.get('incluir_precos',False),body.get('forma',{}),only_prices=OT.active(out))
                elif path in ('/fatiador/trocas/gemini-gerar','/fatiador/trocas/gemini-estado','/fatiador/trocas/gemini-aplicar'):
                    from . import gemini_formas as G
                    if path.endswith('gerar'):result=G.submit(out,body.get('autoriza_envio'))
                    elif path.endswith('estado'):result=G.state(out)
                    else:result=G.apply(out,body.get('ids'))
                elif path=='/fatiador/trocas/editorial':result=E.settings(out,body)
                elif path=='/fatiador/trocas/speaker-confirmar':result=E.assign(out,body)
                elif path=='/fatiador/trocas/preflight':result=E.preflight(out)
                elif path=='/fatiador/trocas/trilha':result=E.soundtrack(out,body)
                elif path=='/fatiador/trocas/pronuncia-teste':result=V.sample(out,body).to_dict()
                elif path=='/fatiador/trocas/original':result=M.submit('original','Ouvir trecho original',E.original_job,'render',out=str(out),rid=body.get('id')).to_dict()
                elif path=='/fatiador/trocas/analisar-finais':result=M.submit('conferencia_audio','Conferir finais dos áudios',E.analyze_batch,'asr',out=str(out)).to_dict()
                elif path=='/fatiador/trocas/analisar-audio':result=M.submit('analise_audio','Analisar possível repetição final',E.analyze_job,'asr',out=str(out),rid=body.get('id'),motor=body.get('motor','fw')).to_dict()
                elif path=='/fatiador/trocas/recortar-audio':result=M.submit('recorte_audio','Recortar áudio localmente',E.trim_job,'render',out=str(out),rid=body.get('id'),start_ms=body.get('inicio_ms',0),end_ms=body.get('fim_ms')).to_dict()
                elif path=='/fatiador/trocas/salvar':result=T.save(out,body.get('itens',[]))
                elif path=='/fatiador/trocas/duracao':result=M.submit('duracao','Preparar áudio e espaço na timeline',T.duration_job,'render',out=str(out),mode=body.get('modo')).to_dict()
                elif path=='/fatiador/trocas/amostras':result=M.submit('amostras','Preparar amostras dos speakers',T.sample_job,'render',out=str(out)).to_dict()
                elif path=='/fatiador/trocas/regenerar-frase':
                    options=body.get('options',{})
                    if not isinstance(options,dict):raise ValueError('Configuração de voz inválida.')
                    # Esta rota nunca amplia o pedido para as outras frases do projeto.
                    options=dict(options,row_ids=[body.get('id')],regenerar=True,somente_pendentes=False)
                    result=V.submit(str(out),options).to_dict()
                elif path=='/fatiador/trocas/gerar':result=V.submit(str(out),body.get('options',{})).to_dict()
                elif path=='/fatiador/trocas/aprovar-audio':result=T.approve_audio(out,body.get('id'),body.get('hash'))
                elif path=='/fatiador/trocas/entrega-rapida':
                    if body.get('autoriza_sem_previa') is not True:raise ValueError('Confirme a autorização para entregar sem prévia.')
                    if review_xml and body.get('preparar_apenas') is True:raise ValueError('Escolha a exportação do XML de revisão.')
                    label='Preparar XML de revisão' if review_xml else 'Preparar montagem para as legendas'
                    result=M.submit('entrega_rapida',label,T.fast_delivery_job,'render',out=str(out),autorizado=True,preparar_apenas=body.get('preparar_apenas') is True,revisao_pendencias=review_xml).to_dict()
                elif path=='/fatiador/trocas/fluxo-estado':result=T.flow_state(out)
                elif path=='/fatiador/trocas/entrega':result=T.export_reviewed(out,body.get('assinatura'))
                elif path=='/fatiador/trocas/exportar':result=T.export_xml(out)
                elif path=='/fatiador/trocas/previa-trocas':result=M.submit('previa_trocas','Preparar prévia das trocas',T.preview_job,'render',out=str(out)).to_dict()
                elif path=='/fatiador/trocas/revisar':result=M.submit('revisao_trocas','Conferir áudio integral da montagem',T.review_job,'asr',out=str(out),aliases=body.get('aliases','')).to_dict()
                else:raise ValueError('Ação de troca desconhecida.')
                if not read_only:
                    if action=='preferencias-voz' and body.get('salvar') is True:action='preferencias-voz-salvar'
                    if action=='finalizacao-confirmar' and body.get('conferida') is True:action='finalizacao-confirmada'
                    AUTO.resume_on_edit(out, action)
        h.send(200,result)
    except (ValueError,KeyError) as error:h.send(400,{'erro':str(error)})
    # Pedido malformado (tipo errado vindo da tela ou de uma versão antiga): resposta clara, sem texto técnico.
    except (TypeError,AttributeError):h.send(400,{'erro':'Dados inválidos nesta ação. Atualize a página e tente novamente; seus arquivos não foram alterados.'})
    except Exception:h.send(500,{'erro':'Não foi possível concluir esta ação. Confira os arquivos, espaço em disco e tente novamente.'})
    finally:
        if upload_lease is not None:
            with _UPLOAD_GUARD:_UPLOADS.discard(upload_lease)
    return True
