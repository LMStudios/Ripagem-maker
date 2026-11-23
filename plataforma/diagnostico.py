"""Diagnóstico sem segredos, gravação segura, acesso só local e recuperação ao abrir o app."""
import io
import os
import re
import sys
import threading
import uuid
from pathlib import Path

# Valores após rótulos de credencial e formatos conhecidos de chave (AssemblyAI, ElevenLabs, MiniMax/JWT, Google).
_PATTERNS = [
    (re.compile(r'(?i)((?:api[_-]?key|x-goog-api-key|xi-api-key|authorization|bearer|token|secret|senha|password|chave)["\'\s:=]+(?:bearer\s+)?)[^\s"\',;]{6,}'), r'\1[oculto]'),
    (re.compile(r'\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}(?:\.[A-Za-z0-9_\-]+)?'), '[oculto]'),
    (re.compile(r'\bAIza[0-9A-Za-z_\-]{20,}'), '[oculto]'),
    (re.compile(r'\bsk[_-][A-Za-z0-9_\-]{16,}'), '[oculto]'),
    (re.compile(r'(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])'), '[oculto]'),
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '[e-mail oculto]'),
]


def redact(text):
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class _Redacted(io.TextIOBase):
    def __init__(self, stream):
        self._stream = stream

    def write(self, text):
        return self._stream.write(redact(str(text)))

    def flush(self):
        return self._stream.flush()

    def fileno(self):
        return self._stream.fileno()

    @property
    def encoding(self):
        return getattr(self._stream, 'encoding', 'utf-8')

    def isatty(self):
        return False


def protect_streams():
    """Tudo que o motor escreve no log de diagnóstico passa pela ocultação de chaves e e-mails."""
    if sys.stdout is not None and not isinstance(sys.stdout, _Redacted):
        sys.stdout = _Redacted(sys.stdout)
    if sys.stderr is not None and not isinstance(sys.stderr, _Redacted):
        sys.stderr = _Redacted(sys.stderr)


def atomic_text(path, text, encoding='utf-8'):
    """Grava num temporário e troca de uma vez: um arquivo incompleto nunca substitui a versão válida."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with open(tmp, 'w', encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with open(tmp, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def local_request(headers, port):
    """Aceita só pedidos do próprio app: protege contra páginas da internet que tentem acionar o servidor local."""
    host = (headers.get('Host') or '').strip().lower()
    allowed = {f'127.0.0.1:{port}', f'localhost:{port}', f'[::1]:{port}'}
    if host and host not in allowed:
        return False
    if (headers.get('Sec-Fetch-Site') or '').lower() == 'cross-site':
        return False
    origin = (headers.get('Origin') or '').strip().lower()
    if origin and origin != 'null' and origin not in {'http://' + a for a in allowed}:
        return False
    return True


STARTUP = {'movimentos': [], 'tarefas_interrompidas': [], 'limpeza_automatica': None}


def startup():
    """Ao abrir: conclui ou desfaz mudanças de pasta interrompidas, registra tarefas interrompidas e roda a limpeza automática (se ligada)."""
    from . import ml_core as M
    from . import projetos as P
    try:
        STARTUP['movimentos'] = P.recover_moves()
    except Exception as e:  # noqa: BLE001
        print('Aviso: não foi possível conferir mudanças de pasta interrompidas:', type(e).__name__, flush=True)
    try:
        STARTUP['tarefas_interrompidas'] = M.restore_interrupted_jobs()
    except Exception as e:  # noqa: BLE001
        print('Aviso: não foi possível conferir tarefas interrompidas:', type(e).__name__, flush=True)

    def auto():
        from . import limpeza as L
        try:
            STARTUP['limpeza_automatica'] = L.auto_cleanup()
        except Exception as e:  # noqa: BLE001
            print('Aviso: limpeza automática não executada:', type(e).__name__, flush=True)
    timer = threading.Timer(30, auto)
    timer.daemon = True
    timer.start()
    return STARTUP
