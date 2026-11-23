"""
Microlead + Body — núcleo (sem IA, sem API, tudo local).

Análise de vídeo  : ffprobe -> áudio 16 kHz -> silencedetect -> Whisper local (processo separado) -> frases/pausas
Cortes            : regras determinísticas (pausas, pontuação, expressões configuráveis, faixa de duração).
                    Nunca afirma entender a copy: quando as regras não decidem, devolve opções para confirmar.
Montagem          : ffmpeg real. Copia os fluxos quando é tecnicamente seguro; senão recodifica num passe só,
                    normalizando fps/resolução/áudio para manter o sincronismo.
Fila              : 1 transcrição e 1 render por vez, com progresso, cancelamento e refazer.
"""
import json
import math
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from .progresso import phase
from . import armazenamento as STORAGE, notificacoes

BASE = Path(__file__).resolve().parent
WS = BASE / "workspace"
VID_DIR = STORAGE.current("videos")
OUT_DIR = STORAGE.current("montagens")
PRESETS = WS / "regras.json"
for d in (VID_DIR, OUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
PY = sys.executable

DEFAULT_RULES = {
    "lead_min_s": 6,
    "lead_max_s": 120,
    "pausa_min_ms": 250,          # pausa considerada limite natural
    "pausa_forte_ms": 900,        # pausa que, sozinha, já separa frases
    "silencio_db": -35,           # limiar do silencedetect
    "folga_fim_lead_ms": 120,     # quanto deixar depois da última palavra da microlead
    "folga_inicio_body_ms": 150,  # quanto deixar antes da primeira palavra do body
    "conf_pontos": 6,             # pontuação mínima para considerar confiável
    "conf_margem": 2,             # vantagem mínima sobre a 2ª opção
    "fim_lead": ["watch this video", "keep watching", "watch until the end", "stay with me", "don't skip",
                 "in this video", "in this short video", "i'll show you", "i'm going to show you",
                 "let me show you", "here's how", "here is how", "make sure you watch", "until the end",
                 "assista até o final", "neste vídeo", "vou te mostrar", "fique até o final", "continue assistindo"],
    "transicao_forte": ["my name is", "hi, i'm", "i'm doctor", "i am doctor", "let me explain", "let me start",
                        "let me tell you", "here's the thing", "but first", "the first thing", "it all started",
                        "a few years ago", "meu nome é", "deixa eu te explicar", "tudo começou", "olá, eu sou"],
    "transicao_fraca": ["now", "so", "look", "listen", "agora", "então", "olha"],
    "ganchos": ["attention", "warning", "if you", "did you know", "breaking", "stop", "imagine", "what if",
                "atenção", "se você", "você sabia", "imagine", "pare"],
}

ABBR = {"dr.", "mr.", "mrs.", "ms.", "vs.", "st.", "jr.", "sr.", "u.s.", "no.", "etc."}


# ======================================================================= utilidades
def now():
    return time.time()


def slug(t, n=40):
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", t)[:n].strip("_") or "video"


def norm(t):
    return re.sub(r"[^\w' ]+", " ", t.lower()).replace("  ", " ").strip()


def fmt_t(s):
    s = max(0.0, s)
    return f"{int(s // 60):02d}:{s % 60:05.2f}"


def load_rules():
    r = dict(DEFAULT_RULES)
    if PRESETS.exists():
        try:
            r.update(json.loads(PRESETS.read_text()).get("atual", {}))
        except Exception:
            pass
    return r


def save_rules(rules):
    data = {}
    if PRESETS.exists():
        try:
            data = json.loads(PRESETS.read_text())
        except Exception:
            data = {}
    clean = {k: rules[k] for k in DEFAULT_RULES if k in rules}
    data["atual"] = clean
    PRESETS.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return load_rules()


# ======================================================================= jobs / fila
class Job:
    def __init__(self, kind, title, fn, **params):
        self.id = uuid.uuid4().hex[:10]
        self.kind, self.title, self.fn, self.params = kind, title, fn, params
        self.status, self.pct, self.step, self.error = "na_fila", 0.0, "Aguardando na fila", None
        self.result, self.proc, self.cancel = None, None, False
        self.created, self.started, self.finished = now(), None, None
        self.log = []
        self.progress = None
        self.error_action = None
        self.context = ""

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "title": self.title, "status": self.status,
                "pct": round(self.pct, 3), "progresso": getattr(self, "progress", None), "contexto": getattr(self, "context", ""), "step": self.step, "error": self.error, "acao_erro": self.error_action, "result": self.result,
                "params": {k: v for k, v in self.params.items() if k != "spec"} | (
                    {"spec": self.params["spec"]} if "spec" in self.params else {}),
                "created": self.created, "started": self.started, "finished": self.finished,
                "log": self.log[-8:]}


JOBS = {}
# "visual": leitura de quadros não espera nem trava renders e amostras de voz.
QUEUES = {"asr": queue.Queue(), "render": queue.Queue(), "visual": queue.Queue()}
HISTORY = WS / "tarefas_concluidas.json"
HISTORY_LOCK = threading.Lock()


def save_finished_jobs():
    with HISTORY_LOCK:
        rows = [j.to_dict() for j in list(JOBS.values()) if j.status in ("concluido", "erro", "cancelado")]
        tmp = HISTORY.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows[-80:], ensure_ascii=False, indent=2))
        tmp.replace(HISTORY)


def restore_finished_jobs():
    if not HISTORY.exists():
        return
    try:
        rows = json.loads(HISTORY.read_text())
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("status") not in ("concluido", "erro", "cancelado"):
                continue
            job = Job(row["kind"], row["title"], None, **row.get("params", {}))
            for key in ("id", "status", "pct", "step", "error", "result", "created", "started", "finished", "log"):
                if key in row:
                    setattr(job, key, row[key])
            job.error_action = row.get("acao_erro")
            JOBS[job.id] = job
    except (OSError, ValueError, KeyError, TypeError):
        pass


restore_finished_jobs()

ACTIVE = WS / "tarefas_ativas.json"


def save_active_jobs():
    """Registro das tarefas em curso: se o app fechar de repente, elas aparecem como interrompidas ao reabrir."""
    rows = [{"id": j.id, "kind": j.kind, "title": j.title, "params": {k: v for k, v in j.params.items() if k != "spec" and isinstance(v, (str, int, float, bool, list))},
             "created": j.created, "step": j.step} for j in list(JOBS.values()) if j.status in ("na_fila", "executando")]
    with HISTORY_LOCK:
        tmp = ACTIVE.with_name(ACTIVE.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
            tmp.replace(ACTIVE)
        finally:
            tmp.unlink(missing_ok=True)


def restore_interrupted_jobs():
    """Tarefas que estavam em curso quando o app fechou: viram 'erro' com orientação; os arquivos já salvos ficam no projeto."""
    try:
        rows = json.loads(ACTIVE.read_text())
    except (OSError, ValueError):
        return []
    restored = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get("id") in JOBS:
            continue
        job = Job(row.get("kind", "tarefa"), row.get("title", "Tarefa"), None, **(row.get("params") or {}))
        job.id, job.created, job.status, job.finished = row["id"], row.get("created", now()), "erro", now()
        job.step = "Interrompida"
        job.error = "O aplicativo foi fechado durante esta tarefa (última fase: " + str(row.get("step", "")) + "). Os arquivos já salvos foram preservados; inicie a tarefa novamente."
        JOBS[job.id] = job
        restored.append({"id": job.id, "titulo": job.title, "pasta": (row.get("params") or {}).get("out", "")})
    try:
        save_finished_jobs()
        save_active_jobs()
    except OSError:
        pass
    return restored


class Cancelled(Exception):
    pass


def _worker(qname):
    q = QUEUES[qname]
    while True:
        job = q.get()
        if job.cancel:
            job.status, job.step, job.finished = "cancelado", "Cancelado antes de começar", now()
            try:save_finished_jobs()
            except OSError:pass
            q.task_done();continue
        job.status, job.started = "executando", now()
        try:
            job.result = job.fn(job, **job.params)
            job.status, job.pct = "concluido", 1.0
            if job.step.startswith(("Aguardando", "Transcrevendo", "Renderizando")):
                job.step = "Concluído"
        except Cancelled:
            job.status, job.step = "cancelado", "Cancelado"
        except Exception as e:  # noqa: BLE001
            job.status, job.error = "erro", friendly_error(e, job)
            job.step = "Erro"
        finally:
            job.finished, job.proc = now(), None
            q.task_done()
            notificacoes.queued_job(job)
            try:
                from . import equipe_auth, relatorio_ripagem
                if equipe_auth.configured():
                    elapsed = job.finished - job.started
                    options = job.params.get('options') or {}
                    regenerate = isinstance(options, dict) and options.get('regenerar') is True
                    relatorio_ripagem.record_operation(job.params.get('out'), job.id, job.kind, job.status, elapsed,
                                                       inicio=job.started, repeticao=regenerate)
            except (ValueError, OSError, TypeError):
                pass
            try:
                save_finished_jobs()
                save_active_jobs()
            except OSError:
                pass


for _q in QUEUES:
    threading.Thread(target=_worker, args=(_q,), daemon=True).start()


_AAC = None


def aac_args(target="x.m4a", bitrate="192k"):
    """Codificador de áudio da saída: WAV sem compressão; AAC pelo codificador do macOS quando existe (2× mais rápido), senão o padrão."""
    global _AAC
    if str(target).lower().endswith(".wav"):
        return ["-c:a", "pcm_s16le"]
    if _AAC is None:
        try:
            listing = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            _AAC = "aac_at" if re.search(r"\baac_at\b", listing) else "aac"
        except (OSError, subprocess.SubprocessError):
            _AAC = "aac"
    return ["-c:a", _AAC, "-b:a", bitrate]


def friendly_error(error, job=None):
    """Mensagens escritas para o usuário (ValueError/RuntimeError) passam; o resto vira texto claro, com o detalhe no diagnóstico."""
    if isinstance(error, (ValueError, RuntimeError)):
        return str(error)
    if job is not None and hasattr(job, "log"):
        import traceback
        job.log.extend(traceback.format_exception(error)[-6:])
    if isinstance(error, OSError):
        reason = error.strerror or str(error)
        return f"Não foi possível ler ou gravar um arquivo ({reason}). Confira o espaço em disco e se a pasta ainda existe; seus arquivos foram preservados."
    return f"Erro inesperado nesta tarefa ({type(error).__name__}). Seus arquivos foram preservados; tente novamente."


def submit(kind, title, fn, qname, dedupe_key=None, **params):
    with STORAGE.LOCK:
        if STORAGE.MAINTENANCE and kind!='limpeza':raise ValueError('A limpeza está em andamento. Aguarde antes de iniciar outro trabalho.')
        for existing in list(JOBS.values()):
            if existing.status not in ('na_fila','executando') or existing.cancel or existing.kind!=kind:continue
            same=(getattr(existing,'dedupe_key',None)==dedupe_key) if dedupe_key is not None else (existing.fn is fn and existing.params==params)
            if same:return existing
        job = Job(kind, title, fn, **params)
        job.dedupe_key=dedupe_key
        JOBS[job.id] = job
        QUEUES[qname].put(job)
        try:save_active_jobs()
        except OSError:pass
        return job


def cancel_job(jid):
    job = JOBS.get(jid)
    if not job:
        return False
    job.cancel = True
    if job.proc and job.proc.poll() is None:
        job.proc.kill()
    if job.status == "na_fila":
        job.status, job.step = "cancelado", "Cancelado"
    return True


def process_error(stderr, code):
    lines=[line.strip() for line in stderr.splitlines() if line.strip()]
    missing=next((re.search(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]",line) for line in lines if 'ModuleNotFoundError:' in line),None)
    if missing:
        return 'A instalação do motor de transcrição está incompleta: falta o módulo '+missing.group(1)+'. Atualize o aplicativo. Seus arquivos foram preservados.'
    details=[line for line in lines if not re.match(r'\[PYI-\d+:(?:ERROR|WARNING)\]',line)]
    return details[-1] if details else f'O processo de mídia encerrou com código {code}. Confira o diagnóstico do aplicativo.'


def run_proc(job, cmd, on_line=None):
    """Drena os dois pipes para o stderr não bloquear a transcrição."""
    from collections import deque
    errors=deque(maxlen=80)
    proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    job.proc=proc
    def drain():
        for line in proc.stderr:errors.append(line[-4000:])
    reader=threading.Thread(target=drain,daemon=True);reader.start()
    try:
        for line in proc.stdout:
            if job.cancel:
                proc.kill()
                raise Cancelled()
            if on_line:on_line(line.rstrip("\n"))
        code=proc.wait();reader.join()
        if job.cancel:raise Cancelled()
        err=''.join(errors)
        if code!=0:
            if hasattr(job,'log'):job.log.extend(err.splitlines()[-16:])
            raise RuntimeError(process_error(err,code))
        return err
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        reader.join(timeout=2)
        proc.stdout.close();proc.stderr.close()
        job.proc=None


# ======================================================================= vídeos (biblioteca)
def vdir(vid):
    return STORAGE.resolve("videos",vid,fallback=VID_DIR)


def read_meta(vid):
    f = vdir(vid) / "meta.json"
    return json.loads(f.read_text()) if f.exists() else None


def write_meta(vid, **kw):
    m = read_meta(vid) or {}
    m.update(kw)
    (vdir(vid) / "meta.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
    return m


def list_videos():
    out = []
    directories={d.name:d for root in reversed(STORAGE.roots("videos")) if root.exists() for d in root.iterdir() if d.is_dir()}
    for d in sorted(directories.values(), key=lambda p: p.stat().st_mtime):
        m = read_meta(d.name)
        if not m:
            continue
        job = JOBS.get(m.get("job"))
        if job and job.status in ("na_fila", "executando"):
            m["status"], m["pct"], m["step"] = job.status, job.pct, job.step
        elif job and job.status in ("erro", "cancelado") and m.get("status") != "pronto":
            m["status"], m["step"], m["error"] = job.status, job.step, job.error
        out.append(m)
    return out


def probe(path):
    from .media_cache import metadata
    d = metadata(path,FFPROBE)
    v = next((s for s in d["streams"] if s["codec_type"] == "video" and s.get("disposition", {}).get("attached_pic") != 1), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    if not v:
        raise RuntimeError("O arquivo não tem trilha de vídeo.")

    def rate(x):
        try:
            n, dd = x.split("/")
            return float(n) / float(dd) if float(dd) else 0.0
        except Exception:
            return 0.0
    fps = rate(v.get("avg_frame_rate", "0/0")) or rate(v.get("r_frame_rate", "0/0"))
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    rot = rot or int(v.get("tags", {}).get("rotate", 0) or 0)
    w, h = int(v["width"]), int(v["height"])
    if abs(rot) in (90, 270):
        w, h = h, w
    return {"duracao": float(d["format"].get("duration") or v.get("duration") or 0),
            "largura": w, "altura": h, "fps": round(fps, 3), "vcodec": v.get("codec_name"),
            "pix_fmt": v.get("pix_fmt"), "perfil": v.get("profile"), "nivel": v.get("level"),
            "tem_audio": a is not None, "acodec": a and a.get("codec_name"),
            "sample_rate": a and int(a.get("sample_rate", 0)), "canais": a and a.get("channels"),
            "bitrate": int(d["format"].get("bit_rate") or 0), "rotacao": rot,
            "tamanho_mb": round(Path(path).stat().st_size / 1048576, 1)}


def detect_silences(wav, db, min_d=0.2):
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", str(wav), "-af",
                        f"silencedetect=noise={db}dB:d={min_d}", "-f", "null", "-"], capture_output=True, text=True)
    sil, start = [], None
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            sil.append({"s": round(start, 3), "e": round(float(m.group(1)), 3)})
            start = None
    return sil


def chunk_cuts(silences, total, every=240.0):
    cuts, target = [], every
    mids = [(x["s"] + x["e"]) / 2 for x in silences if x["e"] - x["s"] >= 0.3]
    while target < total - 30:
        near = min(mids, key=lambda m: abs(m - target), default=None)
        cut = near if near is not None and abs(near - target) < 60 else target
        if not cuts or cut - cuts[-1] > 60:
            cuts.append(round(cut, 2))
        target += every
    return cuts


def build_sentences(words, rules):
    sents, cur = [], []
    hard = rules["pausa_forte_ms"] / 1000
    for i, w in enumerate(words):
        cur.append(i)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["s"] - w["e"]) if nxt else 0
        end_punct = re.search(r"[.?!…][\"')\]]*$", w["w"]) and w["w"].lower() not in ABBR
        if nxt is None or end_punct or gap >= hard or (len(cur) >= 45 and gap >= 0.35):
            ws = [words[k] for k in cur]
            sents.append({"i": len(sents), "s": ws[0]["s"], "e": ws[-1]["e"], "w0": cur[0], "w1": cur[-1],
                          "texto": " ".join(x["w"] for x in ws), "gap_depois": round(gap, 3) if nxt else None})
            cur = []
    return sents


def safe_points(words, min_gap=0.06):
    pts = []
    for i in range(len(words) - 1):
        g = words[i + 1]["s"] - words[i]["e"]
        if g >= min_gap:
            pts.append({"e": words[i]["e"], "s": words[i + 1]["s"], "gap": round(g, 3), "w": i})
    return pts


def analyze_job(job, vid):
    d = vdir(vid)
    m = read_meta(vid)
    src = d / m["arquivo"]
    rules = load_rules()
    job.step, job.pct = "Lendo o arquivo (ffprobe)", 0.02
    info = probe(src)
    write_meta(vid, probe=info, status="analisando")
    if not info["tem_audio"]:
        write_meta(vid, status="sem_audio", step="Sem trilha de áudio")
        raise RuntimeError("Este vídeo não tem áudio. A ferramenta precisa da fala para achar os pontos de corte; use um vídeo com narração.")
    job.step, job.pct = "Extraindo o áudio (local)", 0.05
    wav = d / "audio16k.wav"
    run_proc(job, [FFMPEG, "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
                   "-c:a", "pcm_s16le", str(wav)])
    job.step, job.pct = "Detectando silêncios e pausas", 0.08
    sil = detect_silences(wav, rules["silencio_db"])
    cuts = chunk_cuts(sil, info["duracao"])
    out = d / "transcricao.json"
    engine = m.get("motor", "mlx")

    def on_line(line):
        if line.startswith("PROGRESS "):
            job.pct = 0.1 + 0.85 * float(line.split()[1])
        elif line.startswith("STEP "):
            job.step = line[5:]
        elif line.startswith("ERROR "):
            job.log.append(line)
    job.step = "Transcrevendo localmente (sem internet)"
    run_proc(job, [PY, str(BASE / "asr_worker.py"), str(wav), str(out), "--engine", engine,
                   "--lang", m.get("idioma", "auto"), "--cuts", ",".join(map(str, cuts))], on_line)
    tr = json.loads(out.read_text())
    words = tr["words"]
    if not words:
        raise RuntimeError("A transcrição não encontrou fala neste vídeo.")
    job.step, job.pct = "Montando frases e pontos de corte", 0.97
    analysis = {"palavras": words, "silencios": sil, "idioma": tr["language"], "motor": tr["engine"],
                "modelo": tr["model"]}
    (d / "analise.json").write_text(json.dumps(analysis, ensure_ascii=False))
    write_meta(vid, status="pronto", step="Pronto", idioma_detectado=tr["language"], motor_usado=tr["engine"],
               n_palavras=len(words), analisado_em=now())
    job.step = "Pronto"
    return {"video": vid, "palavras": len(words)}


def add_video(path_tmp, name, motor="mlx", idioma="auto"):
    vid = uuid.uuid4().hex[:10]
    d = vdir(vid)
    d.mkdir(parents=True)
    ext = Path(name).suffix.lower() or ".mp4"
    dst = d / f"original{ext}"
    shutil.move(str(path_tmp), dst)
    write_meta(vid, id=vid, nome=name, arquivo=dst.name, criado=now(), status="na_fila", motor=motor,
               idioma=idioma, confirmado={})
    job = submit("analise", f"Analisar {name}", analyze_job, "asr", vid=vid)
    write_meta(vid, job=job.id)
    return read_meta(vid)


def reanalyze(vid, motor=None, idioma=None):
    m = read_meta(vid)
    kw = {}
    if motor:
        kw["motor"] = motor
    if idioma:
        kw["idioma"] = idioma
    job = submit("analise", f"Analisar {m['nome']}", analyze_job, "asr", vid=vid)
    write_meta(vid, job=job.id, status="na_fila", error=None, **kw)
    return job


def delete_video(vid):
    m = read_meta(vid)
    if m and m.get("job"):
        cancel_job(m["job"])
    shutil.rmtree(vdir(vid), ignore_errors=True)


# ======================================================================= regras de corte (sem IA)
def _phrase_hits(text, phrases):
    t = " " + norm(text) + " "
    return [p for p in phrases if p.strip() and (" " + norm(p) + " ") in t]


def _starts_with(text, phrases):
    t = norm(text)
    return [p for p in phrases if p.strip() and (t == norm(p) or t.startswith(norm(p) + " "))]


def view(vid, rules=None):
    """Tudo o que a tela precisa: frases, pausas, pontos seguros, candidatos e decisão."""
    rules = rules or load_rules()
    m = read_meta(vid)
    a = json.loads((vdir(vid) / "analise.json").read_text())
    words = a["palavras"]
    sents = build_sentences(words, rules)
    for s in sents:
        s["marcas"] = {"gancho": _phrase_hits(s["texto"], rules["ganchos"]),
                       "fim_lead": _phrase_hits(s["texto"], rules["fim_lead"]),
                       "transicao": _starts_with(s["texto"], rules["transicao_forte"])}
    cands = candidates(words, sents, a["silencios"], rules, m["probe"]["duracao"])
    return {"meta": m, "frases": sents, "silencios": a["silencios"], "pontos": safe_points(words),
            "candidatos": cands["lista"], "decisao": cands["decisao"], "regras": rules,
            "idioma": a["idioma"], "motor": a["motor"]}


def candidates(words, sents, silences, rules, total):
    lo, hi = rules["lead_min_s"], rules["lead_max_s"]
    pmin = rules["pausa_min_ms"] / 1000
    out = []
    for k in range(len(sents) - 1):
        left, right = sents[k], sents[k + 1]
        e_left, s_right = left["e"], right["s"]
        gap = s_right - e_left
        mid = (e_left + s_right) / 2
        score, why = 0.0, []
        if gap >= pmin:
            b = min(3.0, gap / 0.25)
            score += b
            why.append(f"pausa de {gap:.2f}s (+{b:.1f})")
        else:
            score -= 1
            why.append(f"pausa curta {gap:.2f}s (−1)")
        if any(x["s"] <= mid <= x["e"] for x in silences):
            score += 1
            why.append("silêncio no áudio (+1)")
        if re.search(r"[.?!…][\"')\]]*$", left["texto"]):
            score += 1
            why.append("fim de frase (+1)")
        ctx = " ".join(s["texto"] for s in sents[max(0, k - 1):k + 1])
        hits = _phrase_hits(ctx, rules["fim_lead"])
        if hits:
            b = min(6, 4 * len(hits))
            score += b
            why.append(f"fim de microlead: “{hits[0]}” (+{b})")
        th = _starts_with(right["texto"], rules["transicao_forte"])
        if th:
            score += 3
            why.append(f"abertura de seção: “{th[0]}” (+3)")
        tw = _starts_with(right["texto"], rules["transicao_fraca"])
        if tw and not th:
            score += 1
            why.append(f"conectivo de transição: “{tw[0]}” (+1)")
        in_range = lo <= mid <= hi
        if in_range:
            score += 1
            why.append(f"dentro da faixa {lo}–{hi}s (+1)")
        else:
            score -= 5
            why.append(f"fora da faixa {lo}–{hi}s (−5)")
        sinais_texto = bool(hits or th)
        out.append({"k": k, "t": round(mid, 3), "e_esq": e_left, "s_dir": s_right, "gap": round(gap, 3),
                    "pontos": round(score, 1), "motivos": why, "na_faixa": in_range, "sinal_texto": sinais_texto,
                    "antes": left["texto"][-90:], "depois": right["texto"][:90],
                    "fim_lead": round(e_left + min(rules["folga_fim_lead_ms"] / 1000, gap / 2), 3),
                    "inicio_body": round(s_right - min(rules["folga_inicio_body_ms"] / 1000, gap / 2), 3)})
    out.sort(key=lambda c: -c["pontos"])
    top = [c for c in out if c["na_faixa"]][:6] or out[:6]
    if not top:
        dec = {"status": "sem_opcoes", "msg": "Não há limites de frase suficientes. Defina o corte manualmente."}
    else:
        c0 = top[0]
        margin = c0["pontos"] - (top[1]["pontos"] if len(top) > 1 else -99)
        if not c0["na_faixa"]:
            dec = {"status": "confirmar", "msg": "Nenhum candidato dentro da faixa de duração. Confira as opções."}
        elif c0["pontos"] >= rules["conf_pontos"] and margin >= rules["conf_margem"] and c0["sinal_texto"]:
            dec = {"status": "confiavel",
                   "msg": f"As regras apontam um corte claro em {fmt_t(c0['t'])} (pontos {c0['pontos']}, "
                          f"{margin:.1f} acima da 2ª opção). Ainda vale ouvir antes de exportar."}
        else:
            dec = {"status": "confirmar",
                   "msg": "As regras não são suficientes para decidir sozinhas (sem compreensão do texto). "
                          "Escolha entre as opções abaixo ou ajuste o corte na timeline."}
    return {"lista": top, "decisao": dec}


def snap(vid, t, role):
    """Leva um tempo qualquer para o ponto seguro mais próximo (nunca no meio de uma palavra)."""
    rules = load_rules()
    a = json.loads((vdir(vid) / "analise.json").read_text())
    words = a["palavras"]
    pts = safe_points(words)
    total = read_meta(vid)["probe"]["duracao"]
    if not pts:
        return {"t": t, "ajustado": False}
    best = min(pts, key=lambda p: abs((p["e"] + p["s"]) / 2 - t))
    if role == "lead":
        cut = best["e"] + min(rules["folga_fim_lead_ms"] / 1000, best["gap"] / 2)
    else:
        cut = best["s"] - min(rules["folga_inicio_body_ms"] / 1000, best["gap"] / 2)
    inside = any(w["s"] < t < w["e"] for w in words)
    return {"t": round(min(max(cut, 0), total), 3), "ajustado": inside or abs(cut - t) > 0.05,
            "dentro_de_palavra": inside, "gap": best["gap"]}


def confirm_cut(vid, **cuts):
    m = read_meta(vid)
    conf = m.get("confirmado") or {}
    conf.update({k: v for k, v in cuts.items() if v is not None})
    write_meta(vid, confirmado=conf)
    return conf


def auto_cuts(vid, role, rules=None):
    """Corte para o lote: usa o confirmado; senão o 1º candidato — e diz se precisa confirmação."""
    m = read_meta(vid)
    conf = m.get("confirmado") or {}
    key = "fim_lead" if role == "lead" else "inicio_body"
    if conf.get(key) is not None:
        return {"t": conf[key], "origem": "confirmado", "status": "confiavel"}
    v = view(vid, rules)
    if not v["candidatos"]:
        return {"t": None, "origem": "nenhum", "status": "sem_opcoes"}
    c0 = v["candidatos"][0]
    return {"t": c0[key], "origem": "regras", "status": v["decisao"]["status"]}


# ======================================================================= montagem real (ffmpeg)
def keyframes(path, a, b):
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                        "-read_intervals", f"{max(0, a - 3):.3f}%{b + 3:.3f}", "-show_entries", "frame=pts_time",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return sorted({round(float(x.split(",")[0]), 4) for x in r.stdout.split() if x.strip() and x[0].isdigit()})


def next_word_start(vid, t):
    a = json.loads((vdir(vid) / "analise.json").read_text())
    return next((w["s"] for w in a["palavras"] if w["s"] >= t - 0.01), None)


def compat_for_copy(pa, pb):
    keys = ["vcodec", "largura", "altura", "pix_fmt", "perfil", "acodec", "sample_rate", "canais"]
    diffs = [k for k in keys if pa.get(k) != pb.get(k)]
    if abs((pa.get("fps") or 0) - (pb.get("fps") or 0)) > 0.01:
        diffs.append("fps")
    if pa.get("rotacao") or pb.get("rotacao"):
        diffs.append("rotacao")
    return diffs


def body_keyframe_in_pause(vid, start):
    """Procura um keyframe dentro da pausa antes da 1ª palavra do body (onde mover o corte não se ouve)."""
    a = json.loads((vdir(vid) / "analise.json").read_text())
    words = a["palavras"]
    nxt = next((w for w in words if w["s"] >= start - 0.02), None)
    prv = max((w for w in words if w["e"] <= start + 0.02), key=lambda w: w["e"], default=None)
    lo = (prv["e"] + 0.03) if prv else 0.0
    hi = (nxt["s"] - 0.03) if nxt else start + 0.3
    src = vdir(vid) / read_meta(vid)["arquivo"]
    kfs = [k for k in keyframes(src, lo, hi) if lo <= k <= hi]
    return (min(kfs, key=lambda k: abs(k - start)) if kfs else None), (lo, hi)


def render_job(job, spec):
    phase(job, "render", "Renderização", False)
    L, B, o = spec["lead"], spec["body"], spec.get("opcoes", {})
    ma, mb = read_meta(L["video"]), read_meta(B["video"])
    pa, pb = ma["probe"], mb["probe"]
    src_a, src_b = vdir(L["video"]) / ma["arquivo"], vdir(B["video"]) / mb["arquivo"]
    la, lb = float(L.get("inicio", 0)), float(L["fim"])
    ba, bb = float(B["inicio"]), float(B.get("fim") or pb["duracao"])
    if lb - la < 0.5 or bb - ba < 0.5:
        raise RuntimeError("Segmento curto demais — confira os cortes.")
    preview = bool(o.get("previa"))
    if preview:
        la, bb = max(la, lb - 4.0), min(bb, ba + 4.0)
    delivery=o.get("entrega","video")
    if delivery not in ('video','xml','ambos'):raise ValueError('Escolha vídeo, XML ou ambos.')
    if delivery=='xml' and not preview:
        from .ml_premiere import export
        xml=export(spec,OUT_DIR,o.get('nome') or 'Microlead e Body',vdir)
        job.step='XML pronto para importar no Premiere'
        return {'arquivo':None,'xml':xml,'duracao_s':(lb-la)+(bb-ba),'esperado_s':(lb-la)+(bb-ba),'transicao_s':lb-la,'decisao':['Sequência editável com as fontes locais e cortes secos. Não aplica fades nem renderiza vídeo.']}
    modo = o.get("modo", "auto")
    saida = o.get("formato", "mp4")
    nome = o.get("nome") or f"{slug(Path(ma['nome']).stem, 24)}_lead-{fmt_t(lb).replace(':', 'm')}" \
                            f"+{slug(Path(mb['nome']).stem, 24)}_body-{fmt_t(ba).replace(':', 'm')}"
    if preview:
        nome = "previa_" + nome
    ext = ".mov" if saida == "mov" else ".mp4"
    out = OUT_DIR / f"{nome}_{job.id}{ext}"
    report = {"modo_pedido": modo, "decisao": [], "arquivo": out.name}
    ba_original = ba

    # --------- caminho 1: copiar fluxos (sem recodificar), só quando é tecnicamente seguro
    used_copy = False
    if modo in ("auto", "copiar") and not preview and saida == "mp4":
        diffs = compat_for_copy(pa, pb)
        kf, win = (None, None)
        if not diffs:
            kf, win = body_keyframe_in_pause(B["video"], ba)
        if diffs:
            report["decisao"].append("Não dá para copiar fluxos: os vídeos diferem em " + ", ".join(diffs) + ".")
        elif kf is None:
            report["decisao"].append(f"Não dá para copiar fluxos: não há keyframe na pausa antes do body "
                                     f"({win[0]:.2f}–{win[1]:.2f}s); cortar fora dele estragaria a imagem.")
        else:
            report["decisao"].append(f"Tentando copiar fluxos sem recodificar: início do body ajustado de {ba:.3f}s "
                                     f"para o keyframe {kf:.3f}s, dentro da pausa (não se ouve).")
            ba = kf
            used_copy = True
        if modo == "copiar" and not used_copy:
            raise RuntimeError(report["decisao"][-1] + " Use o modo automático ou o exato.")

    tmpdir = OUT_DIR / f".tmp_{job.id}"
    tmpdir.mkdir(exist_ok=True)
    total = (lb - la) + (bb - ba)

    def progress_line(offset, span, base_total):
        def f(line):
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    us = int(line.split("=")[1])
                except ValueError:
                    return
                job.pct = min(0.99, (offset + us / 1e6) / base_total) if base_total else 0
        return f

    try:
        if used_copy:
            s1, s2 = tmpdir / "lead.mp4", tmpdir / "body.mp4"
            job.step = "Copiando a microlead (sem recodificar)"
            run_proc(job, [FFMPEG, "-y", "-v", "error", "-progress", "pipe:1", "-nostats", "-ss", f"{la:.3f}",
                           "-i", str(src_a), "-t", f"{lb - la:.3f}", "-map", "0:v:0", "-map", "0:a:0", "-c", "copy",
                           "-avoid_negative_ts", "make_zero", str(s1)], progress_line(0, lb - la, total))
            job.step = "Copiando o body (sem recodificar)"
            run_proc(job, [FFMPEG, "-y", "-v", "error", "-progress", "pipe:1", "-nostats", "-ss", f"{ba:.3f}",
                           "-i", str(src_b), "-t", f"{bb - ba:.3f}", "-map", "0:v:0", "-map", "0:a:0", "-c", "copy",
                           "-avoid_negative_ts", "make_zero", str(s2)], progress_line(lb - la, bb - ba, total))
            # a cópia só corta entre pacotes: confere se a microlead não invadiu a próxima palavra
            real_end = la + verify(s1)["duracao_s"]
            nxt_word = next_word_start(L["video"], lb)
            if nxt_word is not None and real_end > nxt_word - 0.03:
                report["decisao"].append(f"A cópia terminaria a microlead em {real_end:.2f}s, invadindo a palavra "
                                         f"seguinte ({nxt_word:.2f}s). Voltei para o corte exato.")
                used_copy, ba = False, ba_original
                if modo == "copiar":
                    raise RuntimeError(report["decisao"][-1])
            else:
                lst = tmpdir / "lista.txt"
                lst.write_text(f"file '{s1}'\nfile '{s2}'\n")
                job.step = "Juntando (concat sem recodificar)"
                run_proc(job, [FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                               "-movflags", "+faststart", str(out)])
                total = la + (real_end - la) + (bb - ba) - la
        if not used_copy:
            # --------- caminho 2: um passe só, corte exato, tudo normalizado (sincronismo garantido)
            ref = pb if o.get("resolucao", "body") == "body" else pa
            if re.fullmatch(r"\d+x\d+", str(o.get("resolucao", ""))):
                W, H = map(int, o["resolucao"].split("x"))
            else:
                W, H = ref["largura"], ref["altura"]
            fps = float(o.get("fps") or ref["fps"] or 30)
            if preview:
                H2 = 540
                W, H = int(round(W * H2 / H / 2) * 2), H2
            W, H = W - W % 2, H - H % 2
            fade = max(0.0, float(o.get("fade_ms", 20)) / 1000)
            segs = [(src_a, la, lb, pa), (src_b, ba, bb, pb)]
            cmd = [FFMPEG, "-y", "-v", "error", "-progress", "pipe:1", "-nostats"]
            for p, s, e, _ in segs:
                cmd += ["-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", str(p)]
            amap, nxt_in = {}, 2
            for i, (p, s, e, pr) in enumerate(segs):
                if pr["tem_audio"]:
                    amap[i] = f"{i}:a:0"
                else:
                    cmd += ["-f", "lavfi", "-t", f"{e - s:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
                    amap[i] = f"{nxt_in}:a:0"
                    nxt_in += 1
            fc = []
            qd = []
            for i, (p, s, e, pr) in enumerate(segs):
                # duração arredondada para um nº inteiro de quadros: áudio e vídeo de cada trecho ficam iguais,
                # então a emenda não desloca o sincronismo
                dur = max(1, round((e - s) * fps)) / fps
                qd.append(dur)
                fc.append(f"[{i}:v:0]setpts=PTS-STARTPTS,fps={fps:.6f},scale={W}:{H}:force_original_aspect_ratio=decrease,"
                          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p,"
                          f"tpad=stop_mode=clone:stop_duration=1,trim=duration={dur:.6f},setpts=PTS-STARTPTS[v{i}]")
                af = f"[{amap[i]}]asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
                if fade > 0:
                    af += (f",afade=t=out:st={max(0, dur - fade):.3f}:d={fade:.3f}" if i == 0
                           else f",afade=t=in:st=0:d={fade:.3f}")
                af += f",apad,atrim=duration={dur:.6f}[a{i}]"
                fc.append(af)
            fc.append("[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
            cmd += ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]"]
            if preview:
                cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", "-b:a", "128k"]
                report["decisao"].append("Prévia rápida da junção (4 s de cada lado, 540p).")
            elif saida == "mov":
                cmd += ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le", "-c:a", "pcm_s16le"]
                report["decisao"].append("Exportado em ProRes 422 HQ (.mov), bom para continuar editando.")
            elif modo == "rapido":
                br = max(4_000_000, int(max(pa["bitrate"], pb["bitrate"]) * 1.2))
                cmd += ["-c:v", "h264_videotoolbox", "-b:v", str(br), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
                report["decisao"].append("Recodificado no hardware do Mac (mais rápido, arquivo um pouco maior).")
            else:
                crf = int(o.get("crf", 18))
                cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k"]
                if not report["decisao"] or modo == "exato":
                    report["decisao"].append(f"Recodificado com corte exato (x264 CRF {crf}).")
            cmd += ["-r", f"{fps:.6f}", "-movflags", "+faststart", str(out)]
            report.update({"resolucao": f"{W}x{H}", "fps": round(fps, 3), "fade_ms": int(fade * 1000)})
            total = sum(qd)
            job.step = "Renderizando (local)" if not preview else "Renderizando prévia"
            run_proc(job, cmd, progress_line(0, total, total))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        if job.cancel and out.exists():
            out.unlink()

    # --------- verificação do arquivo gerado
    phase(job, "conferencia", "Conferência do vídeo gerado")
    job.step, job.pct = "Conferindo o arquivo gerado", 0.995
    chk = verify(out)
    report.update(chk)
    report.update({"copiou_fluxos": used_copy, "esperado_s": round(total, 3),
                   "cortes": {"lead": [round(la, 3), round(lb, 3)], "body": [round(ba, 3), round(bb, 3)]},
                   "transicao_s": round(lb - la, 3)})
    if delivery=='ambos' and not preview:
        from .ml_premiere import export
        actual={'lead':dict(L,inicio=la,fim=lb),'body':dict(B,inicio=ba,fim=bb),'opcoes':o}
        report['xml']=export(actual,OUT_DIR,nome,vdir)
        report['decisao'].append('XML editável incluído: cortes secos, sem os fades da renderização.')
    job.step = "Pronto"
    return report


def verify(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,duration,width,height,r_frame_rate",
                        "-show_entries", "format=duration,size", "-of", "json", str(path)], capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    vs = next((s for s in d.get("streams", []) if s["codec_type"] == "video"), {})
    au = next((s for s in d.get("streams", []) if s["codec_type"] == "audio"), {})
    vd, ad = float(vs.get("duration") or 0), float(au.get("duration") or 0)
    return {"duracao_s": round(float(d.get("format", {}).get("duration") or 0), 3),
            "video_s": round(vd, 3), "audio_s": round(ad, 3), "dif_av_ms": round(abs(vd - ad) * 1000),
            "tamanho_mb": round(int(d.get("format", {}).get("size") or 0) / 1048576, 2),
            "saida_res": f"{vs.get('width')}x{vs.get('height')}"}


def submit_render(spec):
    L, B = read_meta(spec["lead"]["video"]), read_meta(spec["body"]["video"])
    tag = "Prévia" if spec.get("opcoes", {}).get("previa") else "Montar"
    return submit("render", f"{tag}: {L['nome']} + {B['nome']}", render_job, "render", spec=spec)


# ======================================================================= lote
BATCHES = {}


def create_batch(pairs, opcoes, pular_incertos=True):
    bid = uuid.uuid4().hex[:8]
    items = []
    for p in pairs:
        lc, bc = auto_cuts(p["lead"], "lead"), auto_cuts(p["body"], "body")
        item = {"lead": p["lead"], "body": p["body"], "corte_lead": lc, "corte_body": bc, "job": None}
        incerto = "confiavel" not in (lc["status"], ) or bc["status"] != "confiavel"
        if lc["t"] is None or bc["t"] is None:
            item["status"] = "sem_corte"
        elif incerto and pular_incertos:
            item["status"] = "precisa_confirmar"
        else:
            spec = {"lead": {"video": p["lead"], "inicio": 0, "fim": lc["t"]},
                    "body": {"video": p["body"], "inicio": bc["t"], "fim": None}, "opcoes": opcoes}
            item["job"] = submit_render(spec).id
            item["status"] = "enviado"
        items.append(item)
    BATCHES[bid] = {"id": bid, "itens": items, "criado": now(), "opcoes": opcoes}
    return batch_view(bid)


def batch_view(bid):
    b = BATCHES[bid]
    for it in b["itens"]:
        if it["job"]:
            j = JOBS[it["job"]]
            it["status"], it["pct"], it["step"], it["resultado"], it["erro"] = j.status, j.pct, j.step, j.result, j.error
    return b
