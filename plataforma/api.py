"""Rotas HTTP da plataforma (painel + Microlead/Body). Ligadas ao servidor do app.py."""
import json
import mimetypes
import os
import platform
import re
import subprocess
import uuid
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import ml_core as M
from . import demandas as D
from . import armazenamento as STORAGE
from . import validacao as V

from .atualizacoes import version as installed_version
RUNTIME_VERSION=installed_version()
STATIC = Path(__file__).resolve().parent / "static"
UPLOAD_TMP = M.WS / ".upload"
UPLOAD_TMP.mkdir(parents=True, exist_ok=True)


def _send(h, code, body, ctype="application/json; charset=utf-8", extra=None):
    if isinstance(body, (dict, list)):
        body = json.dumps(body, ensure_ascii=False).encode()
    elif isinstance(body, str):
        body = body.encode()
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store")
    for k, v in (extra or {}).items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(body)


_STATIC_CACHE = {}


def _send_static(h, f):
    """Arquivos da interface com ETag: o navegador revalida e recebe 304 sem baixar de novo.
    O conteúdo fica em memória enquanto o arquivo não muda (tamanho e data conferidos a cada pedido)."""
    st = f.stat()
    key = str(f)
    tag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
    cached = _STATIC_CACHE.get(key)
    if not cached or cached[0] != tag:
        cached = (tag, f.read_bytes())
        _STATIC_CACHE[key] = cached
    ctype = mimetypes.guess_type(f.name)[0] or "text/plain"
    if ctype.startswith("text/") or ctype in ("application/javascript", "application/json", "image/svg+xml"):
        ctype += "; charset=utf-8"
    headers = {"ETag": tag, "Cache-Control": "no-cache"}
    if tag in (h.headers.get("If-None-Match") or ""):
        h.send_response(304)
        for k, v in headers.items():
            h.send_header(k, v)
        h.end_headers()
        return
    h.send_response(200)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(cached[1])))
    for k, v in headers.items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(cached[1])


def _body(h):
    n = int(h.headers.get("Content-Length", 0) or 0)
    return json.loads(h.rfile.read(n) or b"{}") if n else {}


def _send_file(h, f, download=False):
    """Envio com suporte a Range (o player de vídeo precisa disso para avançar/voltar)."""
    ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    with open(f, "rb") as fp:
        size = os.fstat(fp.fileno()).st_size
        start, end = 0, size - 1
        range_header = h.headers.get("Range", "").strip()
        # Serve um único intervalo. Pedidos que não reconhecemos recebem o arquivo inteiro.
        interval = re.fullmatch(r"bytes=([0-9]{0,20})-([0-9]{0,20})", range_header, re.IGNORECASE)
        partial = bool(interval and any(interval.groups()))
        if partial:
            first, last = interval.groups()
            if first:
                start = int(first)
                if last:
                    end = min(end, int(last))
            else:
                suffix = int(last)
                start = max(0, size - suffix)
            if start > end:
                h.send_response(416)
                h.send_header("Content-Range", f"bytes */{size}")
                h.send_header("Content-Length", "0")
                h.end_headers()
                return
        length = end - start + 1
        h.send_response(206 if partial else 200)
        h.send_header("Content-Type", ctype)
        h.send_header("Accept-Ranges", "bytes")
        h.send_header("Content-Length", str(length))
        if partial:
            h.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            h.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(f.name)}")
        h.end_headers()
        fp.seek(start)
        try:
            while length > 0:
                chunk = fp.read(min(length, 1 << 20))
                if not chunk:
                    break
                h.wfile.write(chunk)
                length -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def _system():
    try:
        import mlx_whisper  # noqa: F401
        mlx = True
    except Exception:
        mlx = False
    try:
        import faster_whisper  # noqa: F401
        fw = True
    except Exception:
        fw = False
    ff = subprocess.run([M.FFMPEG, "-version"], capture_output=True, text=True).stdout.split("\n")[0]
    cache = Path.home() / ".cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo"
    return {"ffmpeg": ff, "mlx_whisper": mlx, "modelo_mlx_baixado": cache.exists(), "faster_whisper": fw,
            "maquina": f"{platform.machine()} · {platform.mac_ver()[0] or platform.system()}",
            "motor_padrao": "mlx" if mlx and cache.exists() else ("fw" if fw else None),
            "tudo_local": True}


def handle(h, method):
    p = urlparse(h.path)
    path, q = p.path, parse_qs(p.query)
    try:
        if path in ('/api/notificacoes', '/api/notificacoes/teste') and method in ('GET', 'POST'):
            from . import notificacoes
            if not 0 <= int(h.headers.get('Content-Length', 0) or 0) <= 1024:
                raise ValueError('Configuração muito grande.')
            if path.endswith('/teste') and method == 'POST':
                _send(h, 200, notificacoes.send_test())
            elif path == '/api/notificacoes':
                data = _body(h) if method == 'POST' else {}
                if method == 'POST' and (not isinstance(data, dict) or type(data.get('ativo')) is not bool):
                    raise ValueError('Escolha ligar ou desligar as notificações.')
                _send(h, 200, notificacoes.settings(data.get('ativo')))
            else:
                _send(h, 405, {'erro': 'Use o botão Enviar aviso de teste.'})
            return True
        if path == '/api/studio/preferencias' and method in ('GET', 'POST'):
            from . import studio
            if not 0 <= int(h.headers.get('Content-Length', 0) or 0) <= 4096:
                raise ValueError('Configuração muito grande.')
            _send(h, 200, studio.preferences(_body(h) if method == 'POST' else None))
            return True
        # --------------------------------------------------- páginas
        if method == "GET" and path in ("/", "/painel"):
            _send(h, 200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            return True
        if method == "GET" and path.startswith("/static/"):
            f = (STATIC / unquote(path[len("/static/"):])).resolve()
            if f.is_relative_to(STATIC) and f.is_file():
                _send_static(h, f)
            else:
                _send(h, 404, {"erro": "não encontrado"})
            return True
        # --------------------------------------------------- mídia
        if method == "GET" and path.startswith("/media/v/"):
            vid = path.split("/")[3]
            m = M.read_meta(vid)
            if not m:
                _send(h, 404, {"erro": "vídeo não encontrado"})
            else:
                _send_file(h, M.vdir(vid) / m["arquivo"])
            return True
        if method == "GET" and path.startswith("/media/out/"):
            f = STORAGE.resolve("montagens",unquote(path[len("/media/out/"):]),M.OUT_DIR)
            if not any(f.is_relative_to(root) for root in STORAGE.roots("montagens")+[M.OUT_DIR.resolve()]) or not f.is_file():
                _send(h, 404, {"erro": "arquivo não encontrado"})
            else:
                _send_file(h, f, download="dl" in q)
            return True
        if not path.startswith("/api/"):
            return False

        # --------------------------------------------------- API
        if path == "/api/validacao" and method == "POST":
            _send(h, 200, V.submit(_body(h)).to_dict())
        elif path == "/api/validacao/upload" and method == "POST":
            vid = uuid.uuid4().hex[:10]
            directory = M.vdir(vid)
            directory.mkdir()
            name = Path(unquote(h.headers.get("X-Filename", "video.mp4"))).name
            dest = directory / ("original" + (Path(name).suffix or ".mp4"))
            left = int(h.headers.get("Content-Length", 0))
            try:
                with dest.open("wb") as fp:
                    while left > 0:
                        chunk = h.rfile.read(min(1 << 20, left))
                        if not chunk: raise ValueError("Upload incompleto.")
                        fp.write(chunk)
                        left -= len(chunk)
                info = M.probe(dest)
                M.write_meta(vid, id=vid, nome=name, arquivo=dest.name, criado=M.now(), status="importado", probe=info, confirmado={})
                options = {"video": vid, "termos": unquote(h.headers.get("X-Termos", "")), "idioma": h.headers.get("X-Idioma", "auto"), "motor": h.headers.get("X-Motor", "mlx")}
                _send(h, 200, V.submit(options).to_dict())
            except Exception:
                M.shutil.rmtree(directory, ignore_errors=True)
                raise
        elif path == "/api/demanda/catalogo" and method == "GET":
            _send(h, 200, {"copy": D.COPY, "editores": D.EDITORES})
        elif path == "/api/demanda/interpretar" and method == "POST":
            _send(h, 200, D.parse(_body(h).get("texto", "")))
        elif path == "/api/demanda/nome" and method == "POST":
            _send(h, 200, {"nome": D.name(_body(h))})
        elif path == "/api/demanda/executar" and method == "POST":
            _send(h, 200, D.submit(_body(h)).to_dict())
        elif path == "/api/recursos" and method == "GET":
            _send(h,200,{"forma_produto":True,"hls":True,"falas_leves":True,"gemini_formas":2,"via_uso":True,"versao_em_execucao":RUNTIME_VERSION})
        elif path == "/api/sistema":
            _send(h, 200, _system())
        elif path == "/api/ml/videos" and method == "GET":
            _send(h, 200, M.list_videos())
        elif path == "/api/ml/upload" and method == "POST":
            name = unquote(h.headers.get("X-Filename", "video.mp4"))
            from .uploads import receive
            tmp = UPLOAD_TMP / f"{uuid.uuid4().hex}{Path(name).suffix}"
            try:
                receive(h.rfile, h.headers.get("Content-Length", 0), tmp)
                meta = M.add_video(tmp, name, h.headers.get("X-Motor", "mlx"), h.headers.get("X-Idioma", "auto"))
            finally:
                tmp.unlink(missing_ok=True)
            _send(h, 200, meta)
        elif re.fullmatch(r"/api/ml/video/\w+", path) and method == "GET":
            vid = path.split("/")[-1]
            m = M.read_meta(vid)
            if not m:
                _send(h, 404, {"erro": "vídeo não encontrado"})
            elif m.get("status") != "pronto":
                _send(h, 200, {"meta": m, "pronto": False})
            else:
                _send(h, 200, M.view(vid) | {"pronto": True})
        elif re.fullmatch(r"/api/ml/video/\w+/(\w+)", path) and method in ("POST", "GET"):
            vid, act = path.split("/")[-2], path.split("/")[-1]
            if act == "excluir":
                M.delete_video(vid)
                _send(h, 200, {"ok": True})
            elif act == "reanalisar":
                b = _body(h)
                _send(h, 200, M.reanalyze(vid, b.get("motor"), b.get("idioma")).to_dict())
            elif act == "confirmar":
                _send(h, 200, M.confirm_cut(vid, **_body(h)))
            elif act == "snap":
                _send(h, 200, M.snap(vid, float(q["t"][0]), q.get("role", ["lead"])[0]))
            else:
                _send(h, 404, {"erro": "ação inválida"})
        elif path == "/api/ml/regras":
            if method == "POST":
                _send(h, 200, M.save_rules(_body(h)))
            else:
                _send(h, 200, M.load_rules())
        elif path == "/api/ml/regras/padrao" and method == "POST":
            _send(h, 200, M.save_rules(dict(M.DEFAULT_RULES)))
        elif path == "/api/ml/montar" and method == "POST":
            _send(h, 200, M.submit_render(_body(h)).to_dict())
        elif path == "/api/ml/jobs":
            _send(h, 200, [j.to_dict() for j in sorted(M.JOBS.values(), key=lambda j: -j.created)][:40])
        elif re.fullmatch(r"/api/ml/job/\w+", path):
            j = M.JOBS.get(path.split("/")[-1])
            _send(h, 200 if j else 404, j.to_dict() if j else {"erro": "tarefa não encontrada"})
        elif re.fullmatch(r"/api/ml/job/\w+/cancelar", path) and method == "POST":
            _send(h, 200, {"ok": M.cancel_job(path.split("/")[-2])})
        elif path == "/api/ml/lote" and method == "POST":
            b = _body(h)
            _send(h, 200, M.create_batch(b["pares"], b.get("opcoes", {}), b.get("pular_incertos", True)))
        elif re.fullmatch(r"/api/ml/lote/\w+", path):
            bid = path.split("/")[-1]
            _send(h, 200 if bid in M.BATCHES else 404, M.batch_view(bid) if bid in M.BATCHES else {"erro": "lote não encontrado"})
        elif path == "/api/ml/abrir" and method == "POST":
            alvo = _body(h).get("arquivo")
            f = STORAGE.resolve("montagens",alvo,M.OUT_DIR) if alvo else M.OUT_DIR
            if not any(f.is_relative_to(root) for root in STORAGE.roots("montagens")+[M.OUT_DIR.resolve()]) or not f.exists():raise ValueError('Pasta ou arquivo não encontrado: '+str(f))
            __import__("plataforma.sistema",fromlist=["abrir"]).abrir(f,revelar=True)
            _send(h, 200, {"ok": True,"arquivo":str(f)})
        else:
            _send(h, 404, {"erro": "rota inválida"})
    except ValueError as e:
        _send(h, 400, {"erro": str(e)})
    except Exception as e:  # noqa: BLE001
        _send(h, 500, {"erro": str(e)})
    return True
