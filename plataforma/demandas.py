"""Demandas de troca com tempos explícitos e nomenclatura VTurb. Sem IA externa."""
import html
import json
import math
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urljoin

import requests
from . import ml_core as M
from .progresso import DownloadProgress, phase

COPY = dict(zip(['C20','C21','C46','C47','C49','C50','C51','C52','C59','C75'],
 ['Luiza Bertini','Rodolfo Paulino','João Melz','Diogo Ramalho','Leonardo Nafal','Júlia Araújo','Everton Rodrigues','Patrick Gomes','Mayken','Leonardo Escobar']))
EDITORES = {f'EV{i}': n for i,n in enumerate(['Rafa Carvalho','Genilson','Matheus Duarte','Rafael Oliveira','Evanize Silva','João','Emerson','Luiz Miguel','Guilherme Morissawa','Maria Gomes','Camila Costa','André Nascimento','Lucas Carvalho','Rodrigo Neves','Gabriel Chaves','Deny Klein','Alex Carvalho'],1)}
TIME = r'\d{1,3}:\d{2}(?::\d{2})?(?:[.,]\d+)?'

def seconds(value):
    if isinstance(value, (int,float)):
        n = float(value)
    else:
        s = str(value).strip().replace(',', '.')
        if not re.fullmatch(TIME, s):
            raise ValueError('Tempo inválido. Use mm:ss ou hh:mm:ss.')
        parts = list(map(float,s.split(':')))
        if any(x >= 60 for x in parts[1:]):
            raise ValueError('Minutos/segundos inválidos no tempo informado.')
        n = sum(x * 60**i for i,x in enumerate(reversed(parts)))
    if not math.isfinite(n) or n < 0:
        raise ValueError('Tempo deve ser finito e positivo.')
    return n

def clock(n):
    n = int(round(n))
    return f'{n//60:02d}:{n%60:02d}'

def parse(text):
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text).replace('**','')
    # Desfaz os links Markdown para não contar duas vezes a mesma URL.
    text = re.sub(r'\[([^\]]*)\]\((https?://[^\s)]+)\)', r'\2', text)
    url = r'https?://[^\s<>)]+'
    base = re.search(r'\bVSL\s*:\s*('+url+')', text, re.I)
    delay = re.search(r'\bDELAY\s*:\s*('+TIME+')', text, re.I)
    pitch = re.search(r'\bPITCH\s*:\s*('+TIME+')', text, re.I)
    title = re.search(r'([^\n]*\bVSL\s*\d+[^\n]*)', text, re.I)
    items = []
    for m in re.finditer(r'(?:^|\n)\s*\d+[.\)]\s*('+url+r')(.*?)(?=\n\s*\d+[.\)]\s*https?://|\Z)', text, re.I|re.S):
        desc = m[2]
        end = re.search(r'(?:até|ate)\s*('+TIME+')', desc, re.I)
        old = re.search(r'termina\s*(?:em)?\s*('+TIME+')', desc, re.I)
        ml = re.search(r'\bML\s*(\d+)\b',desc,re.I)
        items.append({'url':m[1].rstrip('.,;'), 'fim':end[1] if end else '', 'corte_original':old[1] if old else '', 'ml':ml[1] if ml else ''})
    product = re.search(r'(?:^|\n)\s*Produto\s*:\s*([^\n]+)',text,re.I)
    page = re.search(r'Link da p[áa]gina\s*:\s*('+url+')',text,re.I)
    niche = re.search(r'(?:^|\n)\s*Nicho\s*:\s*([^\n]+)',text,re.I)
    deadline = re.search(r'(?:^|\n)\s*Prazo\s*:\s*([^\n]+)',text,re.I)
    # The operation described in the explanation determines direction. The
    # heading may identify the donor rather than the destination VSL.
    inline=list(re.finditer(r'\b(?:pegar|usar|utilizar)\s+(?:essa?\s+|a\s+)?ML\b.{0,100}?(?:até|ate)\s*('+TIME+r')\s*('+url+r').{0,100}?(?:plugar|colocar|inserir|encaixar)\b.{0,80}?\bVSL\b.{0,80}?(?:cortando|cortar|a partir|corte)\s*(?:em|de)?\s*('+TIME+r')\s*('+url+r')',text,re.I|re.S))
    observations=[];explicit_bases=set()
    if inline and not items:
        for m in inline:
            destination=m[4].rstrip('.,;');explicit_bases.add(destination)
            items.append({'url':m[2].rstrip('.,;'),'fim':m[1],'corte_original':m[3],'ml':''})
        if len(explicit_bases)==1:
            base_url=next(iter(explicit_bases))
            observations.append('A VSL de destino e a origem da ML foram identificadas pela explicação, mesmo quando o cabeçalho aponta para a ML.')
        else:base_url=''
    else:
        heading=re.search(r'Link da VSL a ser rippada\s*:\s*('+url+')',text,re.I)
        base_url=base[1] if base else heading[1] if heading else ''
    cuts = {i['corte_original'] for i in items if i['corte_original']}
    cut = next(iter(cuts)) if len(cuts)==1 else ''
    warnings = []
    if not base_url: warnings.append('Informe o link da VSL base.')
    if not cut: warnings.append('Informe o fim da lead original; não foi encontrado um tempo único.')
    if not items: warnings.append('Nenhuma troca reconhecida. Informe a origem da ML, a VSL de destino e os tempos.')
    if any(not i['fim'] for i in items): warnings.append('Há variações sem tempo final da microlead.')
    return {'base_url':base_url, 'corte_original':cut, 'delay':delay[1] if delay else '', 'pitch':pitch[1] if pitch else '', 'ajustar_pitch':True,
            'titulo':product[1].strip() if product else title[1].strip() if title else '', 'variacoes':items, 'avisos':warnings,'observacoes':observations,'produto':product[1].strip() if product else '', 'pagina':page[1].rstrip('.,;') if page else '', 'nicho':niche[1].strip() if niche else '', 'prazo':deadline[1].strip() if deadline else ''}

def name(data):
    def val(k): return re.sub(r'\s+', ' ', str(data.get(k,'')).strip()).upper()
    product = val('produto')
    def num(k):
        s = val(k)
        if not s.isdigit() or int(s)<1: raise ValueError(f'Informe {k} com número maior que zero.')
        return f'{int(s):02d}'
    kind = data.get('tipo','vsl')
    if kind not in ('vsl','ml','mod','mod_ml','upsell','close'): raise ValueError('Tipo de nomenclatura inválido.')
    if kind == 'close':
        original = str(data.get('original','')).strip()
        if not original: raise ValueError('Cole o nome original para novos closes.')
        return original.removesuffix(' - 1/3/6') + ' - 1/3/6'
    if not product: raise ValueError('Informe o produto.')
    copy, editor = val('copy'), val('editor')
    if copy not in COPY or editor not in EDITORES: raise ValueError('Selecione o copywriter e o editor.')
    if kind == 'upsell':
        parts = [product, 'UPSELL '+num('upsell'), 'V'+str(int(num('versao'))), val('alteracao') or 'CONTROLE', copy,editor]
        if val('fluxo'): parts += ['FLUXO '+num('fluxo')]
    else:
        parts = [product+' VSL '+num('vsl')]
        if kind.startswith('mod'): parts += ['MOD']
        else:
            parts += ['LEAD '+num('lead'), 'V'+str(int(num('versao')))]
            if val('alteracao'): parts += [val('alteracao')]
        if kind == 'ml': parts += ['ML'+str(int(num('ml')))]
        parts += [copy,editor]
        if kind == 'mod_ml': parts += ['ML '+str(int(num('ml')))]
    if val('pitch'): parts += ['PITCH '+clock(seconds(data['pitch']))]
    elif kind != 'upsell': raise ValueError('Informe o pitch para gerar a nomenclatura completa.')
    return ' - '.join(parts)

def validate(plan):
    if plan.get('entrega','video') not in ('video','xml','ambos'):raise ValueError('Tipo de entrega inválido.')
    if plan.get('entrega')=='xml' and plan.get('validacao',{}).get('ativo'):raise ValueError('A conferência do vídeo final exige entrega em vídeo ou ambos.')
    check_url(plan.get('base_url',''))
    cut = seconds(plan.get('corte_original',''))
    if cut <= 0: raise ValueError('O corte original precisa ser maior que zero.')
    items = plan.get('variacoes',[])
    if not items: raise ValueError('Adicione ao menos uma microlead.')
    auto = plan.get('validacao',{}).get('ativo',False)
    pitch = seconds(plan['pitch']) if plan.get('pitch') else None
    if plan.get('ajustar_pitch') and not auto and (pitch is None or pitch < cut):
        raise ValueError('Para ajustar o pitch, informe o pitch original após a lead removida.')
    names = []
    for i,item in enumerate(items):
        check_url(item.get('url',''))
        end = seconds(item.get('fim',''))
        if end < .5: raise ValueError('A microlead precisa ter pelo menos 0,5 segundo.')
        meta = dict(plan.get('nomenclatura',{}))
        if meta.get('produto'):
            meta['ml'] = item.get('ml','')
            if auto: meta['pitch'] = '00:00'
            elif plan.get('ajustar_pitch'): meta['pitch'] = clock(pitch-cut+end)
            elif pitch is not None: meta['pitch'] = clock(pitch)
            generated = name(meta)
            names.append(generated.replace('PITCH 00:00','PITCH PENDENTE') if auto else generated)
        else:
            names.append(f"{plan.get('titulo') or 'VSL'} - VAR {i+1:02d}")
    if len(set(names)) != len(names): raise ValueError('As variações têm nomes iguais. Informe um número de ML diferente para cada uma.')
    return names

def check_url(url):
    p = urlparse(url)
    if p.path.lower().endswith('.mpd'):
        raise ValueError('Playlists DASH (.mpd) ainda não são suportadas. Use MP4 ou HLS (.m3u8).')
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:
        raise ValueError('Use um link HTTP/HTTPS válido, sem usuário ou senha na URL.')

def download(job, url, label="Vídeo de origem"):
    check_url(url)
    vid = uuid.uuid4().hex[:10]
    directory = M.vdir(vid)
    directory.mkdir(parents=True)
    dest = directory/'original.mp4'
    p = urlparse(url)
    if p.hostname in ('drive.google.com','www.drive.google.com'):
        match = re.search(r'/d/([\w-]+)',p.path)
        fileid = match[1] if match else parse_qs(p.query).get('id',[''])[0]
        if not fileid: raise ValueError('Não foi possível identificar o arquivo do Drive.')
        url = 'https://drive.google.com/uc?export=download&id='+fileid
    phase(job,'download',label)
    job.step = 'Conectando para baixar '+label
    try:
        if p.path.lower().endswith('.m3u8'):
            download_hls(job,url,dest,label)
            info=M.probe(dest)
            M.write_meta(vid,id=vid,nome=f'Download {vid}',arquivo=dest.name,criado=M.now(),status='importado',probe=info,confirmado={})
            return vid
        with requests.Session() as session:
            response = session.get(url,stream=True,timeout=(20,60))
            # Google Drive pede confirmação para arquivos grandes.
            if 'text/html' in response.headers.get('Content-Type',''):
                page = response.text
                response.close()
                action = re.search(r'<form[^>]+action="([^"]+)"',page)
                fields = dict(re.findall(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"',page))
                if action and 'drive.google.com' in url and urlparse(html.unescape(action[1])).hostname in ('drive.google.com','drive.usercontent.google.com'):
                    response = session.get(html.unescape(action[1]),params=fields,stream=True,timeout=(20,60))
                else:
                    raise ValueError('O link retornou uma página HTML. Compartilhe o arquivo do Drive ou use a URL direta do vídeo/CDN.')
            with response:
                response.raise_for_status()
                if 'text/html' in response.headers.get('Content-Type',''):
                    raise ValueError('Download exige acesso. Libere o arquivo no Drive ou informe o link direto.')
                progress=DownloadProgress(job,label,response.headers)
                with dest.open('wb') as fp:
                    for chunk in response.iter_content(64*1024):
                        if job.cancel: raise M.Cancelled()
                        fp.write(chunk)
                        progress.add(len(chunk))
                progress.update(force=True)
                if job.cancel: raise M.Cancelled()
        phase(job,'analise','Análise do arquivo baixado')
        job.step='Conferindo o download de '+label
        info = M.probe(dest)
        M.write_meta(vid,id=vid,nome=f'Download {vid}',arquivo=dest.name,criado=M.now(),status='importado',probe=info,confirmado={})
        return vid
    except Exception:
        M.shutil.rmtree(directory,ignore_errors=True)
        raise

def check_hls_vod(job,url,depth=0):
    """Reject live streams and DRM before allocating a potentially endless file."""
    if job.cancel:raise M.Cancelled()
    if depth>4:raise ValueError('Playlist HLS com referências excessivas.')
    check_url(url)
    with requests.get(url,stream=True,timeout=(20,30)) as response:
        response.raise_for_status();chunks=[];size=0
        for chunk in response.iter_content(65536):
            if job.cancel:raise M.Cancelled()
            size+=len(chunk)
            if size>2*1024*1024:raise ValueError('Playlist HLS maior que o limite de leitura.')
            chunks.append(chunk)
        text=b''.join(chunks).decode('utf-8-sig',errors='replace');resolved=response.url
    if not text.lstrip().startswith('#EXTM3U'):raise ValueError('O link .m3u8 não retornou uma playlist HLS válida.')
    if re.search(r'#EXT-X-KEY:[^\n]*(?:METHOD=SAMPLE-AES|KEYFORMAT=)',text,re.I):raise ValueError('Esta playlist usa proteção DRM não suportada. Use uma fonte de vídeo acessível.')
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    variants=[lines[i+1] for i,line in enumerate(lines[:-1]) if line.startswith('#EXT-X-STREAM-INF:') and not lines[i+1].startswith('#')]
    if variants:return check_hls_vod(job,urljoin(resolved,variants[0]),depth+1)
    if '#EXT-X-ENDLIST' not in lines:raise ValueError('Este HLS está ao vivo ou não foi finalizado. Use uma playlist de vídeo completo (VOD).')

def download_hls(job,url,dest,label):
    job.step='Conferindo playlist HLS de '+label
    check_hls_vod(job,url)
    progress=DownloadProgress(job,label,{})
    def report(line):
        if line.startswith('total_size='):
            try:received=int(line.split('=',1)[1])
            except ValueError:return
            if received>=progress.received:progress.add(received-progress.received)
    temporary=dest.with_suffix('.partial.mp4')
    cmd=[M.FFMPEG,'-y','-v','error','-nostdin','-progress','pipe:1','-nostats','-protocol_whitelist','http,https,tcp,tls,crypto','-rw_timeout','60000000','-i',url,'-map','0:v:0','-map','0:a:0?','-c','copy','-movflags','+faststart',str(temporary)]
    try:
        M.run_proc(job,cmd,report)
        if job.cancel:raise M.Cancelled()
        temporary.replace(dest);progress.received=dest.stat().st_size;progress.update(force=True)
        phase(job,'analise','Conferência do HLS baixado');job.step='Conferindo o download HLS de '+label
    finally:
        if temporary.exists():temporary.unlink()

def execute(job, plan):
    names = validate(plan)
    cache = {}
    # Cache pela URL original, inclusive quando o Drive muda o endereço de download.
    def get(url,label):
        if url not in cache: cache[url] = download(job,url,label)
        return cache[url]
    base = get(plan['base_url'],'VSL base')
    cut = seconds(plan['corte_original'])
    base_duration = M.read_meta(base)['probe']['duracao']
    if cut >= base_duration-.5: raise ValueError('Corte original está fora da duração da VSL.')
    results = []
    for i,item in enumerate(plan['variacoes']):
        if job.cancel: raise M.Cancelled()
        job.context=f'Variação {i+1} de {len(names)}'
        lead = get(item['url'],f'ML da variação {i+1} de {len(names)}')
        end = seconds(item['fim'])
        if end > M.read_meta(lead)['probe']['duracao']+.03:
            raise ValueError(f'Variação {i+1}: o fim da ML ultrapassa a duração do vídeo.')
        spec = {'lead':{'video':lead,'inicio':0,'fim':end},'body':{'video':base,'inicio':cut},
                'opcoes':{'modo':'exato','nome':re.sub(r'[/\\:\x00-\x1f]','-',names[i]),'fade_ms':0,'entrega':plan.get('entrega','video')}}
        job.step = f'Montando variação {i+1}/{len(names)}'
        result = M.render_job(job,spec)
        entry = result | {'nomenclatura': names[i]}
        if plan.get('validacao', {}).get('ativo') and result.get('arquivo'):
            from . import validacao as V
            # Salva a saída na resposta antes de transcrever: falha na auditoria não oculta o vídeo.
            entry['status_validacao'] = 'em_andamento'
            job.result = {'versoes': results + [entry]}
            try:
                audit = V.audit_path(job, M.OUT_DIR/result['arquivo'], plan['validacao'])
                entry['validacao'] = audit
                entry['status_validacao'] = 'concluida'
                if audit['pitch']:
                    detected = clock(audit['pitch']['tempo'])
                    entry['pitch_detectado'] = detected
                    if 'PITCH PENDENTE' in names[i]:
                        final_name = names[i].replace('PITCH PENDENTE', 'PITCH '+detected)
                        old = M.OUT_DIR/result['arquivo']
                        new = M.OUT_DIR/(re.sub(r'[/\\:\x00-\x1f]', '-', final_name)+'_'+job.id+old.suffix)
                        # O relatório/XML referenciam a fonte; regenera após renomear.
                        old.rename(new)
                        audit = V.export(audit, new, M.probe(new), Path(audit['exports']['json']).stem.removeprefix('validacao_'))
                        entry.update(arquivo=new.name, nomenclatura=final_name, validacao=audit)
                else:
                    entry['aviso_pitch'] = 'Pitch pendente: confira os candidatos e o áudio antes de nomear.'
                entry['validacao'] = V.public(entry['validacao'])
            except M.Cancelled:
                raise
            except Exception as error:
                entry.update(status_validacao='erro', erro_validacao=str(error))
        results.append(entry)
        job.result = {'versoes':results}
    manifest = M.OUT_DIR/f'demanda_{job.id}.json'
    manifest.write_text(json.dumps({'plano':plan,'versoes':results},ensure_ascii=False,indent=2))
    job.step = 'Todas as variações concluídas'
    return {'versoes':results,'manifesto':manifest.name}

def submit(plan):
    validate(plan)
    return M.submit('demanda','Troca de microleads por demanda',execute,'render',plan=plan)
