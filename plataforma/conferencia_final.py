"""Conferência final do vídeo exportado e relatório de entrega para o cliente.

Lê o vídeo pronto neste computador: transcrição local do áudio e leitura de texto (OCR) dos
quadros. Procura o nome do produto antigo e suas grafias no áudio, na imagem e na legenda
gravada, e, quando o projeto tem troca de preços, os valores antigos. Nada é enviado para fora.
Resultado automático: indica pontos para conferir, não substitui a revisão humana.
"""
import base64
import html
import json
import math
import os
import platform
import re
import subprocess
import time
from pathlib import Path

from . import ml_core as M, trocas as T

VERSION = 'conferencia-final-1'
VIDEO = {'.mp4', '.mov', '.m4v', '.mkv', '.webm'}
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def folder(out): return Path(out) / 'entregas' / 'conferencia_final'


def state_path(out): return folder(out) / 'estado.json'


def load(out):
    try:
        return json.loads(state_path(out).read_text())
    except (OSError, ValueError):
        return {}


def check_path(value):
    """Vídeo escolhido pelo editor: precisa existir e ser um vídeo."""
    path = Path(str(value or '')).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise ValueError('Escolha o vídeo exportado do Premiere.')
    if path.suffix.lower() not in VIDEO:
        raise ValueError('Escolha um vídeo (MP4, MOV, M4V, MKV ou WEBM).')
    return path.resolve()


def names(out, plan):
    """Nome do produto e grafias cadastradas pelo editor.

    A lista automática da conferência de menções pode incluir palavras comuns da copy
    (ex.: "gelatin" numa VSL de gelatina), que gerariam alarmes falsos no vídeo final.
    """
    aliases = ','.join(str(v) for v in (plan.get('produto', ''), plan.get('produto_aliases', ''), (plan.get('editorial') or {}).get('aliases', '')) if v)
    return [n for n in dict.fromkeys(x.strip() for x in re.split(r'[,;\n]', aliases)) if n]


def old_prices(out):
    """Valores antigos da troca de preços (só quando o projeto troca preços)."""
    file = Path(out) / 'precos_TROCA.json'
    try:
        mapping = json.loads(file.read_text()).get('mapa_precos') or {}
    except (OSError, ValueError):
        return []
    found = []
    for old, new in mapping.items():
        digits, target = re.sub(r'[^\d.,]', '', str(old)), re.sub(r'[^\d.,]', '', str(new))
        if digits and digits != target and re.search(r'\d', digits):
            found.append(digits.rstrip('.,'))
    return sorted(set(found), key=len, reverse=True)


def _clock(seconds):
    total = max(0, int(seconds))
    return f'{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}' if total >= 3600 else f'{total // 60:02d}:{total % 60:02d}'


def _audio(job, out, path, aliases, prices):
    from . import validacao as V
    engine = 'mlx' if platform.system() == 'Darwin' and platform.machine() == 'arm64' else 'fw'
    cache = folder(out) / ('asr_' + T.digest([VERSION, *T.source_identity(path), path.name]) + '.json')
    try:
        transcript = json.loads(cache.read_text())
    except (OSError, ValueError):
        transcript = V.transcribe(job, path, {'motor': engine, 'idioma': 'auto'})
        T.write(cache, transcript)  # refazer a conferência não transcreve de novo
    report = V.analyze(transcript['words'], ','.join(aliases))
    hits = [{'tipo': 'produto', 'inicio_s': round(h['mencao_inicio'], 2), 'fim_s': round(h['mencao_fim'], 2), 'termo': h['termo'],
             'certeza': 'encontrado' if h['status'] == 'encontrado' else 'possivel', 'contexto': h['texto']} for h in report['resquicios']]
    words = transcript['words']
    for i, w in enumerate(words):
        token = re.sub(r'[^\d.,]', '', str(w['w'])).rstrip('.,')
        if token and token in prices:
            context = ' '.join(x['w'] for x in words[max(0, i - 6):i + 7])
            hits.append({'tipo': 'preco', 'inicio_s': round(float(w['s']), 2), 'fim_s': round(float(w['e']), 2), 'termo': token,
                         'certeza': 'possivel', 'contexto': context})
    hits.sort(key=lambda h: h['inicio_s'])
    return hits, {'motor': transcript.get('engine'), 'palavras': len(words)}


def _ocr(job, out, path, info, aliases, prices):
    from . import deteccao_visual as D
    directory = folder(out) / ('ocr_' + T.digest([VERSION, *T.source_identity(path), str(path.name)]))
    directory.mkdir(parents=True, exist_ok=True)
    start, end = 0.0, info['duration']
    units = D.units(start, end)
    pending = [u for u in units if not D.unit_file(directory, u).exists()]
    width, height = D.frame_size(info)
    if pending:
        count = max(1, min(4, (os.cpu_count() or 2) // 2, len(pending)))
        groups = [pending[i::count] for i in range(count)]
        procs = [subprocess.Popen([M.PY, str(M.BASE / 'ocr_worker.py'), str(path), str(directory), '--ffmpeg', M.FFMPEG,
                                   '--unidades', ','.join(f'{u:.3f}' for u in g), '--duracao', str(D.UNIT_S),
                                   '--largura', str(width), '--altura', str(height), '--threads', '1'],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=NO_WINDOW) for g in groups]
        try:
            while any(p.poll() is None for p in procs):
                if job.cancel:
                    raise M.Cancelled()
                done = sum(D.unit_file(directory, u).exists() for u in pending)
                job.pct = .55 + .35 * done / len(pending)
                job.step = f'Lendo a imagem do vídeo final · {done} de {len(pending)} minuto(s)'
                job.progress = {'tipo': 'conferencia_final', 'fase': 'Leitura da imagem', 'processadas': done, 'total': len(pending), 'indeterminado': False}
                time.sleep(.5)
            failed = next((p for p in procs if p.returncode), None)
            if failed:
                raise RuntimeError(M.process_error(failed.stderr.read().decode('utf-8', 'replace'), failed.returncode))
        finally:
            for p in procs:
                if p.poll() is None:
                    p.kill(); p.wait()
                if p.stderr:
                    p.stderr.close()
    samples, changes = D.read_samples(directory, units, start, end)
    wanted = [D.norm(n) for n in aliases if D.norm(n)]
    hits = []
    for item in D.group(samples, changes, wanted) if wanted else []:
        if item['nota'] < .9:
            continue  # leitura distante do nome (ex.: "get in") não vira ponto no relatório do cliente
        hits.append({'tipo': 'produto', 'local': item['local'], 'inicio_s': round(item['inicio_ms'] / 1000, 2), 'fim_s': round(item['fim_ms'] / 1000, 2),
                     'termo': item['texto'], 'certeza': 'encontrado' if item['nota'] >= D.HIGH else 'possivel', 'leituras': item['leituras']})
    if prices:
        last = -10.0
        for t, rows in samples:
            for row in rows:
                text = str(row[0])
                number = next((p for p in prices if re.search(r'(?<![\d.,])' + re.escape(p) + r'(?![\d])', text)), None)
                # Valor antigo na tela só conta com cara de preço ($, R$ ou "preço").
                if number and re.search(r'[$€£]|R\$|USD|price|preço|precio', text, re.I) and t - last > 2:
                    hits.append({'tipo': 'preco', 'local': D.place(row), 'inicio_s': round(t, 2), 'fim_s': round(t + 1, 2), 'termo': text[:60], 'certeza': 'possivel'})
                    last = t
    hits.sort(key=lambda h: h['inicio_s'])
    return hits, {'minutos': len(units), 'minutos_reaproveitados': len(units) - len(pending), 'quadros_lidos': len(samples)}


def _frame(path, seconds, target):
    subprocess.run([M.FFMPEG, '-v', 'error', '-y', '-ss', f'{max(0, seconds):.2f}', '-i', str(path), '-frames:v', '1',
                    '-vf', 'scale=-2:180', '-q:v', '5', str(target)], capture_output=True, timeout=60, creationflags=NO_WINDOW)
    return target if target.is_file() else None


def check_job(job, out, caminho):
    """Tarefa: confere o vídeo exportado e gera o relatório de entrega."""
    out = Path(out)
    path = check_path(caminho)
    plan = T.load(out)
    info = T.probe(path, False)
    aliases = [] if plan.get('somente_valores') else names(out, plan)
    prices = old_prices(out)
    if not aliases and not prices:
        raise ValueError('Informe o produto antigo do projeto antes da conferência final.')
    started = time.perf_counter()
    job.step = 'Transcrevendo o áudio do vídeo final'
    audio, audio_info = _audio(job, out, path, aliases, prices) if info.get('has_audio', True) else ([], {})
    if job.cancel:
        raise M.Cancelled()
    image, image_info = _ocr(job, out, path, info, aliases, prices) if info['video'] else ([], {})
    job.step = 'Montando o relatório de entrega'
    job.pct = .93
    stamp = time.strftime('%Y%m%d-%H%M%S')
    target = folder(out) / stamp
    target.mkdir(parents=True, exist_ok=True)
    for hit in image + audio:
        frame = _frame(path, (hit['inicio_s'] + hit['fim_s']) / 2, target / f'quadro_{len(os.listdir(target)):03d}.jpg') if info['video'] else None
        hit['quadro'] = frame.name if frame else ''
    report = build_report(out, plan, path, info, audio, image, audio_info, image_info, aliases, prices, time.perf_counter() - started)
    T.write(target / 'relatorio.json', report)
    (target / 'relatorio.html').write_text(render_html(report, target), encoding='utf-8')
    summary = {'quando': report['quando'], 'arquivo_video': path.name, 'aprovado': report['aprovado'], 'pontos': report['pontos'],
               'relatorio': str((target / 'relatorio.html').relative_to(out)), 'json': str((target / 'relatorio.json').relative_to(out)),
               'fonte': T.source_identity(path)}
    T.write(state_path(out), {'ultima': summary, 'historico': (load(out).get('historico') or [])[-9:] + [summary]})
    job.pct = 1
    job.step = 'Conferência final concluída · ' + ('nenhuma menção encontrada' if report['aprovado'] else f"{report['pontos']} ponto(s) para conferir")
    return summary | {'para_revisar': report['pontos']}


def build_report(out, plan, path, info, audio, image, audio_info, image_info, aliases, prices, seconds):
    from . import identidade_entrega as ID
    try:
        identity = ID.identity(plan, out)['nome_sequencia']
    except (ValueError, OSError, KeyError):
        identity = Path(out).name
    selected = [r for r in plan.get('itens', []) if r.get('aprovado')]
    visual = {}
    try:
        from . import conferencia_visual as CV
        visual = CV.summary(out)
    except (ValueError, OSError, KeyError):
        pass
    found = [h for h in audio + image if h['certeza'] == 'encontrado']
    return {'formato': VERSION, 'quando': time.strftime('%d/%m/%Y %H:%M'), 'projeto': identity,
            'produto_antigo': plan.get('produto', ''), 'produto_novo': plan.get('produto_novo', ''),
            'somente_valores': bool(plan.get('somente_valores')), 'termos': aliases, 'precos_antigos': prices,
            'video': {'arquivo': path.name, 'duracao_s': round(info['duration'], 2), 'largura': info.get('width'), 'altura': info.get('height')},
            'trocas': {'falas_substituidas': len(selected),
                       'aparicoes_cobertas': (visual.get('cobertura') or {}).get('cobertas', 0),
                       'aparicoes_aprovadas': (visual.get('aparicoes') or {}).get('aprovadas', 0)},
            'audio': audio, 'imagem': [h for h in image if h.get('local') != 'legenda'], 'legenda': [h for h in image if h.get('local') == 'legenda'],
            'pontos': len(audio) + len(image), 'encontrados': len(found), 'aprovado': not (audio or image),
            'detalhes': {'audio': audio_info, 'imagem': image_info, 'tempo_s': round(seconds, 1)},
            'metodo': 'Conferência automática local: transcrição do áudio do vídeo exportado e leitura de texto dos quadros (cerca de 1 por segundo e após cada corte). '
                      'Encontra nomes e grafias próximas do produto antigo e valores antigos. Erros de reconhecimento podem ocultar ou sugerir ocorrências; '
                      'a conferência humana continua necessária.'}


def _img(target, name):
    file = Path(target) / name if name else None
    if not file or not file.is_file():
        return ''
    return 'data:image/jpeg;base64,' + base64.b64encode(file.read_bytes()).decode()


def render_html(report, target):
    """Página única, com as imagens embutidas: pode ser enviada ao cliente como está."""
    e = html.escape
    def rows(items, kind):
        if not items:
            return f'<p class="ok">✓ Nenhuma ocorrência encontrada {kind}.</p>'
        out = []
        for h in items:
            image = _img(target, h.get('quadro'))
            what = 'Valor antigo' if h['tipo'] == 'preco' else 'Produto antigo'
            sure = 'Encontrado' if h['certeza'] == 'encontrado' else 'Possível · conferir'
            context = '<br><small>' + e(h.get('contexto', ''))[:180] + '</small>' if h.get('contexto') else ''
            picture = '<img src="' + image + '" alt="">' if image else ''
            out.append('<tr><td class="tc">' + _clock(h['inicio_s']) + '</td><td>' + e(what) + '<br><small>' + e(sure) + '</small></td>'
                       '<td>“' + e(str(h.get('termo', ''))) + '”' + context + '</td><td>' + picture + '</td></tr>')
        return '<table><tr><th>Tempo</th><th>Tipo</th><th>Trecho</th><th>Quadro</th></tr>' + ''.join(out) + '</table>'
    r = report
    status = ('<div class="badge ok">Conferência aprovada</div><p>Nenhuma menção ao produto antigo foi encontrada no áudio, na imagem e na legenda gravada do vídeo exportado.</p>'
              if r['aprovado'] else f'<div class="badge warn">{r["pontos"]} ponto(s) para conferir</div><p>Os trechos abaixo foram apontados pela conferência automática. Confira cada um no vídeo.</p>')
    swap = f'{e(r["produto_antigo"])} → {e(r["produto_novo"])}' if not r['somente_valores'] else 'Otimização de preços e kits'
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Relatório de entrega · {e(r["projeto"])}</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:960px;margin:32px auto;padding:0 20px;color:#1d1f24;background:#fff}}
h1{{font-size:24px;margin:0}}h2{{font-size:17px;margin:28px 0 8px;border-bottom:1px solid #e3e5ea;padding-bottom:6px}}
.meta{{color:#666;font-size:13px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}}
.grid div{{border:1px solid #e3e5ea;border-radius:10px;padding:10px}}.grid b{{display:block;font-size:22px}}
.badge{{display:inline-block;padding:6px 14px;border-radius:999px;font-weight:600;margin:14px 0 4px}}.badge.ok{{background:#e5f6ee;color:#17734a}}.badge.warn{{background:#fff3df;color:#8a5a00}}
p.ok{{color:#17734a}}table{{border-collapse:collapse;width:100%;font-size:13.5px}}th,td{{text-align:left;border-bottom:1px solid #eee;padding:8px;vertical-align:top}}
td.tc{{font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:600}}img{{height:90px;border-radius:6px}}small{{color:#777}}
footer{{margin-top:32px;font-size:12px;color:#777}}@media print{{body{{margin:0}}}}</style></head><body>
<p class="meta">Relatório de entrega · {e(r["quando"])}</p><h1>{e(r["projeto"])}</h1><p class="meta">{swap} · vídeo {e(r["video"]["arquivo"])} · {_clock(r["video"]["duracao_s"])}</p>
{status}
<div class="grid"><div><b>{r["trocas"]["falas_substituidas"]}</b>falas substituídas</div><div><b>{r["trocas"]["aparicoes_cobertas"]}</b>aparições do produto cobertas</div>
<div><b>{len(r["audio"])}</b>pontos no áudio</div><div><b>{len(r["imagem"]) + len(r["legenda"])}</b>pontos na imagem e legenda</div></div>
<h2>Áudio</h2>{rows(r["audio"], "no áudio")}
<h2>Imagem</h2>{rows(r["imagem"], "na imagem")}
<h2>Legenda gravada</h2>{rows(r["legenda"], "na legenda gravada")}
<h2>Como foi conferido</h2><p class="meta">{e(r["metodo"])} Termos procurados: {e(", ".join(r["termos"]) or "—")}{(" · valores antigos: " + e(", ".join(r["precos_antigos"]))) if r["precos_antigos"] else ""}.</p>
<footer>Gerado pelo Ripagem Maker neste computador. Nenhum vídeo ou áudio foi enviado para serviços externos.</footer></body></html>'''


def view(out):
    data = load(out)
    last = data.get('ultima')
    if last:
        last = dict(last, existe=(Path(out) / last['relatorio']).is_file())
    return {'ultima': last, 'historico': data.get('historico', [])}
