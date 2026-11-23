"""Rotas das ferramentas avulsas, projetos, armazenamento e tratamento de áudio."""
import json
import re
import shutil
import uuid
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import armazenamento as S
from . import ml_core as M

AUDIO = {'.wav', '.mp3', '.m4a', '.aac', '.flac', '.ogg', '.opus', '.mp4', '.mov', '.webm'}
MAX_UPLOAD = 2 * 1024 ** 3

TOOLS = [
    {'id': 'transcricao', 'nome': 'Transcrição de áudio e vídeo', 'recebe': 'Um vídeo ou áudio (MP4, MOV, WAV, MP3…).',
     'entrega': 'Transcrição por speaker (TXT, SRT e JSON) e os trechos de cada pessoa.', 'salva': 'Pasta do projeto, em Fatiador.',
     'etapa': 1, 'reaproveita': False, 'custo': 'Usa a chave do AssemblyAI (pode consumir créditos).'},
    {'id': 'mencoes', 'nome': 'Identificação e edição de menções', 'recebe': 'Uma transcrição já feita.',
     'entrega': 'Lista das frases com o produto antigo, editável.', 'salva': 'trocas/plano.json no projeto.', 'etapa': 3, 'reaproveita': True,
     'custo': 'Local, sem custo.'},
    {'id': 'adaptacao', 'nome': 'Adaptação de produto, forma e modo de uso', 'recebe': 'As menções identificadas.',
     'entrega': 'Frases reescritas com o produto novo, forma e modo de uso confirmados.', 'salva': 'trocas/plano.json no projeto.', 'etapa': 3,
     'reaproveita': True, 'custo': 'Local; a sugestão pelo Gemini é opcional e pede autorização.'},
    {'id': 'falas', 'nome': 'Geração de falas por speaker', 'recebe': 'Frases aprovadas e a voz de cada speaker.',
     'entrega': 'Um áudio por frase, gerado e encaixado na duração original.', 'salva': 'trocas/gerados e trocas/encaixados no projeto.', 'etapa': 3,
     'reaproveita': True, 'custo': 'Usa ElevenLabs ou MiniMax (consome créditos). Áudios já gerados são reaproveitados.'},
    {'id': 'tratamento', 'nome': 'Tratamento de áudio', 'recebe': 'Áudios de um projeto ou arquivos avulsos.',
     'entrega': 'Cópia com silêncio das bordas aparado e ruído reduzido; o original fica intacto.', 'salva': 'trocas/tratados no projeto, ou Ferramentas/Tratamento de audio.',
     'avulsa': True, 'reaproveita': True, 'custo': 'Local, sem custo.'},
    {'id': 'separacao', 'nome': 'Separação de voz e trilha', 'recebe': 'Um áudio ou vídeo com voz e música juntas.',
     'entrega': 'Dois arquivos: só a voz e só a trilha.', 'salva': 'Ferramentas/Separacao de voz.', 'avulsa': True, 'reaproveita': False,
     'custo': 'Local, sem custo (precisa do componente Demucs).'},
    {'id': 'broll', 'nome': 'Caçar B-rolls', 'recebe': 'Uma busca ou link de vídeo.',
     'entrega': 'Clipes para assistir e baixar, com avisos de texto na tela e marca-d’água.',
     'salva': 'Ferramentas/Caçar B-rolls.', 'avulsa': True, 'reaproveita': False, 'custo': 'Sem consumo de créditos do app.'},
    {'id': 'takes', 'nome': 'Preparação dos takes', 'recebe': 'Um projeto com falas e a pasta de takes dos potes.',
     'entrega': 'Takes distribuídos em V2 cobrindo cada fala substituída.', 'salva': 'trocas/visuais no projeto (os takes originais não são copiados).',
     'etapa': 4, 'reaproveita': True, 'custo': 'Local, sem custo.'},
    {'id': 'premiere', 'nome': 'Exportação para o Premiere', 'recebe': 'Falas aprovadas e, se houver, os takes preparados.',
     'entrega': 'XML da sequência completa e manifesto JSON.', 'salva': 'trocas/ no projeto.', 'etapa': 6, 'reaproveita': True,
     'custo': 'Local, sem custo.'},
    {'id': 'srt', 'nome': 'Correção de legendas SRT', 'recebe': 'Um SRT e os nomes do produto antigo e novo.',
     'entrega': 'SRT corrigido e relatório das trocas.', 'salva': 'Pasta do projeto escolhido.', 'etapa': 7, 'reaproveita': True,
     'custo': 'Local, sem custo.'},
]


def _send(h, code, body):
    data = json.dumps(body, ensure_ascii=False).encode()
    h.send_response(code)
    h.send_header('Content-Type', 'application/json; charset=utf-8')
    h.send_header('Content-Length', str(len(data)))
    h.send_header('Cache-Control', 'no-store')
    h.end_headers()
    h.wfile.write(data)


def _body(h, limit=65536):
    n = int(h.headers.get('Content-Length', 0) or 0)
    if n > limit:
        raise ValueError('Solicitação grande demais.')
    return json.loads(h.rfile.read(n) or b'{}') if n else {}


def _busy():
    return any(j.status in ('na_fila', 'executando') for j in M.JOBS.values())


def separation_available():
    import importlib.util
    import sys
    return not getattr(sys, 'frozen', False) and importlib.util.find_spec('demucs') is not None


def catalog():
    from . import projetos as P
    tools = [dict(t) for t in TOOLS]
    for t in tools:
        if t['id'] == 'separacao':
            t['disponivel'] = separation_available()
            if not t['disponivel']:
                t['aviso'] = 'O componente de separação (Demucs) não está instalado nesta versão. Nada é enviado para fora do computador.'
    return {'ferramentas': tools, 'projetos': P.listing(False)[:30]}


def _upload(h, folder):
    name = Path(unquote(h.headers.get('X-Filename', 'audio.wav'))).name
    if Path(name).suffix.lower() not in AUDIO:
        raise ValueError('Envie um arquivo de áudio ou vídeo (WAV, MP3, M4A, MP4…).')
    size = int(h.headers.get('Content-Length', 0) or 0)
    if not 0 < size <= MAX_UPLOAD:
        raise ValueError('Arquivo vazio ou maior que 2 GB.')
    target = Path(folder) / name
    n = 2
    while target.exists():  # nunca sobrescreve um envio anterior com o mesmo nome
        target = Path(folder) / f'{Path(name).stem}_{n}{Path(name).suffix}'
        n += 1
    partial = target.with_name('.' + target.name + '.parcial')
    left = size
    with partial.open('wb') as f:
        while left > 0:
            chunk = h.rfile.read(min(1 << 20, left))
            if not chunk:
                raise ValueError('Upload incompleto. Envie o arquivo novamente.')
            f.write(chunk)
            left -= len(chunk)
    partial.replace(target)
    return target


def _tool_session(kind, token):
    """Pasta de uma sessão da ferramenta avulsa (criada no primeiro envio)."""
    if token:
        if not re.fullmatch(r'[0-9a-f]{12}', token):
            raise ValueError('Sessão inválida.')
        index = _sessions()
        if token not in index:
            raise ValueError('Sessão expirada. Envie os arquivos novamente.')
        return token, Path(index[token])
    folder = S.tool_folder(kind)
    token = uuid.uuid4().hex[:12]
    index = _sessions()
    index[token] = str(folder)
    _save_sessions(index)
    return token, folder


SESSIONS = M.WS / 'ferramentas_sessoes.json'


def _sessions():
    try:
        return json.loads(SESSIONS.read_text())
    except (OSError, ValueError):
        return {}


def _save_sessions(index):
    from . import projetos as P
    P._write_json(SESSIONS, dict(list(index.items())[-100:]))


def separate_job(job, source, folder):
    import subprocess
    import sys
    if not separation_available():
        raise ValueError('O componente de separação (Demucs) não está instalado nesta versão.')
    job.step = 'Separando voz e trilha (pode levar alguns minutos)'
    job.progress = {'tipo': 'separacao', 'fase': 'Separando voz e trilha', 'indeterminado': True}
    work = Path(folder) / '.demucs'
    M.run_proc(job, [sys.executable, '-m', 'demucs', '--two-stems=vocals', '-n', 'htdemucs', '-o', str(work), str(source)])
    stem = Path(source).stem
    produced = next(work.rglob(stem), None)
    if not produced:
        raise RuntimeError('A separação terminou sem gerar arquivos. O original foi preservado.')
    voice = Path(folder) / f'{stem}_VOZ.wav'
    music = Path(folder) / f'{stem}_TRILHA.wav'
    shutil.move(str(produced / 'vocals.wav'), voice)
    shutil.move(str(produced / 'no_vocals.wav'), music)
    shutil.rmtree(work, ignore_errors=True)
    job.pct = 1
    job.step = 'Separação concluída'
    return {'pasta': str(folder), 'relativo': S.tool_relative(folder), 'voz': voice.name, 'trilha': music.name}


def handle(h, method, legacy_jobs):
    from . import limpeza as L
    from . import projetos as P
    from . import tratamento_audio as TA
    p = urlparse(h.path)
    path, q = p.path, parse_qs(p.query)
    if not (path.startswith('/api/ferramentas') or path.startswith('/api/projetos') or path.startswith('/api/armazenamento')
            or path.startswith('/api/tratamento') or path.startswith('/ferramentas/arquivo/')):
        return False
    try:
        if method == 'GET' and path.startswith('/ferramentas/arquivo/'):
            from . import api as PLATAFORMA
            rel = unquote(path[len('/ferramentas/arquivo/'):])
            f = S.resolve('ferramentas', rel)
            if not any(f.is_relative_to(r) for r in S.roots('ferramentas')) or not f.is_file():
                _send(h, 404, {'erro': 'Arquivo não encontrado.'})
            else:
                PLATAFORMA._send_file(h, f, download='dl' in q)
            return True
        if method == 'GET' and path == '/api/ferramentas':
            result = catalog()
        elif method == 'POST' and path.startswith('/api/ferramentas/broll/'):
            from . import broll as BR
            action = path.rsplit('/', 1)[-1]
            body = _body(h)
            out = S.current('ferramentas') / 'Caçar B-rolls'
            args = {'out': str(out), 'frase': BR.LIBRARY_ROW, 'library': True}
            if action == 'broll-estado':
                result = BR.view(out, library=True)
                result['pasta'] = S.tool_relative(out)
            elif action == 'broll-buscar':
                result = M.submit('broll', 'Buscar B-rolls', BR.search_job, 'visual',
                                  dedupe_key=str(out), consulta=str(body.get('consulta') or ''), **args).to_dict()
            elif action == 'broll-link':
                url = str(body.get('url') or '')
                BR.source_of(url)
                result = M.submit('broll', 'Adicionar B-roll pelo link', BR.link_job, 'visual',
                                  dedupe_key=str(out) + ':' + url, url=url, **args).to_dict()
            elif action == 'broll-links':
                urls = body.get('urls')
                if not isinstance(urls, list):
                    raise ValueError('Lista de vídeos inválida.')
                result = M.submit('broll', 'Baixar B-rolls coletados', BR.links_job, 'visual',
                                  dedupe_key=str(out), urls=urls[:20], consulta=str(body.get('consulta') or '')[:120],
                                  fonte=str(body.get('fonte') or '')[:20], **args).to_dict()
            else:
                raise ValueError('Ação de B-roll inválida.')
        elif method == 'GET' and path == '/api/projetos':
            result = {'projetos': P.listing(False), 'pasta_novos': str(S.current('fatiador'))}
        elif method == 'POST' and path == '/api/projetos/favorito':
            b = _body(h)
            result = P.set_favorite(b.get('pasta', ''), b.get('favorito'))
        elif method == 'POST' and path == '/api/projetos/local':
            b = _body(h)
            out = P.find(b.get('pasta', ''))
            result = {'pasta': out.name, 'caminho': str(out.resolve()), 'pasta_novos': str(S.current('fatiador')), 'xmls_a_refazer': P.stale_xmls(out),
                      'em_uso': P.summary(out)['em_uso']}
        elif method == 'POST' and path == '/api/projetos/abrir-pasta':
            from .sistema import abrir
            out = P.find(_body(h).get('pasta', ''))
            abrir(out)
            result = {'ok': True, 'caminho': str(out.resolve())}
        elif method == 'POST' and path == '/api/projetos/verificar-destino':
            b = _body(h)
            result = P.check_destination(b.get('pasta', ''), b.get('destino', ''))
        elif method == 'POST' and path == '/api/projetos/mover':
            b = _body(h)
            with S.LOCK:
                if S.MAINTENANCE:
                    raise ValueError('A limpeza está em andamento. Mova o projeto quando ela terminar.')
                P.check_destination(b.get('pasta', ''), b.get('destino', ''))
                result = M.submit('mover_projeto', 'Mover projeto', P.move_job, 'render', dedupe_key='mover:' + b.get('pasta', ''),
                                  name=b.get('pasta', ''), destination=b.get('destino', ''), out=str(P.find(b.get('pasta', '')))).to_dict()
        elif method == 'GET' and path == '/api/armazenamento':
            result = L.storage_status()
        elif method == 'POST' and path == '/api/armazenamento/regras':
            result = S.save_cleanup_settings(_body(h))
        elif method == 'POST' and path in ('/api/armazenamento/medir', '/api/armazenamento/conferir', '/api/armazenamento/limpar'):
            b = _body(h)
            with S.LOCK:
                if L.active(legacy=legacy_jobs()) and path != '/api/armazenamento/medir':
                    raise ValueError('Aguarde as tarefas em andamento antes de limpar. A medição pode ser feita a qualquer momento.')
                if path == '/api/armazenamento/medir':
                    result = M.submit('armazenamento', 'Medir espaço ocupado', L.usage, 'visual', dedupe_key='medir').to_dict()
                else:
                    def clean(job):
                        work = (lambda: L.build_plan(job, b)) if path.endswith('conferir') else (lambda: L.run_plan(job, b.get('token'), b.get('itens')))
                        return L.maintenance(job, work, legacy_jobs)
                    result = M.submit('limpeza', 'Conferir o que pode ser limpo' if path.endswith('conferir') else 'Limpar materiais selecionados',
                                      clean, 'render').to_dict()
        elif method == 'GET' and path == '/api/tratamento/padrao':
            result = S.treatment_settings()
        elif method == 'POST' and path == '/api/tratamento/padrao':
            result = S.save_treatment_settings(_body(h))
        elif method == 'POST' and path in ('/api/tratamento/projeto', '/api/tratamento/desfazer'):
            b = _body(h)
            out = P.find(b.get('pasta', ''))
            if path.endswith('desfazer'):
                result = M.submit('tratamento_audio', 'Desfazer tratamento do áudio', TA.undo_row, 'render', dedupe_key='desfazer:' + str(out) + b.get('id', ''),
                                  out=str(out), rid=b.get('id', '')).to_dict()
            else:
                ids = [str(i) for i in (b.get('ids') or [])][:500]
                if not ids:
                    raise ValueError('Escolha pelo menos uma fala com áudio.')
                options = TA.normalize(b.get('opcoes') or S.treatment_settings())
                result = M.submit('tratamento_audio', 'Tratar áudios gerados', TA.treat_rows, 'render', dedupe_key='tratar:' + str(out),
                                  out=str(out), ids=ids, options=options).to_dict()
        elif method == 'POST' and path in ('/api/ferramentas/tratamento/enviar', '/api/ferramentas/separacao/enviar'):
            kind = 'Tratamento de audio' if 'tratamento' in path else 'Separacao de voz'
            token, folder = _tool_session(kind, h.headers.get('X-Sessao', ''))
            target = _upload(h, folder)
            result = {'sessao': token, 'arquivo': target.name, 'pasta': str(folder)}
        elif method == 'POST' and path == '/api/ferramentas/tratamento/processar':
            b = _body(h)
            token, folder = _tool_session('Tratamento de audio', b.get('sessao', ''))
            names = [Path(n).name for n in b.get('arquivos') or [] if (folder / Path(n).name).is_file()]
            if not names:
                raise ValueError('Envie pelo menos um arquivo antes de tratar.')
            result = M.submit('tratamento_avulso', 'Tratar áudios avulsos', TA.standalone_job, 'render', dedupe_key='avulso:' + token,
                              files=names, options=TA.normalize(b.get('opcoes') or {}), folder=str(folder)).to_dict()
        elif method == 'POST' and path == '/api/ferramentas/separacao/processar':
            b = _body(h)
            token, folder = _tool_session('Separacao de voz', b.get('sessao', ''))
            name = Path(str(b.get('arquivo', ''))).name
            if not (folder / name).is_file():
                raise ValueError('Envie o arquivo antes de separar.')
            result = M.submit('separacao', 'Separar voz e trilha', separate_job, 'render', dedupe_key='separar:' + token,
                              source=str(folder / name), folder=str(folder)).to_dict()
        elif method == 'POST' and path == '/api/ferramentas/abrir':
            from .sistema import abrir
            target = Path(str(_body(h).get('caminho', ''))).resolve()
            allowed = S.roots('ferramentas') + S.roots('fatiador') + S.roots('montagens')
            if not any(target.is_relative_to(r) for r in allowed) or not target.exists():
                raise ValueError('Pasta ou arquivo fora das pastas do app.')
            abrir(target, revelar=target.is_file())
            result = {'ok': True, 'caminho': str(target)}
        else:
            _send(h, 404, {'erro': 'rota inválida'})
            return True
        _send(h, 200, result)
    except (ValueError, KeyError, TypeError) as e:
        _send(h, 400, {'erro': str(e)})
    except OSError as e:
        _send(h, 400, {'erro': M.friendly_error(e)})
    except Exception as e:  # noqa: BLE001
        _send(h, 500, {'erro': M.friendly_error(e)})
    return True
