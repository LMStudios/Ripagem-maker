"""Limpeza conservadora: caches recriáveis e cópias APFS, sem apagar mídias."""
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
import unicodedata
from collections import defaultdict
from pathlib import Path
from . import armazenamento as S,ml_core as M

HOME=S.PROJECT/'plataforma/workspace/limpeza'
LOCK=threading.RLock()
MEDIA={'.mp4','.mov','.m4v','.mkv','.webm','.mp3','.wav','.m4a','.zip'}
def read(path,default):
    try:return json.loads(path.read_text())
    except (FileNotFoundError,ValueError):return default

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)
def stamp(p):
    s=p.stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns]
def check(job):
    if job.cancel:raise M.Cancelled()
def digest(job,p):
    before=stamp(p);h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(8*1024**2):check(job);h.update(b)
    if stamp(p)!=before:raise ValueError('Um arquivo mudou durante a análise. Analise novamente.')
    return h.hexdigest()
def roots():return list(dict.fromkeys(p for kind in ('fatiador','montagens','videos') for p in S.roots(kind) if p.is_dir()))
def free_space():
    volumes={}
    for p in roots()+[S.PROJECT]:
        if p.exists():volumes[p.stat().st_dev]=shutil.disk_usage(p).free
    return sum(volumes.values())

def allowed(p):return not p.is_symlink() and any(p.resolve().is_relative_to(r.resolve()) for r in roots())
def cache_files():
    result=[]
    for folder in [S.PROJECT/'__pycache__',S.PROJECT/'plataforma/__pycache__',S.PROJECT/'tests/__pycache__']:
        if folder.is_dir() and not folder.is_symlink():result.extend(p for p in folder.glob('*.pyc') if p.is_file() and not p.is_symlink())
    build=S.PROJECT/'mac_app/.build'
    if build.is_dir() and not build.is_symlink():
        for p in build.rglob('*'):
            rel=p.relative_to(build)
            if p.is_file() and not p.is_symlink() and (str(rel) in {'DRStudio','AppIcon.icns','icon_1024.png'} or (rel.parent==Path('AppIcon.iconset') and rel.name.startswith('icon_') and p.suffix=='.png')):result.append(p)
    return result

def active(job=None,legacy=()):
    return any(j.id!=getattr(job,'id',None) and j.status in ('na_fila','executando') for j in M.JOBS.values()) or any(j.get('status')=='running' for j in legacy)
def maintenance(job,fn,legacy):
    with S.LOCK:
        if S.MAINTENANCE or active(job,legacy()):raise ValueError('Aguarde os trabalhos em andamento antes da limpeza.')
        S.MAINTENANCE=True
    try:
        with LOCK:return fn()
    finally:
        with S.LOCK:S.MAINTENANCE=False

def legacy_optimized():
    # Registro da primeira limpeza feita neste projeto, sem assumir só pelo nome.
    report=read(S.PROJECT/'limpeza_relatorio_20261025.json',{})
    hashes={r['path']:r['hash'] for group in report.get('groups',[]) for r in group}
    return {(r['path'],r['canonical']):hashes.get(r['path']) for r in report.get('consolidated',[])}

def analyze(job):
    catalog=read(HOME/'catalogo.json',{'hashes':{},'clones':[]});hashes=catalog['hashes'];files={};seen=set()
    job.step='Listando mídias e caches do aplicativo';job.progress={'indeterminado':True,'tipo':'limpeza','fase':'Listando arquivos'}
    for root in roots():
        for parent,dirs,names in os.walk(root,followlinks=False):
            check(job);dirs[:]=[d for d in dirs if not (Path(parent)/d).is_symlink()]
            for name in names:
                p=Path(parent)/name
                if p.is_symlink() or p.suffix.lower() not in MEDIA or not p.is_file():continue
                st=stamp(p)
                if tuple(st[:2]) in seen or st[2]<10*1024**2:continue
                seen.add(tuple(st[:2]));files[str(p)]=st
    sizes=defaultdict(list)
    for path,st in files.items():sizes[(st[0],st[2])].append(path)
    candidates=[p for group in sizes.values() if len(group)>1 for p in group];by_hash=defaultdict(list)
    for i,path in enumerate(candidates):
        check(job);job.step=f'Comparando conteúdo · {i+1} de {len(candidates)} arquivos';job.pct=i/max(1,len(candidates));job.progress={'tipo':'limpeza','fase':'Comparando arquivos','processadas':i,'total':len(candidates),'indeterminado':False}
        key=json.dumps(files[path]);h=hashes.get(key)
        if not h:h=digest(job,Path(path));hashes[key]=h
        if stamp(Path(path))!=files[path]:raise ValueError('Arquivo alterado. Analise novamente.')
        by_hash[(files[path][0],files[path][2],h)].append(path)
    planned=[];optimized=0;old=legacy_optimized();clones=catalog.get('clones',[])
    for (_,size,h),group in by_hash.items():
        if len(group)<2:continue
        known=[r for r in clones if r['hash']==h and r['path'] in group and r['canonical'] in group and r['stamp']==files[r['path']] and r['canonical_stamp']==files[r['canonical']]]
        names={unicodedata.normalize('NFC',p):p for p in group};legacy=[(names[unicodedata.normalize('NFC',p)],names[unicodedata.normalize('NFC',c)]) for (p,c),value in old.items() if value==h and unicodedata.normalize('NFC',p) in names and unicodedata.normalize('NFC',c) in names]
        # Um conjunto pode ter múltiplas origens registradas; mantém seus caminhos.
        canonical=next((r['canonical'] for r in known),next((c for p,c in legacy),group[0]))
        for target in group:
            if target==canonical:continue
            prior=next((r for r in known if r['path']==target),None)
            was_legacy=any(p==target for p,c in legacy)
            if prior or was_legacy:
                optimized+=size
                if not prior:clones.append({'path':target,'canonical':canonical,'stamp':files[target],'canonical_stamp':files[canonical],'hash':h})
                continue
            planned.append({'path':target,'canonical':canonical,'stamp':files[target],'canonical_stamp':files[canonical],'hash':h,'bytes':size})
    caches=[{'path':str(p),'stamp':stamp(p),'bytes':p.stat().st_size} for p in cache_files()]
    token=uuid.uuid4().hex;plan={'token':token,'created':time.time(),'duplicates':planned,'caches':caches}
    write(HOME/'catalogo.json',{'hashes':hashes,'clones':clones});write(HOME/'plano.json',plan)
    result={'token':token,'created':plan['created'],'duplicados':len(planned),'duplicacao_bytes':sum(r['bytes'] for r in planned),'caches':len(caches),'cache_bytes':sum(r['bytes'] for r in caches),'ja_otimizado_bytes':optimized,'livre_bytes':free_space(),'exemplos':[str(Path(r['path']).relative_to(S.PROJECT)) if Path(r['path']).is_relative_to(S.PROJECT) else str(Path(r['path'])) for r in planned[:8]]}
    write(HOME/'analise.json',result);job.step='Análise concluída — confira antes de limpar';job.pct=1;return result

def execute(job,token):
    plan=read(HOME/'plano.json',{})
    if not token or plan.get('token')!=token or time.time()-plan.get('created',0)>86400:raise ValueError('Faça uma nova análise antes de limpar.')
    catalog=read(HOME/'catalogo.json',{'hashes':{},'clones':[]});before=free_space();done=[];warnings=[];removed=0;potential=0
    total=len(plan['duplicates'])+len(plan['caches']);processed=0
    try:
        for row in plan['duplicates']:
            check(job);target=Path(row['path']);canonical=Path(row['canonical']);processed+=1
            job.step=f'Consolidando cópias · {processed} de {total}';job.pct=processed/max(1,total)
            if not allowed(target) or not allowed(canonical) or stamp(target)!=row['stamp'] or stamp(canonical)!=row['canonical_stamp']:raise ValueError('Arquivos mudaram desde a análise. Analise novamente antes de continuar.')
            tmp=target.with_name('.ripagem-clone-'+uuid.uuid4().hex);st=target.stat()
            try:
                p=subprocess.run(['/bin/cp','-c','-p',str(canonical),str(tmp)],capture_output=True)
                if p.returncode:warnings.append('O volume não permitiu otimizar esta cópia; original preservado: '+target.name);continue
                os.utime(tmp,ns=(st.st_atime_ns,st.st_mtime_ns))
                if digest(job,tmp)!=row['hash'] or stamp(target)!=row['stamp'] or stamp(canonical)!=row['canonical_stamp']:raise ValueError('Arquivo mudou durante a limpeza; a cópia original foi mantida.')
                check(job);os.replace(tmp,target);potential+=row['bytes'];done.append(str(target))
                catalog['clones']=[r for r in catalog['clones'] if r['path']!=str(target)]+[{'path':str(target),'canonical':str(canonical),'stamp':stamp(target),'canonical_stamp':stamp(canonical),'hash':row['hash']}]
                catalog['hashes'][json.dumps(stamp(target))]=row['hash'];write(HOME/'catalogo.json',catalog)
            finally:
                if tmp.exists():tmp.unlink()
        allowed_caches={str(p) for p in cache_files()}
        for row in plan['caches']:
            check(job);p=Path(row['path']);processed+=1;job.step=f'Removendo caches recriáveis · {processed} de {total}';job.pct=processed/max(1,total)
            if str(p) not in allowed_caches or not p.is_file() or p.is_symlink() or stamp(p)!=row['stamp']:continue
            p.unlink();removed+=1;potential+=row['bytes']
        job.step='Conferindo o espaço recuperado';job.progress={'tipo':'limpeza','fase':'Conferindo espaço','indeterminado':True}
        # APFS pode atualizar o espaço disponível alguns segundos após as trocas.
        for _ in range(12):
            check(job)
            if free_space()-before>=potential*.95:break
            time.sleep(.5)
        job.step='Limpeza segura concluída';job.pct=1
        return {'consolidados':len(done),'caches_removidos':removed,'liberado_bytes':min(potential,max(0,free_space()-before)),'livre_bytes':free_space(),'avisos':warnings,'preservado':'Originais, transcrições, áudios, XMLs e caminhos das mídias preservados.'}
    finally:
        write(HOME/'ultima.json',{'when':time.time(),'consolidados':len(done),'caches_removidos':removed,'liberado_bytes':min(potential,max(0,free_space()-before)),'livre_bytes':free_space(),'avisos':warnings})
        # Evita executar novamente um plano com metadados anteriores à limpeza.
        if (HOME/'plano.json').exists():(HOME/'plano.json').unlink()

def status():return {'ultima':read(HOME/'ultima.json',None),'analise':read(HOME/'analise.json',None),'livre_bytes':free_space(),'em_andamento':S.MAINTENANCE}


# ====================================================================== armazenamento e limpeza por categoria
# Tudo vai para a Lixeira (recuperável). Nada é removido só por ser antigo: favoritos, projetos ativos,
# em processamento e arquivos citados por um projeto ou XML exportado ficam protegidos.
CATEGORIES={'projetos':'Projetos','resultados':'Resultados (XML, montagens e vídeos legendados)','previas':'Prévias','temporarios':'Temporários','caches':'Caches','recuperacao':'Pasta de recuperação do app'}
ACTIVE_HOURS=24

def _nfc(p):
    from .projetos import key
    return key(Path(p).resolve())

def _size(p):
    try:return 0 if p.is_symlink() else p.stat().st_size
    except OSError:return 0

def _tree(p):
    p=Path(p)
    if p.is_file():return _size(p)
    total=0
    for parent,dirs,names in os.walk(p,followlinks=False):
        for n in names:total+=_size(Path(parent)/n)
    return total

def _temporary(p):
    n=p.name
    return n.endswith(('.tmp','.parcial.wav','.parcial.mp4','.parcial.m4a')) or n.startswith('.ripagem-clone-') or '.parcial.' in n

def _project_items(out):
    """Classifica os itens de um projeto: prévias e temporários soltos; o resto é o projeto."""
    out=Path(out);previews=[];temps=[]
    trocas=out/'trocas'
    if trocas.is_dir():
        for d in trocas.iterdir():
            if d.is_dir() and d.name.startswith('previa_'):previews.append(d)
            elif d.is_dir() and d.name.startswith('mix-'):temps.append(d)
        legend=trocas/'legendas'
        if legend.is_dir():previews+= [f for f in legend.rglob('previa_*.mp4') if f.is_file()]
    for parent,dirs,names in os.walk(out,followlinks=False):
        for n in names:
            f=Path(parent)/n
            if _temporary(f):temps.append(f)
    return previews,temps

def _protected(row):
    if row['favorito']:return 'Favorito'
    if row['em_uso']:return 'Em processamento'
    opened=row.get('aberto_em') or 0
    if time.time()-opened<ACTIVE_HOURS*3600:return 'Aberto nas últimas 24 h'
    return ''

def _projects(with_size=True):
    from . import projetos as P
    rows=[]
    for out in P.all_projects():
        row=P.summary(out,with_size);row['aberto_em']=P.read_meta(out).get('aberto_em',0);row['protecao']=_protected(row);rows.append(row)
    return rows

def usage(job):
    """Quanto cada categoria ocupa. Só lê: não altera nada."""
    from . import projetos as P
    job.step='Medindo projetos';job.progress={'tipo':'limpeza','fase':'Medindo projetos','indeterminado':True}
    totals={k:0 for k in CATEGORIES};projects=_projects(True)
    for row in projects:
        check(job);previews,temps=_project_items(row['caminho'])
        p_bytes=sum(_tree(p) for p in previews);t_bytes=sum(_tree(p) for p in temps)
        totals['previas']+=p_bytes;totals['temporarios']+=t_bytes
        xml=sum(_size(x) for x in Path(row['caminho']).rglob('*.xml'))
        totals['resultados']+=xml;totals['projetos']+=max(0,row['bytes']-p_bytes-t_bytes-xml)
        zip_file=Path(row['caminho']).with_suffix('.zip')
        if zip_file.is_file():totals['resultados']+=_size(zip_file)
    job.step='Medindo resultados e temporários'
    for root in S.roots('montagens')+S.roots('ferramentas'):
        if root.is_dir():
            for f in root.rglob('*'):
                if f.is_file() and not f.is_symlink():totals['previas' if f.name.startswith('previa_') else 'resultados']+=_size(f)
    for folder in _loose_temp_folders():totals['temporarios']+=_tree(folder)
    totals['caches']=sum(_size(p) for p in cache_files())
    for folder in _recovery_folders():totals['recuperacao']+=_tree(folder)
    result={'categorias':[{'id':k,'nome':v,'bytes':totals[k]} for k,v in CATEGORIES.items()],'projetos':sorted(projects,key=lambda r:-r['bytes']),'livre_bytes':free_space(),'medido_em':time.time()}
    write(HOME/'uso.json',result);job.step='Medição concluída';job.pct=1;return result

def _loose_temp_folders():
    folders=[S.PROJECT/'.uploads',M.WS/'.upload']
    return [f for f in folders if f.is_dir() and not f.is_symlink()]

def _recovery_folders():
    seen=[]
    for root in roots()+S.roots('fatiador'):
        f=root/'.Recuperar Ripagem Maker'
        if f.is_dir() and f not in seen:seen.append(f)
    return seen

def _loose_temp_files(min_age_s=6*3600):
    """Uploads e temporários soltos com mais de algumas horas (os recentes podem pertencer a uma tarefa em curso)."""
    now=time.time();files=[]
    for folder in _loose_temp_folders():
        for f in folder.iterdir():
            try:
                if not f.is_symlink() and now-f.stat().st_mtime>min_age_s:files.append(f)
            except OSError:pass
    return files

def build_plan(job,body):
    """Monta a lista do que pode ir para a Lixeira, com o espaço estimado e o motivo de cada proteção."""
    from . import projetos as P
    body=body or {};wanted=set(body.get('categorias') or []);chosen=set(body.get('projetos') or [])
    if not wanted<={'previas','temporarios','caches','projetos_antigos'}:raise ValueError('Categoria de limpeza inválida.')
    days=body.get('dias',90)
    if isinstance(days,bool) or not isinstance(days,int) or not 1<=days<=3650:raise ValueError('Use um período entre 1 e 3650 dias.')
    job.step='Conferindo referências dos projetos e XMLs';job.progress={'tipo':'limpeza','fase':'Conferindo referências','indeterminado':True}
    used=P.all_references();items=[];protected=[]
    def add(path,category,reason=''):
        path=Path(path)
        if not path.exists() or path.is_symlink():return
        key=_nfc(path)
        hit=next((u for u in used if u==key or u.startswith(key+os.sep)),None) if path.is_dir() else (key if key in used else None)
        if hit:protected.append({'caminho':str(path),'categoria':category,'motivo':'Usado por um projeto ou XML exportado'});return
        st=path.stat();items.append({'caminho':str(path),'categoria':category,'bytes':_tree(path),'mtime_ns':st.st_mtime_ns,'motivo':reason})
    projects=_projects(False)
    for row in projects:
        check(job);previews,temps=_project_items(row['caminho'])
        busy=row['em_uso']
        if 'previas' in wanted:
            for p in previews:
                if busy:protected.append({'caminho':str(p),'categoria':'previas','motivo':'Projeto em processamento'})
                else:add(p,'previas','Prévia antiga, não usada pela prévia atual')
        if 'temporarios' in wanted and not busy:
            for p in temps:add(p,'temporarios','Sobra de uma tarefa interrompida')
    if 'temporarios' in wanted:
        for f in _loose_temp_files():add(f,'temporarios','Upload temporário antigo')
    if 'caches' in wanted:
        for f in cache_files():add(f,'caches','Cache recriável')
    old=[]
    if 'projetos_antigos' in wanted:
        limit=time.time()-days*86400
        for row in projects:
            if row['atualizado']>=limit:continue
            info={'pasta':row['pasta'],'nome':row['nome'],'produto':row['produto'],'atualizado':row['atualizado'],'etapa':row['etapa'],'bytes':_tree(row['caminho']),'protecao':row['protecao']}
            external=[x for x in _xml_users_outside(row['caminho'],projects)]
            if external:info['protecao']='Citado em XML de outro projeto ou das Montagens'
            old.append(info)
            if row['pasta'] in chosen and not info['protecao']:
                st=Path(row['caminho']).stat();items.append({'caminho':row['caminho'],'categoria':'projetos_antigos','bytes':info['bytes'],'mtime_ns':st.st_mtime_ns,'motivo':'Projeto sem uso há mais de '+str(days)+' dias'})
                z=Path(row['caminho']).with_suffix('.zip')
                if z.is_file():items.append({'caminho':str(z),'categoria':'projetos_antigos','bytes':_size(z),'mtime_ns':z.stat().st_mtime_ns,'motivo':'Pacote ZIP do projeto'})
            elif row['pasta'] in chosen:protected.append({'caminho':row['caminho'],'categoria':'projetos_antigos','motivo':info['protecao']})
    token=uuid.uuid4().hex;plan={'token':token,'created':time.time(),'items':items}
    write(HOME/'plano_categorias.json',plan)
    job.step='Confira a lista antes de limpar';job.pct=1
    return {'token':token,'itens':items,'protegidos':protected[:200],'projetos_antigos':sorted(old,key=lambda r:r['atualizado']),'estimado_bytes':sum(i['bytes'] for i in items),'livre_bytes':free_space()}

def _xml_users_outside(folder,projects):
    from . import projetos as P
    key=_nfc(folder);hits=[]
    for row in projects:
        if row['caminho']==folder:continue
        for xml in Path(row['caminho']).rglob('*.xml'):
            if any(p.startswith(key+os.sep) for p in P.xml_paths(xml)):hits.append(str(xml))
    for root in S.roots('montagens'):
        if root.is_dir():
            for xml in root.glob('*.xml'):
                if any(p.startswith(key+os.sep) for p in P.xml_paths(xml)):hits.append(str(xml))
    return hits

def run_plan(job,token,selected):
    """Manda para a Lixeira somente os itens marcados, se nada mudou desde a conferência."""
    from . import lixeira,projetos as P
    plan=read(HOME/'plano_categorias.json',{})
    if not token or plan.get('token')!=token or time.time()-plan.get('created',0)>3600:raise ValueError('A lista expirou. Confira novamente antes de limpar.')
    chosen=set(selected or [])
    rows=[i for i in plan['items'] if i['caminho'] in chosen]
    if not rows:raise ValueError('Marque pelo menos um item para limpar.')
    used=P.all_references();active=P.active_folders();done=[];skipped=[];freed=0
    for n,row in enumerate(rows):
        check(job);path=Path(row['caminho']);job.step=f'Enviando para a Lixeira · {n+1} de {len(rows)}';job.pct=n/len(rows)
        job.progress={'tipo':'limpeza','fase':'Enviando para a Lixeira','processadas':n,'total':len(rows),'indeterminado':False}
        key=_nfc(path)
        if not path.exists():skipped.append({'caminho':str(path),'motivo':'Já não existe'});continue
        if path.stat().st_mtime_ns!=row['mtime_ns']:skipped.append({'caminho':str(path),'motivo':'Mudou desde a conferência'});continue
        if key in used or any(a==key or a.startswith(key+os.sep) for a in active):skipped.append({'caminho':str(path),'motivo':'Passou a ser usado por um projeto'});continue
        if row['categoria']!='projetos_antigos' and path.is_dir() and any(u.startswith(key+os.sep) for u in used):skipped.append({'caminho':str(path),'motivo':'Contém arquivo usado por um projeto'});continue
        result=lixeira.to_trash(path);done.append(row|result);freed+=row['bytes']
    report={'quando':time.time(),'removidos':done,'ignorados':skipped,'liberado_bytes':freed,'automatica':False}
    _save_report(report);(HOME/'plano_categorias.json').unlink(missing_ok=True)
    job.step='Limpeza concluída';job.pct=1;return report

def _save_report(report):
    folder=HOME/'relatorios';folder.mkdir(parents=True,exist_ok=True)
    write(folder/(time.strftime('%Y%m%d_%H%M%S')+('_auto' if report.get('automatica') else '')+'.json'),report)
    write(HOME/'ultimo_relatorio.json',report)

def auto_cleanup(job=None):
    """Limpeza automática (desligada por padrão): só temporários, caches e, se escolhido, projetos antigos sem proteção."""
    from . import lixeira,projetos as P
    cfg=S.cleanup_settings()
    if not cfg['ativa']:return None
    last=read(HOME/'auto_ultima.json',{})
    if time.time()-last.get('quando',0)<20*3600:return None
    with S.LOCK:
        if S.MAINTENANCE or active():return None
        S.MAINTENANCE=True
    try:return _auto(cfg)
    finally:
        with S.LOCK:S.MAINTENANCE=False

def _auto(cfg):
    from . import lixeira,projetos as P
    used=P.all_references();done=[];freed=0
    candidates=[]
    if cfg['temporarios']:
        candidates+=[('temporarios',f) for f in _loose_temp_files(24*3600)]
        for row in _projects(False):
            if not row['em_uso']:candidates+=[('temporarios',p) for p in _project_items(row['caminho'])[1]]
    if cfg['caches']:candidates+=[('caches',f) for f in cache_files()]
    if cfg['projetos_antigos']:
        limit=time.time()-cfg['dias']*86400;projects=_projects(False)
        for row in projects:
            if row['atualizado']<limit and not row['protecao'] and not _xml_users_outside(row['caminho'],projects):candidates.append(('projetos_antigos',Path(row['caminho'])))
    for category,path in candidates:
        key=_nfc(path)
        if category!='projetos_antigos' and (key in used or any(u.startswith(key+os.sep) for u in used)):continue
        size=_tree(path);result=lixeira.to_trash(path);done.append({'caminho':str(path),'categoria':category,'bytes':size}|result);freed+=size
    report={'quando':time.time(),'removidos':done,'ignorados':[],'liberado_bytes':freed,'automatica':True,'regras':cfg}
    write(HOME/'auto_ultima.json',{'quando':report['quando']})
    if done:_save_report(report)
    return report

def storage_status():
    return {'uso':read(HOME/'uso.json',None),'ultimo_relatorio':read(HOME/'ultimo_relatorio.json',None),'regras':S.cleanup_settings(),'livre_bytes':free_space(),'em_andamento':S.MAINTENANCE}
