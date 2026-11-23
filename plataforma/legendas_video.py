"""Vídeo com legendas aplicadas: estilo, presets, prévia curta e render da montagem final em blocos.

A montagem é a mesma do XML (V1 com extensões, V2, margens removidas) e o áudio é o áudio final da
montagem. As medidas do estilo são relativas à altura/largura do vídeo, então um preset serve para
16:9, 9:16 ou 1:1. O render completo é feito em blocos de 60 s guardados: cancelar não perde o pronto.
"""
import json
import math
import os
import re
import subprocess
import time
from pathlib import Path

from . import ml_core as M, trocas as T, legendas as L

VERSION = 'video-legendas-1'
CHUNK_S = 60
PREVIEW_S = 15
STYLE = {'fonte': 'Arial', 'tamanho': 6.0, 'negrito': True, 'italico': False, 'maiusculas': False,
         'cor': '#FFFFFF', 'cor_destaque': '#FFD400', 'contorno': .35, 'cor_contorno': '#000000',
         'sombra': .2, 'cor_sombra': '#000000', 'opacidade_sombra': .6,
         'fundo': False, 'cor_fundo': '#000000', 'opacidade_fundo': .7,
         'posicao': 'inferior', 'alinhamento': 'centro', 'margem_vertical': 8.0, 'margem_lateral': 6.0,
         'exibicao': 'frase', 'palavras_bloco': 3, 'caracteres_linha': 32, 'linhas': 2}
BUILTIN = {
    'Clássico · contorno': {},
    'Caixa escura': {'fundo': True, 'contorno': 0, 'sombra': 0, 'negrito': False, 'tamanho': 5.5},
    'Destaque da palavra': {'exibicao': 'destaque', 'tamanho': 6.5, 'contorno': .45},
    'Vertical 9:16 · palavras': {'exibicao': 'palavras', 'palavras_bloco': 3, 'tamanho': 4.2, 'maiusculas': True,
                                 'posicao': 'meio', 'margem_vertical': 0, 'contorno': .4, 'linhas': 1},
}
HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')
FONT_DIRS = ['/System/Library/Fonts', '/System/Library/Fonts/Supplemental', '/Library/Fonts', str(Path.home() / 'Library/Fonts'),
             'C:/Windows/Fonts', str(Path.home() / 'AppData/Local/Microsoft/Windows/Fonts')]
FONTS = {'Arial': ('Arial.ttf', 'arial.ttf'), 'Arial Black': ('Arial Black.ttf', 'ariblk.ttf'), 'Helvetica Neue': ('HelveticaNeue.ttc',),
         'Avenir Next': ('Avenir Next.ttc',), 'Futura': ('Futura.ttc',), 'Impact': ('Impact.ttf', 'impact.ttf'),
         'Verdana': ('Verdana.ttf', 'verdana.ttf'), 'Georgia': ('Georgia.ttf', 'georgia.ttf'), 'Trebuchet MS': ('Trebuchet MS.ttf', 'trebuc.ttf'),
         'Tahoma': ('Tahoma.ttf', 'tahoma.ttf'), 'Montserrat': ('Montserrat-Bold.ttf', 'Montserrat-Regular.ttf', 'Montserrat[wght].ttf'),
         'Roboto': ('Roboto-Bold.ttf', 'Roboto-Regular.ttf'), 'Inter': ('Inter-Bold.ttf', 'Inter[opsz,wght].ttf')}


def folder(out): return Path(out) / 'trocas/render'
def path(out): return folder(out) / 'estado.json'
def presets_path(): return M.WS / 'legendas_presets.json'


def fonts():
    """Famílias encontradas neste computador (o render usa as fontes do sistema)."""
    found = []
    for family, files in FONTS.items():
        if any((Path(d) / f).exists() for d in FONT_DIRS for f in files):
            found.append(family)
    return found


def clean_style(style):
    result = dict(STYLE)
    for key, default in STYLE.items():
        if key not in (style or {}):
            continue
        value = style[key]
        if isinstance(default, bool):
            result[key] = bool(value)
        elif isinstance(default, (int, float)):
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ValueError('Valor inválido em ' + key) from None
            if not math.isfinite(value):
                raise ValueError('Valor inválido em ' + key)
            result[key] = int(value) if isinstance(default, int) and not isinstance(default, bool) else value
        elif key.startswith('cor'):
            if not HEX.match(str(value)):
                raise ValueError('Use cores no formato #RRGGBB.')
            result[key] = str(value).upper()
        else:
            result[key] = str(value)[:60]
    checks = [(1 <= result['tamanho'] <= 20, 'Tamanho da fonte: 1 a 20% da altura.'), (0 <= result['contorno'] <= 3, 'Contorno: 0 a 3%.'),
              (0 <= result['sombra'] <= 3, 'Sombra: 0 a 3%.'), (0 <= result['margem_vertical'] <= 45, 'Margem vertical: 0 a 45%.'),
              (0 <= result['margem_lateral'] <= 30, 'Margem lateral: 0 a 30%.'), (result['posicao'] in ('inferior', 'meio', 'superior'), 'Posição inválida.'),
              (result['alinhamento'] in ('esquerda', 'centro', 'direita'), 'Alinhamento inválido.'),
              (result['exibicao'] in ('frase', 'destaque', 'palavras'), 'Exibição inválida.'), (1 <= result['palavras_bloco'] <= 8, 'Palavras por bloco: 1 a 8.'),
              (12 <= result['caracteres_linha'] <= 80, 'Caracteres por linha: 12 a 80.'), (result['linhas'] in (1, 2, 3), 'Linhas: 1 a 3.'),
              (0 <= result['opacidade_fundo'] <= 1 and 0 <= result['opacidade_sombra'] <= 1, 'Opacidade: 0 a 1.'), (bool(result['fonte'].strip()), 'Escolha uma fonte.')]
    for ok, message in checks:
        if not ok:
            raise ValueError(message)
    return result


# ---------- presets ----------

def presets():
    try:
        user = json.loads(presets_path().read_text())
    except (OSError, ValueError):
        user = {}
    mine = {}
    for name, values in (user.items() if isinstance(user, dict) else ()):
        # Um preset salvo com limites antigos (ou editado à mão) não pode derrubar a tela de legendas.
        try:
            mine[name] = clean_style(values)
        except (TypeError, ValueError):
            continue
    return {'padrao': {name: clean_style(values) for name, values in BUILTIN.items()}, 'meus': mine}


def save_preset(name, style):
    name = str(name).strip()[:40]
    if not name or name in BUILTIN:
        raise ValueError('Dê um nome novo ao preset (os padrões não podem ser substituídos).')
    data = presets()['meus']
    data[name] = clean_style(style)
    T.write(presets_path(), data)
    return presets()


def delete_preset(name):
    data = presets()['meus']
    data.pop(str(name), None)
    T.write(presets_path(), data)
    return presets()


# ---------- ASS ----------

def ass_color(value, opacity=1.0):
    r, g, b = value[1:3], value[3:5], value[5:7]
    return f'&H{round((1 - opacity) * 255):02X}{b}{g}{r}'.upper()


def ass_time(seconds):
    cs = max(0, round(seconds * 100))
    return f'{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}'


def escape(text, upper=False):
    text = str(text).replace('\\', '/').replace('{', '(').replace('}', ')')
    return text.upper() if upper else text


def ass(cue_list, style, width, height):
    s = style
    align = {'inferior': 0, 'meio': 3, 'superior': 6}[s['posicao']] + {'esquerda': 1, 'centro': 2, 'direita': 3}[s['alinhamento']]
    box = s['fundo']
    outline = height * (.012 if box else s['contorno'] / 100)
    header = ['[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {width}', f'PlayResY: {height}', 'WrapStyle: 2', 'ScaledBorderAndShadow: yes', '',
              '[V4+ Styles]',
              'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, '
              'ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
              f"Style: Legenda,{s['fonte']},{round(height * s['tamanho'] / 100)},{ass_color(s['cor'])},{ass_color(s['cor_destaque'])},"
              f"{ass_color(s['cor_fundo'], s['opacidade_fundo']) if box else ass_color(s['cor_contorno'])},{ass_color(s['cor_sombra'], s['opacidade_sombra'])},"
              f"{-1 if s['negrito'] else 0},{-1 if s['italico'] else 0},0,0,100,100,0,0,{3 if box else 1},{outline:.2f},{height * s['sombra'] / 100:.2f},"
              f"{align},{round(width * s['margem_lateral'] / 100)},{round(width * s['margem_lateral'] / 100)},{round(height * s['margem_vertical'] / 100)},1",
              '', '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    events = []
    rgb = s['cor_destaque']
    highlight = '{\\c&H' + (rgb[5:7] + rgb[3:5] + rgb[1:3]).upper() + '&}'
    for cue in cue_list:
        words = [escape(w['texto'], s['maiusculas']) for w in cue['palavras']]
        breaks, position = set(), 0
        for line in cue['linhas'][:-1]:
            position += len(line.split())
            breaks.add(position)

        def compose(current=None):
            parts = []
            for k, word in enumerate(words):
                if k:
                    parts.append('\\N' if k in breaks else ' ')
                parts.append(highlight + word + '{\\r}' if k == current else word)
            return ''.join(parts)
        if s['exibicao'] == 'destaque' and len(words) > 1:
            times = [w['inicio'] for w in cue['palavras']]
            for k in range(len(words)):
                a = cue['inicio'] if k == 0 else max(cue['inicio'], times[k])
                b = cue['fim'] if k == len(words) - 1 else min(cue['fim'], max(a, times[k + 1]))
                if b - a >= .01:
                    events.append(f'Dialogue: 0,{ass_time(a)},{ass_time(b)},Legenda,,0,0,0,,{compose(k)}')
        else:
            events.append(f"Dialogue: 0,{ass_time(cue['inicio'])},{ass_time(cue['fim'])},Legenda,,0,0,0,,{compose()}")
    return '\n'.join(header + events) + '\n'


def words_state(out):
    file = L.folder(out) / 'palavras.json'
    if not file.exists():
        raise ValueError('Gere primeiro o SRT da montagem (bloco acima): ele alinha o texto com o áudio final.')
    data = json.loads(file.read_text())
    state = L.load(out)
    result = state.get('resultado') or {}
    if data.get('assinatura') != result.get('assinatura') or L.view(out).get('desatualizado'):
        raise ValueError('As legendas da montagem estão desatualizadas. Gere o SRT da montagem novamente.')
    return data


def build_cues(data, style):
    config = {'caracteres_linha': style['caracteres_linha'], 'linhas': 1 if style['exibicao'] == 'palavras' else style['linhas'],
              'duracao_max_s': 6.0, 'palavras_bloco': style['palavras_bloco'] if style['exibicao'] == 'palavras' else 0}
    windows = [tuple(w) for w in data['janelas']] if data.get('janelas') is not None else None
    return L.cues([dict(w) for w in data['palavras']], config, data['nomes'], windows)


# ---------- montagem final ----------

class Montage:
    """Mesma composição do XML: V1 (com extensões), V2 e margens removidas, no tempo final."""

    def __init__(self, job, out):
        from . import visuais as VIS, montagem as MT, fechamento as FC
        self.out = Path(out)
        plan = T.load(out)
        rows = T.approved(plan, True)
        self.info = T.probe(T.source(out))
        if not self.info['video']:
            raise ValueError('O vídeo com legendas exige o vídeo original; este trabalho tem só áudio.')
        visuals = VIS.valid_prepared(out, True) if VIS.path(out).exists() else []
        self.fps = self.info['fps']
        self.width, self.height = self.info['width'] - self.info['width'] % 2, self.info['height'] - self.info['height'] % 2
        self.layout = MT.parts(job, out, rows, visuals, self.info)
        self.closures = FC.windows(self.layout['changes'], self.fps)
        self.FC = FC
        self.frames = FC.position(self.layout['frames'], self.closures)

    def ranges(self, a, b):
        """Intervalos pré-fechamento que formam os quadros finais [a, b)."""
        result = []
        for lo, hi in self.FC.kept(0, self.layout['frames'], self.closures):
            start = self.FC.position(lo, self.closures)
            x, y = max(a, start), min(b, start + hi - lo)
            if y > x:
                result.append((lo + x - start, lo + y - start))
        return result

    def command(self, a, b, ass_file, target, scale=None, audio=None, crf=18):
        fps, w, h = self.fps, self.width, self.height
        cmd = [M.FFMPEG, '-y', '-v', 'error']
        filters, segments, n = [], [], 0
        for r, (x, y) in enumerate(self.ranges(a, b)):
            base = []
            for piece in self.layout['video']:
                s, e = max(x, piece['start']), min(y, piece['end'])
                if e <= s:
                    continue
                cmd += ['-ss', f"{(piece['in'] + s - piece['start']) / fps:.6f}", '-t', f'{(e - s) / fps + 1 / fps:.6f}', '-i', str(piece['path'])]
                filters.append(f'[{n}:v:0]fps={fps:.8f},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,'
                               f'trim=end_frame={e - s},setpts=N/({fps:.8f}*TB)[b{r}_{len(base)}]')
                base.append(f'[b{r}_{len(base)}]')
                n += 1
            label = f'r{r}'
            filters.append(''.join(base) + f'concat=n={len(base)}:v=1:a=0[{label}base]')
            current = f'{label}base'
            for k, piece in enumerate(self.layout['visuals']):
                s, e = max(x, piece['start']), min(y, piece['end'])
                if e <= s:
                    continue
                cmd += ['-ss', f"{(piece['in'] + s - piece['start']) / fps:.6f}", '-t', f'{(e - s) / fps + 1 / fps:.6f}', '-i', str(piece['path'])]
                filters.append(f'[{n}:v:0]fps={fps:.8f},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,'
                               f'trim=end_frame={e - s},setpts=PTS-STARTPTS+{(s - x) / fps:.6f}/TB[o{r}_{k}]')
                filters.append(f"[{current}][o{r}_{k}]overlay=eof_action=pass:enable='between(t,{(s - x) / fps:.6f},{(e - x) / fps - .0001:.6f})'[{label}v{k}]")
                current = f'{label}v{k}'
                n += 1
            filters.append(f'[{current}]trim=end_frame={y - x},setpts=PTS-STARTPTS[{label}]')
            segments.append(f'[{label}]')
        start = a / fps
        escaped = str(ass_file).replace('\\', '/').replace(':', '\\:').replace("'", "\\'")
        tail = f"setpts=PTS-STARTPTS+{start:.6f}/TB,ass='{escaped}',setpts=PTS-STARTPTS"
        if scale:
            tail += f',scale=-2:{min(scale, h)}'
        filters.append(''.join(segments) + f'concat=n={len(segments)}:v=1:a=0,{tail},format=yuv420p[vout]')
        if audio:
            cmd += ['-ss', f'{start:.6f}', '-t', f'{(b - a) / fps:.6f}', '-i', str(audio)]
        cmd += ['-filter_complex', ';'.join(filters), '-map', '[vout]']
        if audio:
            cmd += ['-map', f'{n}:a:0', '-c:a', 'aac', '-b:a', '192k']
        cmd += ['-r', f'{fps:.8f}', '-frames:v', str(b - a), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', str(crf), '-movflags', '+faststart', str(target)]
        return cmd


def montage_audio(job, out):
    """Áudio final da montagem, reaproveitando o da transcrição quando a montagem é a mesma."""
    key = L.audio_signature(out)
    cache = L.audio_cache(out)
    data = json.loads(cache.read_text()) if cache.exists() else {}
    if data.get('audio') and (Path(out) / data['audio']).is_file():
        return Path(out) / data['audio']
    own = folder(out) / f'audio_{key}.m4a'
    if own.is_file():
        return own
    job.step = 'Montando o áudio final da montagem'
    own.parent.mkdir(parents=True, exist_ok=True)
    Path(T.mix(job, out)).replace(own)
    if data:
        data['audio'] = str(own.relative_to(out))
        T.write(cache, data)
    return own


# ---------- estado e tarefas ----------

def load(out):
    state = json.loads(path(out).read_text()) if path(out).exists() else {}
    state['estilo'] = clean_style(state.get('estilo') or {})
    return state


def view(out):
    state = load(out)
    state.update(presets=presets(), fontes=fonts())
    try:
        data = words_state(out)
        state['palavras_confiaveis'] = data.get('alinhamento_por_palavra', False)
        state['so_coberturas'] = data.get('janelas') is not None
        current = signature(out, state['estilo'])
        for key in ('previa', 'final'):
            if state.get(key):
                state[key]['atual'] = state[key].get('assinatura') == current
    except ValueError as error:
        state['bloqueio'] = str(error)
    return state


def save_style(out, style):
    with T.LOCK:
        state = load(out)
        state['estilo'] = clean_style(style)
        T.write(path(out), state)
    return view(out)


def signature(out, style):
    data = words_state(out)
    return T.digest([VERSION, data['assinatura'], style])


def write_ass(out, style, montage):
    data = words_state(out)
    if style['exibicao'] == 'destaque' and not data.get('alinhamento_por_palavra'):
        style = dict(style, exibicao='frase')
    cue_list = build_cues(data, style)
    target = folder(out) / f'legendas_{signature(out, style)[:12]}.ass'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(ass(cue_list, style, montage.width, montage.height), encoding='utf-8')
    return target, cue_list


def preview_job(job, out, inicio=None, style=None):
    out = Path(out)
    style = clean_style(style or load(out)['estilo'])
    job.step = 'Preparando a montagem'
    montage = Montage(job, out)
    ass_file, cue_list = write_ass(out, style, montage)
    if inicio is None:
        inicio = max(0.0, (cue_list[0]['inicio'] if cue_list else 0) - 1)
    inicio = max(0.0, min(float(inicio), montage.frames / montage.fps - 1))
    audio = montage_audio(job, out)
    a = round(inicio * montage.fps)
    b = min(montage.frames, a + round(PREVIEW_S * montage.fps))
    target = folder(out) / f'previa_{T.digest([signature(out, style), a])[:10]}.mp4'
    job.step = 'Renderizando a prévia de 15 s com as legendas'
    job.pct = .5
    M.run_proc(job, montage.command(a, b, ass_file, target, scale=720, audio=audio, crf=23))
    with T.LOCK:
        state = load(out)
        state.update(estilo=style, previa={'arquivo': str(target.relative_to(out)), 'inicio': a / montage.fps, 'assinatura': signature(out, style)})
        T.write(path(out), state)
    job.pct = 1
    job.step = 'Prévia pronta'
    return state['previa']


def render_job(job, out, style=None):
    out = Path(out)
    started = time.perf_counter()
    style = clean_style(style or load(out)['estilo'])
    job.step = 'Preparando a montagem'
    montage = Montage(job, out)
    ass_file, _ = write_ass(out, style, montage)
    audio = montage_audio(job, out)
    key = signature(out, style)
    chunk = round(CHUNK_S * montage.fps)
    pieces = [(a, min(montage.frames, a + chunk)) for a in range(0, montage.frames, chunk)]
    blocks = folder(out) / 'blocos'
    blocks.mkdir(parents=True, exist_ok=True)
    files, reused = [], 0
    for index, (a, b) in enumerate(pieces):
        if job.cancel:
            raise M.Cancelled()
        target = blocks / f'{key[:12]}_{index:04d}.mp4'
        files.append(target)
        if target.exists():
            reused += 1
            continue
        job.step = f'Renderizando o vídeo com legendas · bloco {index + 1} de {len(pieces)}'
        job.pct = .02 + .9 * index / len(pieces)
        job.progress = {'tipo': 'render', 'processadas': index, 'total': len(pieces), 'reutilizadas': reused, 'indeterminado': False}
        partial = target.with_suffix('.partial.mp4')
        try:
            M.run_proc(job, montage.command(a, b, ass_file, partial))
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
    job.step = 'Juntando os blocos com o áudio final'
    job.pct = .95
    listing = blocks / f'{key[:12]}_lista.txt'
    listing.write_text(''.join(f"file '{f.name}'\n" for f in files))
    from . import identidade_entrega as ID
    stem = re.sub(r'[\\/:*?"<>|]+', '-', ID.identity(T.load(out), out)['nome_sequencia']).strip() or 'VIDEO'
    target = folder(out) / f'{stem} - LEGENDADO.mp4'
    partial = target.with_suffix('.partial.mp4')
    try:
        M.run_proc(job, [M.FFMPEG, '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(listing), '-i', str(audio),
                         '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy', '-shortest', '-movflags', '+faststart', str(partial)])
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    duration = T.probe(target)['duration']
    expected = montage.frames / montage.fps
    if abs(duration - expected) > 1.0:
        raise ValueError(f'O vídeo saiu com {duration:.1f} s, mas a montagem tem {expected:.1f} s. Nada foi substituído; tente novamente.')
    result = {'arquivo': str(target.relative_to(out)), 'assinatura': key, 'duracao_s': round(duration, 2), 'blocos': len(pieces),
              'blocos_reaproveitados': reused, 'tempo_s': round(time.perf_counter() - started, 1)}
    with T.LOCK:
        state = load(out)
        state.update(estilo=style, final=result)
        T.write(path(out), state)
    # Blocos só servem para retomar um render interrompido; com o vídeo pronto, liberam espaço.
    for old in list(blocks.glob('*.mp4')) + [listing]:
        old.unlink(missing_ok=True)
    job.pct = 1
    job.step = 'Vídeo com legendas pronto'
    return result
