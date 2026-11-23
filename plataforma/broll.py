"""Buscador de b-roll por frase, com filtro de texto e marca d'água, para a trilha V3 do XML.

Fluxo: a transcrição vira frases; para cada frase o app sugere uma busca (editável), procura
vídeos curtos no YouTube com o yt-dlp (gratuito, sem chave), baixa só um trecho de poucos
segundos, converte para H.264 sem áudio e confere o quadro neste computador:
- texto na tela (OCR em alguns quadros);
- marca d'água de banco pago (mediana dos quadros + passa-alta + OCR: a marca é estática);
- canal ou título de revendedor de banco pago (descartado antes de baixar).
Os candidatos são só sugestões. Nada vai para o XML sem o editor escolher o clipe da frase.
"""
import json
import re
import subprocess
import time
from pathlib import Path

from . import ml_core as M, trocas as T

VERSION = 'broll-1'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
SUFFIX = 'stock footage'
CLIP_S = 10.0          # segundos baixados de cada candidato
MAX_SOURCE_S = 180     # vídeos mais longos costumam ser aula, podcast ou entrevista
SEARCH_N = 20
# Bancos pagos revendidos no YouTube trazem marca d'água; o canal inteiro cai (ver memória da L117).
RESELLERS = ('videohive', 'envato', 'pond5', 'shutterstock', 'motion array', 'motionarray', 'storyblocks', '123rf',
             'istock', 'getty', 'adobe stock', 'dreamstime', 'depositphotos', 'artgrid', 'cinemastock', 'bannerdrones',
             'dollarstock', 'james gower', 'videoblocks', 'alamy', 'filmsupply', 'framepool', 'stock kit')
NOT_BROLL = ('podcast', 'interview', 'explained', 'how to', 'tutorial', 'official video', 'lyrics', 'reaction', 'review',
             'webinar', 'lecture', 'live stream', 'full movie', 'episode')
STOP = set('''a an the and or but if then than so of to in on at by for with from into onto over under about as is are was were be
been being am do does did done have has had having i me my mine we us our you your he him his she her it its they them their this
that these those there here what which who whom whose when where why how all any both each few more most other some such no nor not
only own same too very can could will would shall should may might must just also even ever still yet again once now today really
because while until after before during through up down out off above below between why let lets get got gets going go goes went
make made makes say said says tell told know knew think thought want wanted like one two three first last new old every thing
things something anything nothing way ways time times day days year years lot lots much many well back right left yes yeah okay
de da do das dos e o a os as um uma que em no na nos nas por para com se é foi ser ter isso essa esse esta este eu você ele ela
eles elas nós mas mais muito também já não sim como quando onde porque pra pro
myself yourself himself herself itself ourselves themselves someone anyone everyone nobody somebody anybody everything
look looks looked looking see saw seen sees seeing feel felt feels feeling try tried tries trying save saved need needed
come came comes coming take took taken takes give gave given gives find found finds put keep kept start started began begin
call called seem seemed turn turned become became show showed leave left mean meant hear heard ask asked asking help helped
work worked use used using wish wished happen happened happening happens tell telling talk talked wait waited ready best better
good great bad big small little long short high low next whole real true sure able enough almost always never often sometimes
maybe perhaps already soon later finally simply exactly actually literally truly certainly probably mean god dear oh hey
course without within against among along around across behind beyond toward towards upon whether though although however'''.split())


def folder(out): return Path(out) / 'broll'


def state_path(out): return folder(out) / 'estado.json'


def load(out):
    try:
        return json.loads(state_path(out).read_text())
    except (OSError, ValueError):
        return {'versao': VERSION, 'buscas': {}, 'candidatos': {}, 'escolhas': {}}


def save(out, state):
    state['versao'] = VERSION
    T.write(state_path(out), state)


def _sentences(out):
    from . import visuais as VIS
    raw = json.loads((Path(out) / 'transcricao_bruta.json').read_text())
    rows = []
    for words in VIS.sentences(raw.get('words', [])):
        text = ' '.join(w['text'] for w in words).strip()
        start, end = int(words[0]['start']), int(words[-1]['end'])
        if text and end > start:
            rows.append({'id': str(start), 'inicio_ms': start, 'fim_ms': end, 'texto': text, 'speaker': words[0].get('speaker', '')})
    return rows


def _product_words(out):
    try:
        plan = T.load(out)
    except (OSError, ValueError):
        return set()
    names = ' '.join(str(plan.get(k) or '') for k in ('produto', 'produto_novo', 'produto_aliases'))
    return {w for w in re.findall(r'[a-zà-ú]+', names.lower()) if len(w) > 2}


def suggest_query(text, banned=()):
    """Busca inicial a partir da frase: palavras de conteúdo na ordem da fala (o editor ajusta)."""
    words = [w for w in re.findall(r"[A-Za-zÀ-ú][A-Za-zÀ-ú'’-]+", text)
             if "'" not in w and '’' not in w and w.lower() not in STOP and w.lower() not in banned and len(w) > 2
             and not (w[0].isupper() and text.find(w) > 0)]  # nomes próprios no meio da frase não viram imagem
    ranked = sorted(dict.fromkeys(w.lower() for w in words), key=lambda w: -len(w))[:4]
    ordered = [w for w in dict.fromkeys(x.lower() for x in words) if w in ranked]
    return ' '.join(ordered)


def _gaps(out):
    try:
        from . import visuais as VIS
        return [(g['inicio_ms'], g['fim_ms']) for g in VIS.gap_report(out).get('frestas', [])]
    except Exception:
        return []


LIBRARY_ROW = 'biblioteca'


def _eligible_rows(out, library=False):
    if library:
        return [{'id': LIBRARY_ROW, 'inicio_ms': 0, 'fim_ms': 0, 'texto': '', 'speaker': ''}], None
    from .visuais import first_product_mention
    first = first_product_mention(out)
    rows = [] if first is None else [
        row | {'inicio_ms': max(first, row['inicio_ms'])}
        for row in _sentences(out) if row['fim_ms'] > first
    ]
    return rows, first


def require_row(out, frase, library=False):
    rows, _ = _eligible_rows(out, library)
    for row in rows:
        if row['id'] == frase:
            return row
    raise ValueError('A frase está fora da seção do produto. Atualize a lista.')


def view(out, library=False):
    """Frases com a busca sugerida, os candidatos já encontrados e a escolha de cada uma."""
    state = load(out)
    banned = set() if library else _product_words(out)
    gaps = [] if library else _gaps(out)
    eligible, first = _eligible_rows(out, library)
    rows = []
    for row in eligible:
        search = state['buscas'].get(row['id'], {})
        cands = [dict(state['candidatos'][c], id=c) for c in search.get('candidatos', []) if c in state['candidatos']]
        for c in cands:
            c['existe'] = (Path(out) / c['arquivo']).is_file()
        choice = state['escolhas'].get(row['id'])
        if choice and choice['inicio_ms'] < row['inicio_ms']:
            choice = None
        rows.append(row | {
            'busca': search.get('consulta') or suggest_query(row['texto'], banned),
            'buscada': bool(search),
            'candidatos': cands,
            'escolha': choice,
            'fresta': any(a < row['fim_ms'] and row['inicio_ms'] < b for a, b in gaps),
        })
    chosen = [] if library else approved(out, eligible)
    return {'frases': rows, 'escolhidos': len(chosen), 'segundos': round(sum(r['fim_ms'] - r['inicio_ms'] for r in chosen) / 1000, 1),
            'pasta': 'broll', 'motor': _engine(), 'primeira_mencao_ms': first}


def _engine():
    try:
        import yt_dlp  # noqa: F401
        return {'ok': True}
    except ImportError:
        return {'ok': False, 'erro': 'Falta o componente de busca (yt-dlp). Atualize o Ripagem Maker pelo instalador completo.'}


def _reseller(entry):
    text = ' '.join(str(entry.get(k) or '') for k in ('channel', 'uploader', 'title')).lower()
    return any(r in text for r in RESELLERS)


def _not_broll(entry):
    title = str(entry.get('title') or '').lower()
    return any(r in title for r in NOT_BROLL)


def search(query, n=SEARCH_N):
    import yt_dlp
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'extract_flat': True, 'noprogress': True, **_js()}) as y:
        result = y.extract_info(f'ytsearch{n}:{query}', download=False)
    return [e for e in result.get('entries') or [] if e and e.get('id')]


def pick(entries, seen, limit, blocked_channels=()):
    """Vídeos curtos, sem revendedor de banco pago, sem repetir id nem canal bloqueado."""
    keep, skipped = [], {'revendedor': 0, 'longo': 0, 'repetido': 0, 'fora_do_tema': 0}
    for e in entries:
        duration = e.get('duration') or 0
        if e['id'] in seen:
            skipped['repetido'] += 1
        elif _reseller(e) or (e.get('channel_id') and e['channel_id'] in blocked_channels):
            skipped['revendedor'] += 1
        elif not 3 <= duration <= MAX_SOURCE_S:
            skipped['longo'] += 1
        elif _not_broll(e):
            skipped['fora_do_tema'] += 1
        else:
            keep.append(e)
        if len(keep) >= limit:
            break
    return keep, skipped


def _download(entry, target):
    """Baixa só um trecho e entrega H.264 sem áudio (o Premiere abre sem plugin)."""
    import yt_dlp
    from yt_dlp.utils import download_range_func
    duration = float(entry.get('duration') or CLIP_S)
    length = min(CLIP_S, duration)
    start = 0.0 if duration <= CLIP_S + 2 else min(duration * .2, duration - length - 1)
    raw = target.with_name(target.stem + '-bruto')
    opts = {'quiet': True, 'no_warnings': True, 'noprogress': True, 'outtmpl': str(raw) + '.%(ext)s',
            'format': 'bv*[height<=1080][vcodec^=avc1]/bv*[height<=1080]/b[height<=1080]/b',
            'download_ranges': download_range_func(None, [(start, start + length)]), 'sleep_interval_requests': 1,
            'ffmpeg_location': str(Path(M.FFMPEG).parent) if Path(M.FFMPEG).is_absolute() else None, **_js()}
    link = entry.get('url') or 'https://www.youtube.com/watch?v=' + entry['id']
    seek = 0.0
    try:
        with yt_dlp.YoutubeDL({k: v for k, v in opts.items() if v is not None}) as y:
            y.download([link])
    except Exception:
        # Alguns sites (Pinterest, HLS) não aceitam baixar só o trecho: baixa o vídeo e corta aqui.
        if duration > 300:
            raise
        for f in target.parent.glob(raw.name + '.*'):
            f.unlink(missing_ok=True)
        opts.pop('download_ranges')
        with yt_dlp.YoutubeDL({k: v for k, v in opts.items() if v is not None}) as y:
            y.download([link])
        seek = start
    files = sorted(target.parent.glob(raw.name + '.*'))
    if not files:
        raise ValueError('O YouTube não entregou o trecho.')
    try:
        subprocess.run([M.FFMPEG, '-v', 'error', '-y', '-ss', f'{seek:.2f}', '-i', str(files[0]), '-t', f'{length:.2f}', '-an', '-c:v', 'libx264', '-preset', 'veryfast',
                        '-crf', '20', '-pix_fmt', 'yuv420p', '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', '-movflags', '+faststart', str(target)],
                       check=True, capture_output=True, creationflags=NO_WINDOW)
    finally:
        for f in files:
            f.unlink(missing_ok=True)
    return start


def _frames(path, count, width=640):
    import numpy as np
    info = T.probe(path, False)
    w = min(width, info['width'] - info['width'] % 2)
    h = max(2, round(w * info['height'] / info['width'] / 2) * 2)
    rate = count / max(.5, info['duration'])
    raw = subprocess.run([M.FFMPEG, '-v', 'error', '-i', str(path), '-vf', f'fps={rate:.4f},scale={w}:{h}', '-frames:v', str(count),
                          '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'], capture_output=True, creationflags=NO_WINDOW).stdout
    n = len(raw) // (w * h * 3)
    return [np.frombuffer(raw[i * w * h * 3:(i + 1) * w * h * 3], np.uint8).reshape(h, w, 3) for i in range(n)], info


_ENGINE = None


def _ocr(image):
    global _ENGINE
    if _ENGINE is None:
        from rapidocr import RapidOCR
        _ENGINE = RapidOCR(params={'Global.log_level': 'error'})
    result = _ENGINE(image)
    found = []
    for box, text, score in zip(result.boxes if result.boxes is not None else [], result.txts or [], result.scores or []):
        if float(score) >= .6 and len(re.sub(r'\W', '', text)) >= 3:
            found.append(text)
    return found


def inspect(path):
    """Texto na tela e marca d'água estática. Devolve os achados para o editor ver no cartão."""
    import cv2
    import numpy as np
    frames, info = _frames(path, 24)
    if not frames:
        raise ValueError('Não foi possível ler o clipe baixado.')
    text = []
    for f in frames[::8]:
        text += _ocr(f)
    grays = np.stack([cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32) for f in frames])
    motion = float(np.mean(np.abs(np.diff(grays, axis=0)))) if len(grays) > 1 else 0.0
    mark, lines = [], 0
    if len(grays) >= 8:
        # Marca d'água é estática: a borda fina dela não se mexe enquanto a cena embaixo se mexe.
        high = np.stack([g - cv2.GaussianBlur(g, (0, 0), 3) for g in grays])
        region = np.stack([cv2.GaussianBlur(g, (0, 0), 8) for g in grays]).std(0)
        mean, spread = np.abs(high.mean(0)), high.std(0)
        static = ((mean > 2.5) & (spread < mean * .6) & (region > 6)).astype(np.uint8) * 255
        found = cv2.HoughLinesP(static, 1, np.pi / 180, 40, minLineLength=int(.15 * static.shape[1]), maxLineGap=10)
        diagonal = strong = 0
        for x1, y1, x2, y2 in ([] if found is None else np.asarray(found).reshape(-1, 4)):
            # Paredes, teto e móveis dão linhas horizontais/verticais (ou em perspectiva sobre área quase parada);
            # a grade de banco pago é diagonal e atravessa a cena que se mexe embaixo dela.
            angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1))) % 180
            if min(angle, abs(angle - 90), 180 - angle) <= 6:
                continue
            diagonal += 1
            n = max(2, int(np.hypot(x2 - x1, y2 - y1)))
            xs, ys = np.linspace(x1, x2, n).astype(int), np.linspace(y1, y2, n).astype(int)
            if float(np.median(region[ys, xs])) >= 22 and float(mean[ys, xs].mean()) >= 9:
                strong += 1
        lines = strong
        if strong >= 3 and strong >= .4 * diagonal:
            mark.append(f'grade de marca d\'água sobre a imagem ({strong} linhas)')
        # Logotipo ou texto fixo: OCR na mediana com passa-alta (a cena se dissolve, a marca fica).
        if motion >= 2.0 and not text:  # com texto na tela, a mediana só relê a própria legenda
            median = np.median(grays, axis=0)
            hp = cv2.normalize(np.abs(median - cv2.GaussianBlur(median, (0, 0), 9)), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            mark += [t for t in _ocr(cv2.cvtColor(255 - hp, cv2.COLOR_GRAY2BGR)) if t not in text]
    return {'texto': list(dict.fromkeys(text))[:6], 'marca_dagua': list(dict.fromkeys(mark))[:6], 'movimento': round(motion, 1), 'linhas_fixas': lines,
            'largura': info['width'], 'altura': info['height'], 'duracao_s': round(info['duration'], 2)}


def _thumb(path, target):
    subprocess.run([M.FFMPEG, '-v', 'error', '-y', '-ss', '1', '-i', str(path), '-frames:v', '1', '-vf', 'scale=320:-2', '-q:v', '4', str(target)],
                   capture_output=True, creationflags=NO_WINDOW)


def status_of(found):
    if found.get('marca_dagua'):
        return 'marca_dagua'
    if found.get('texto'):
        return 'texto'
    return 'limpo'


SOURCES = {'youtube.com': 'yt', 'youtu.be': 'yt', 'tiktok.com': 'tt', 'pinterest.': 'pin', 'pin.it': 'pin'}
SOURCE_NAMES = {'yt': 'YouTube', 'tt': 'TikTok', 'pin': 'Pinterest'}


def _add(out, e, source):
    """Baixa o trecho, confere e grava o candidato. Devolve o id."""
    out = Path(out)
    cid = f'{source}-' + re.sub(r'[^\w-]', '', str(e['id']))[:40]
    (folder(out) / 'clipes').mkdir(parents=True, exist_ok=True)
    (folder(out) / 'miniaturas').mkdir(parents=True, exist_ok=True)
    clip = folder(out) / 'clipes' / f'{cid}.mp4'
    thumb = folder(out) / 'miniaturas' / f'{cid}.jpg'
    try:
        start = _download(e, clip)
        checks = inspect(clip)
        _thumb(clip, thumb)
    except Exception:
        clip.unlink(missing_ok=True)
        raise
    url = e.get('webpage_url') or (e.get('url') if source != 'yt' else '') or 'https://www.youtube.com/watch?v=' + e['id']
    state = load(out)
    state['candidatos'][cid] = {'youtube_id': e['id'], 'fonte': SOURCE_NAMES[source], 'titulo': e.get('title') or e.get('description') or '',
                                'canal': e.get('channel') or e.get('uploader') or '', 'canal_id': e.get('channel_id') or e.get('uploader_id') or '',
                                'url': url, 'inicio_origem_s': round(start, 2), 'arquivo': str(clip.relative_to(out)),
                                'miniatura': str(thumb.relative_to(out)), 'status': status_of(checks), **checks}
    save(out, state)
    return cid


def source_of(url):
    from urllib.parse import urlparse
    try:
        parsed = urlparse(str(url or '').strip())
    except ValueError:
        parsed = None
    host = (parsed.hostname or '').lower() if parsed and parsed.scheme in ('http', 'https') else ''
    for key, code in SOURCES.items():
        if key in host:
            return code
    raise ValueError('Cole o link de um vídeo do YouTube, TikTok ou Pinterest.')


def _from_link(out, url):
    """Lê o link, recusa revendedor e repetido, baixa e confere. Devolve o id do candidato."""
    import yt_dlp
    source = source_of(url)
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True, **_js()}) as y:
        info = y.extract_info(str(url).strip(), download=False)
    if info.get('entries'):
        info = next(iter(info['entries']))
    if not info.get('id') or (info.get('vcodec') == 'none' and not info.get('formats')):
        raise ValueError('Esse link não tem vídeo.')
    for key, cand in load(out)['candidatos'].items():  # já baixado em outra frase: reaproveita
        if str(cand.get('youtube_id')) == str(info['id']) and (Path(out) / cand['arquivo']).is_file():
            return key
    if _reseller(info):
        raise ValueError("Vídeo de banco pago revendido: costuma ter marca d'água. Escolha outro.")
    if (info.get('duration') or 0) > 900:
        raise ValueError('Vídeo longo demais para b-roll.')
    info['url'] = info.get('webpage_url') or str(url).strip()
    return _add(out, info, source)


def _attach(out, frase, ids, consulta=''):
    state = load(out)
    search = state['buscas'].setdefault(frase, {'consulta': '', 'quando': '', 'candidatos': [], 'ignorados': {}, 'falhas': 0})
    search['candidatos'] = list(dict.fromkeys(list(ids) + search['candidatos']))
    search['quando'] = time.strftime('%Y-%m-%d %H:%M')
    if consulta:
        search['consulta'] = consulta
    save(out, state)
    return state


def link_job(job, out, frase, url, library=False):
    """Vídeo escolhido pelo editor no TikTok, Pinterest ou YouTube: entra como candidato da frase."""
    out = Path(out)
    require_row(out, frase, library)
    job.step = f'Baixando o vídeo do {SOURCE_NAMES[source_of(url)]} e conferindo texto e marca d\'água'
    job.pct = .2
    cid = _from_link(out, url)
    state = _attach(out, frase, [cid])
    job.pct = 1
    return {'frase': frase, 'encontrados': 1, 'limpos': int(state['candidatos'][cid]['status'] == 'limpo'), 'candidato': cid}


def links_job(job, out, frase, urls, consulta='', fonte='', library=False):
    """Links coletados pelo app na busca do TikTok ou do Pinterest: baixa e confere um por um."""
    out = Path(out)
    require_row(out, frase, library)
    urls = [u for u in dict.fromkeys(str(u).strip() for u in urls or []) if u][:20]
    for u in urls:
        source_of(u)
    if not urls:
        raise ValueError('Nenhum vídeo coletado.')
    found, failed = [], 0
    for i, url in enumerate(urls):
        if job.cancel:
            raise M.Cancelled()
        job.step = f'Baixando e conferindo {i + 1} de {len(urls)} · {fonte or SOURCE_NAMES[source_of(url)]}'
        job.pct = .05 + .9 * i / len(urls)
        job.progress = {'tipo': 'broll', 'fase': 'Candidatos', 'processadas': i, 'total': len(urls), 'indeterminado': False}
        try:
            cid = _from_link(out, url)
        except Exception as error:  # vídeo removido, privado ou sem vídeo não derruba a lista
            failed += 1
            print(f'b-roll: {url} falhou: {error}', flush=True)
            continue
        found.append(cid)
        time.sleep(.8)
    state = _attach(out, frase, found, consulta)
    job.pct = 1
    clean = sum(state['candidatos'][c]['status'] == 'limpo' for c in found)
    return {'frase': frase, 'encontrados': len(found), 'limpos': clean, 'falhas': failed, 'fonte': fonte}


def _js():
    """Runtime de JavaScript para o YouTube quando houver um no computador (sem ele ainda baixa)."""
    import shutil
    found = {name: {} for name in ('deno', 'node') if shutil.which(name)}
    return {'js_runtimes': found} if found else {}

def search_job(job, out, frase, consulta, quantidade=6, library=False):
    """Procura, baixa um trecho de cada candidato e confere texto e marca d'água."""
    out = Path(out)
    require_row(out, frase, library)
    query = ' '.join(str(consulta or '').split())[:120]
    if not query:
        raise ValueError('Escreva o que procurar para esta frase.')
    engine = _engine()
    if not engine['ok']:
        raise ValueError(engine['erro'])
    full = query if 'footage' in query.lower() or 'b roll' in query.lower() else f'{query} {SUFFIX}'
    job.step = 'Procurando vídeos curtos no YouTube'
    job.pct = .05
    state = load(out)
    seen = {c.get('youtube_id') for c in state['candidatos'].values()}
    blocked = {c.get('canal_id') for c in state['candidatos'].values() if c.get('status') == 'marca_dagua' and c.get('canal_id')}
    entries, skipped = pick(search(full), seen, int(quantidade), blocked)
    found, failed = [], 0
    for i, e in enumerate(entries):
        if job.cancel:
            raise M.Cancelled()
        job.step = f'Baixando e conferindo {i + 1} de {len(entries)} · {e.get("title", "")[:50]}'
        job.pct = .1 + .85 * i / max(1, len(entries))
        job.progress = {'tipo': 'broll', 'fase': 'Candidatos', 'processadas': i, 'total': len(entries), 'indeterminado': False}
        try:
            cid = _add(out, e, 'yt')
        except Exception as error:  # um vídeo indisponível não derruba a busca
            failed += 1
            print(f'b-roll: {e["id"]} falhou: {error}', flush=True)
            if 'Sign in to confirm' in str(error):
                break
            time.sleep(1)
            continue
        found.append(cid)
        time.sleep(1.5)
    state = load(out)
    previous = state['buscas'].get(frase, {}).get('candidatos', [])
    state['buscas'][frase] = {'consulta': query, 'quando': time.strftime('%Y-%m-%d %H:%M'), 'candidatos': list(dict.fromkeys(found + previous)),
                              'ignorados': skipped, 'falhas': failed}
    save(out, state)
    job.pct = 1
    clean = sum(state['candidatos'][c]['status'] == 'limpo' for c in found)
    return {'frase': frase, 'encontrados': len(found), 'limpos': clean, 'ignorados': skipped, 'falhas': failed}


def choose(out, frase, candidato):
    """Escolha do editor: o clipe cobre a frase a partir do início dela, até o fim da frase ou do clipe."""
    out = Path(out)
    row = require_row(out, frase)
    state = load(out)
    if not candidato:
        state['escolhas'].pop(frase, None)
        save(out, state)
        return view(out)
    cand = state['candidatos'].get(candidato)
    if not cand or candidato not in state['buscas'].get(frase, {}).get('candidatos', []):
        raise ValueError('Esse clipe não é candidato desta frase.')
    if not (out / cand['arquivo']).is_file():
        raise ValueError('O clipe não está mais na pasta do projeto. Busque de novo.')
    end = min(row['fim_ms'], row['inicio_ms'] + int(cand['duracao_s'] * 1000))
    others = [(c['inicio_ms'], c['fim_ms']) for c in approved(out) if c['frase'] != frase]
    if any(a < end and row['inicio_ms'] < b for a, b in others):
        raise ValueError('Já há um b-roll escolhido sobre este trecho. Remova o outro primeiro.')
    state['escolhas'][frase] = {'candidato': candidato, 'arquivo': cand['arquivo'], 'inicio_ms': row['inicio_ms'], 'fim_ms': end,
                                'texto': row['texto'], 'status': cand['status'], 'quando': time.strftime('%Y-%m-%d %H:%M')}
    save(out, state)
    return view(out)


def approved(out, eligible=None):
    """B-rolls escolhidos cujo arquivo ainda existe (ordem do tempo do original)."""
    out = Path(out)
    choices = load(out).get('escolhas', {})
    if not choices:
        return []
    if eligible is None:
        eligible, _ = _eligible_rows(out)
    starts = {row['id']: row['inicio_ms'] for row in eligible}
    rows = []
    for frase, c in sorted(choices.items(), key=lambda kv: kv[1]['inicio_ms']):
        if frase not in starts or c['inicio_ms'] < starts[frase]:
            continue
        path = out / c['arquivo']
        if path.is_file() and c['fim_ms'] > c['inicio_ms']:
            rows.append(c | {'frase': frase, 'path': path})
    return rows
