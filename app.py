#!/usr/bin/env python3
"""
Transcrição + Fatiador de Speakers (AssemblyAI)

Roda um servidor local (só na sua máquina) com uma página onde você:
  1. arrasta um áudio/vídeo,
  2. o app transcreve no AssemblyAI com diarização (speaker labels),
  3. entrega transcrição (.txt, .srt, .json) e fatia cada fala por speaker
     (um arquivo por fala + um arquivo com todas as falas do speaker emendadas),
  4. oferece ZIP do projeto sob demanda.

Uso:  python3 app.py        (abre http://localhost:8765 no navegador)
Requisitos: python3 + requests + ffmpeg/ffprobe no PATH.
A chave fica em .env ao lado deste arquivo:  ASSEMBLYAI_API_KEY=...
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from collections import Counter
import webbrowser
from datetime import datetime
from decimal import Decimal
from difflib import SequenceMatcher
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

# Windows pode iniciar com cp1252 mesmo quando o log é um arquivo UTF-8.
# Configure os streams antes de qualquer aviso e propague aos processos Python.
for _stream in (sys.stdout,sys.stderr):
    if _stream is not None and hasattr(_stream,'reconfigure'):
        _stream.reconfigure(encoding='utf-8',errors='backslashreplace')
os.environ['PYTHONIOENCODING']='utf-8'
from plataforma import diagnostico as _DIAG
_DIAG.protect_streams()

import requests

from plataforma import armazenamento as STORAGE
from plataforma import recorte_audio as RECORTE
from plataforma import equipe_api as EQUIPE_API
from plataforma import trocas_api as TROCAS_API
from plataforma import api as PLATAFORMA  # painel novo + Microlead/Body (tudo local)

BASE = Path(__file__).resolve().parent
RUNTIME_VERSION=PLATAFORMA.RUNTIME_VERSION
OUT_ROOT = STORAGE.current("fatiador")
UPLOADS = BASE / ".uploads"
PORT = int(os.environ.get("PORT", 8765))
API = "https://api.assemblyai.com/v2"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

JOBS = {}  # id -> estado do processamento


# ---------------------------------------------------------------- utilidades
def api_key():
    from plataforma import credenciais
    return credenciais.key()


def ts_srt(ms):
    return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"


def ts_short(ms):
    s = ms // 1000
    return f"{s//60:02d}m{s%60:02d}s"


def slug(text, n=40):
    t = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()
    t = re.sub(r"\s+", "_", t)
    return t[:n].rstrip("_") or "fala"


def set_state(jid, **kw):
    JOBS[jid].update(kw)


# ---------------------------------------------------------------- detecção do produto
def _dict_words():
    f = Path("/usr/share/dict/words")
    if not f.exists():
        return set()
    return {w.strip() for w in f.read_text(errors="ignore").splitlines() if w and w[0].islower()}


DICT = _dict_words()


def _proper_names():
    f = Path("/usr/share/dict/words")
    if not f.exists():
        return set()
    lines = [w.strip() for w in f.read_text(errors="ignore").splitlines() if w.strip()]
    low = {w for w in lines if w[0].islower()}
    return {w.lower() for w in lines if w[0].isupper() and w.lower() not in low}


NAMES = _proper_names()
STOP_CAPS = set("""i i'm i'll i've i'd american americans usa us fda gmp amazon omron johns hopkins university association
heart big pharma god oz sanjay gupta mehmet monday tuesday wednesday thursday friday saturday sunday january february
march april may june july august september october november december ohio michigan texas florida virginia california
new york america english spanish dr doctor mr mrs ms ok yes no the harvard stanford mayo clinic jama ai tv icu usa's states united buy now""".split())


def detect_product(d):
    """Acha o nome do produto: termo capitalizado no meio de frase (ou 2 termos seguidos) que mais se repete,
    somando as variações que o reconhecimento errou. Devolve {product, aliases, alternativas}."""
    from plataforma.mencoes import contextual_names, transcript_words, is_common_speech_word
    raw_words = transcript_words(d)
    words = [w["text"] for w in raw_words]
    if not words:
        return None
    clean = lambda t: re.sub(r"^[^\w]+|[^\w]+$", "", t)
    cand = {}  # texto -> contagem (só ocorrências capitalizadas no meio da frase)
    def ok_single(t):
        l = t.lower()
        return len(t) >= 4 and t[0].isupper() and l not in STOP_CAPS and l not in DICT and not is_common_speech_word(t)
    for i, raw in enumerate(words):
        t = clean(raw)
        if not t or i == 0 or re.search(r"[.?!]$", words[i - 1]) or not t[0].isupper():
            continue
        if i and clean(words[i - 1]).lower() in ("dr", "doctor", "mr", "mrs", "ms"):
            continue
        two = None
        if i + 1 < len(words):
            t2 = clean(words[i + 1])
            if t2 and t2[0].isupper() and not re.search(r"[.,;?!]$", raw) and t.lower() not in STOP_CAPS and t2.lower() not in STOP_CAPS and not is_common_speech_word(t) and not is_common_speech_word(t2):
                two = f"{t} {t2}"
        if two:
            cand[two] = cand.get(two, 0) + 1
        if ok_single(t):
            cand[t] = cand.get(t, 0) + 1
    # agrupa variações parecidas e soma as ocorrências (em qualquer posição da frase)
    all_norm = [norm(clean(w)) for w in words]
    # um termo solto que faz parte de um nome composto forte ("Cardio" de "Cardio Flush") sai da disputa
    for name in [k for k in cand if " " not in k]:
        for k2, c2 in cand.items():
            if " " in k2 and name in k2.split() and c2 >= 0.6 * cand[name]:
                cand.pop(name, None); break
    groups = []
    for name, c in sorted(cand.items(), key=lambda kv: -kv[1]):
        if c < 2:
            continue
        n = norm(name)
        for g in groups:
            if SequenceMatcher(None, n, norm(g["name"])).ratio() >= 0.78:
                g["variants"][name] = c; break
        else:
            groups.append({"name": name, "variants": {name: c}})
    def vocative(name):
        """True se o termo aparece quase sempre como chamamento: ", Phil." """
        n = norm(name); hits = voc = 0
        for i, w in enumerate(all_norm):
            if w == n and " " not in name:
                hits += 1
                prev = words[i - 1] if i else ""
                nxt = words[i] if True else ""
                if prev.endswith(",") and re.search(r"[.?!,]$", words[i]):
                    voc += 1
        return hits >= 3 and voc / hits >= 0.5
    out = []
    totals = {size: Counter(''.join(all_norm[i:i+size]) for i in range(len(all_norm)-size+1)) for size in (1, 2)}
    for g in groups:
        if any(vocative(v) or (" " not in v and v.lower() in NAMES and not re.search(r"[a-z][A-Z]", v)) for v in g["variants"]):
            continue
        total = 0
        for v in g["variants"]:
            nv = norm(v); size = 2 if " " in v else 1
            for token, count in totals[size].items():
                if token == nv:
                    total += count
                elif 2 * min(len(token),len(nv)) >= .8 * (len(token)+len(nv)):
                    sim = SequenceMatcher(None, token, nv)
                    if sim.quick_ratio() >= .8 and sim.ratio() >= .8:
                        total += count
        best = max(g["variants"], key=lambda v: g["variants"][v])
        if re.search(r"[a-z][A-Z]", best) or " " in best:
            total = int(total * 1.5)
        out.append({"name": best, "total": total, "aliases": [v for v in g["variants"] if v != best]})
    out.sort(key=lambda g: (-g["total"], -len(g["name"])))
    out = [g for g in out if g["total"] >= 3]
    contextual = contextual_names(sentences(raw_words))
    if contextual:
        # Agrupa a mesma marca grafada com capitalização ou espaços diferentes.
        for name, count in contextual:
            existing = next((g for g in out if norm(g["name"]) == norm(name)), None)
            if existing:
                existing["contexto"] = count
            else:
                out.append({"name": name.title(), "total": count, "aliases": [], "contexto": count, "somente_contexto": True})
        out.sort(key=lambda g: (-min(g.get("contexto",0),3), -g["total"], -len(g["name"])))
    if not out:
        return None
    top = out[0]
    return {"product": top["name"], "aliases": "", "mencoes": top["total"],
            "confirmar": top.get("somente_contexto",False),
            "alternativas": [{"nome": g["name"], "mencoes": g["total"]} for g in out[1:5]]}


# ---------------------------------------------------------------- frases com o produto
ABBR = {"dr.", "mr.", "mrs.", "ms.", "vs.", "st.", "jr.", "sr.", "u.s.", "no.", "etc."}


def norm(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())


def sentences(words):
    """Frases orais a partir das palavras do AssemblyAI (quebra em .?! e troca de speaker)."""
    out, cur = [], []
    for w in words:
        if cur and w.get("speaker") != cur[-1].get("speaker"):
            out.append(cur); cur = []
        cur.append(w)
        t = w["text"]
        if re.search(r"[.?!][\"')\]]*$", t) and t.lower() not in ABBR and not re.fullmatch(r"[A-Za-z]\.", t):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def match_spans(toks, names):
    from plataforma.mencoes import spans
    return spans(toks, names, approximate=False)


def swap_name(sw, picks, novo):
    out, k = [], 0
    starts = {i: size for i, size, _ in picks}
    while k < len(sw):
        if k in starts:
            size = starts[k]
            first, last = sw[k]["text"], sw[k + size - 1]["text"]
            lead = re.match(r"^[^\w$]*", first).group(0)
            trail = re.search(r"[^\w%$]*$", last).group(0)
            out.append(f"{lead}{novo}{trail}")
            k += size
        else:
            out.append(sw[k]["text"]); k += 1
    return " ".join(out)


def find_phrases(d, product, aliases="", novo=""):
    from plataforma import mencoes as MC
    names = MC.names(product, aliases)
    res = []
    params = dict(field="text", time="start", end="end", max_pause=850)
    protect_new = novo and MC.compact(novo) not in {MC.compact(n) for n in names}
    words = MC.transcript_words(d)
    groups = sentences(words)
    # Nome dito em partes (“Gluco. Trust. Pro.”) une as frases que ele atravessa.
    bridges = MC.bridged_spans(words, names, **params)
    if bridges:
        index = {id(w): g for g, group in enumerate(groups) for w in group}
        merged = []
        spans_by_group = {}
        for i, size, _ in bridges:
            a, b = index[id(words[i])], index[id(words[i + size - 1])]
            spans_by_group[a] = max(spans_by_group.get(a, a), b)
        g = 0
        while g < len(groups):
            last = spans_by_group.get(g, g)
            k = g
            while k < last:
                k += 1
                last = max(last, spans_by_group.get(k, k))
            merged.append([w for group in groups[g:last + 1] for w in group])
            g = last + 1
        groups = merged
    for sw in groups:
        picks = MC.timed_spans(sw, names, **params)
        if protect_new:
            protected = {j for i, size, _ in MC.timed_spans(sw, [novo], approximate=False, **params)
                         for j in range(i,i+size)}
            picks = [(i,size,score) for i,size,score in picks if not protected.intersection(range(i,i+size))]
        if not picks:
            continue
        voices = Counter(w.get("speaker") for w in sw if w.get("speaker"))
        item = {"n": len(res) + 1, "speaker": (voices.most_common(1)[0][0] if voices else None) or "A", "start": sw[0]["start"],
                "end": sw[-1]["end"], "text": " ".join(w["text"] for w in sw), "mencoes": len(picks), "primeira_mencao_ms": sw[picks[0][0]]["start"]}
        variants = [" ".join(w["text"] for w in sw[i:i + size]) for i, size, score in picks if score < 1]
        if variants:
            item["mencoes_revisar"] = variants
        if novo:
            item["novo"] = swap_name(sw, picks, novo)
            exact_picks = [p for p in picks if p[2] == 1]
            if variants and exact_picks:
                item["novo_sem_sugestoes"] = swap_name(sw, exact_picks, novo)
                item["novo_com_sugestoes"] = item["novo"]
        res.append(item)
    n = len(res)
    m = RECORTE.metrics(res, float(d.get("audio_duration") or 0))
    resumo = f"[PRODUTO: {product.upper()}]\n\nFrases com o produto: {n}"
    review_count = sum(bool(r.get("mencoes_revisar")) for r in res)
    if review_count:
        resumo += f" · {review_count} com grafias prováveis para conferir"
    if (d.get("recorte_transcricao") or {}).get("inicio_ms", 0) > 0:
        resumo += "\nBusca parcial: a primeira metade não foi transcrita."
    if n and m["duracao_vsl_ms"]:
        resumo += f"\nPrimeira menção: {ts_short(m['primeira_mencao_ms'])}\nJanela de troca até o fim da VSL: {ts_short(m['janela_troca_ms'])}\nSoma das frases a substituir: {ts_short(m['soma_frases_ms'])}"
    elif not n:
        resumo += "\nNenhuma menção encontrada no trecho analisado. Confira o nome e, se necessário, transcreva o vídeo inteiro."
    return res, resumo


def cut_wav_then_mp3(src, a_ms, b_ms, dst, pad_ms):
    a, b = max(0, a_ms - pad_ms) / 1000, (b_ms + pad_ms) / 1000
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{a:.3f}", "-i", str(src), "-t", f"{b-a:.3f}",
                    "-vn", "-ac", "2", "-ar", "44100", "-c:a", "libmp3lame", "-q:a", "2", str(dst)], check=True)


def write_phrases(out, d, product, aliases, novo, do_cut, pad_ms, progress=None):
    res, resumo = find_phrases(d, product, aliases, novo)
    tag = slug(product, 30).upper()
    lines = "\n".join(f"{r['n']}. {r['text']}" for r in res)
    (out / f"frases_{tag}.txt").write_text(f"{resumo}\n\n{lines}\n")
    if novo:
        (out / f"frases_{tag}_NOVO_{slug(novo, 30)}.txt").write_text(
            "\n".join(f"{r['n']}. [Speaker {r['speaker']}] {r['novo']}" for r in res) + "\n")
    src = next(iter(out.glob("_fonte.*")), None)
    folder = out / f"FRASES_{tag}"
    if do_cut and src and res:
        folder.mkdir(exist_ok=True)
    for r in res:
        if do_cut and src:
            if progress:
                progress(r["n"], len(res))
            name = f"{r['n']:03d}_speaker{r['speaker']}_{ts_short(r['start'])}.mp3"
            cut_wav_then_mp3(src, r["start"], r["end"], folder / name, pad_ms)
            r["file"] = f"{folder.name}/{name}"
    (out / f"frases_{tag}.json").write_text(json.dumps({"produto": product, "produto_aliases": aliases, "produto_novo": novo or None,
                                                       "resumo": resumo, "frases": res, "metricas": RECORTE.metrics(res, float(d.get("audio_duration") or 0))}, ensure_ascii=False, indent=2))
    return res, resumo


def export_fatiador_premiere(out, d, phrases, product, aliases="", include_prices=False, fps=30):
    """Exporta a seleção do Fatiador, sem retranscrever nem passar pela revisão."""
    from plataforma import validacao as V
    selected = [dict(p, origem="produto") for p in phrases]
    prices = out / "precos_TROCA.json"
    if include_prices and prices.exists():
        selected += [dict(p, origem="preco_kit") for p in json.loads(prices.read_text()).get("frases", [])]
    names = V.terms([product] + [a.strip() for a in aliases.split(",") if a.strip()])
    items = []
    for n, phrase in enumerate(sorted(selected, key=lambda p: p["start"]), 1):
        text = V.norm(phrase["text"])
        exact = phrase["origem"] == "preco_kit" or any((" " + a + " ") in (" " + text + " ") for a in names)
        a, b = phrase["start"], phrase["end"]
        items.append(phrase | {"n": n, "tl_in": a, "tl_out": b, "status": "ok" if exact else "revisar"})
    tag = slug(product, 30).upper() or "TRECHOS"
    prefix = "fatiador_" + tag
    exports = {"json": prefix + ".json", "jsx": prefix + "_marcadores.jsx", "cortes_jsx": prefix + "_cortes.jsx"}
    script = jsx_premiere(items).replace("__FPS__", str(fps))
    (out / exports["jsx"]).write_text(script)
    (out / exports["cortes_jsx"]).write_text(script.replace('MODE: "MARCADORES"', 'MODE: "CORTAR"', 1))
    # O script existente corta somente áudio em A1; o arquivo de cortes deixa isso explícito.
    words = [{"w": w["text"], "s": w["start"] / 1000, "e": w["end"] / 1000} for w in d.get("words", [])]
    analysis = V.analyze(words, [])
    analysis["resquicios"] = [{"inicio": i["tl_in"] / 1000, "fim": i["tl_out"] / 1000,
        "texto": i["text"], "termo": product if i["origem"] == "produto" else "preço/kit",
        "tipo": "produto_antigo" if i["status"] == "ok" else "produto_possivel",
        "status": "encontrado" if i["status"] == "ok" else "revisar"} for i in items]
    source = next(iter(out.glob("_fonte.*")), None)
    if source:
        try:
            info = V.M.probe(source)
        except RuntimeError:
            info = None  # Fonte somente de áudio: JSON/JSX continuam disponíveis.
        if info:
            report = V.export(analysis, source, info, uuid.uuid4().hex[:10])
            for kind in ("xml", "cortes"):
                from plataforma.nomes_arquivos import write_xml
                import xml.etree.ElementTree as ET
                tree = ET.parse(V.M.OUT_DIR / report["exports"][kind])
                filename = write_xml(tree.getroot(), out, product, "Cortes de video e audio" if kind == "cortes" else "Marcadores").name
                exports[kind] = filename
    payload = {"produto": product, "origem": "Fatiador e troca de potes", "unidade": "milissegundos",
               "referencia": "Início do arquivo original. Para uma timeline editada, use Alinhar com a timeline.",
               "itens": items, "exports": exports, "pitch": analysis["pitch"],
               "instrucoes": "JSX de cortes: fatia áudio A1 usando QE, sem remoção ou ripple. Confira sequência e trilha. XML com cortes: sequência nova, vídeo e áudio divididos. Menções aproximadas só recebem marcadores."}
    (out / exports["json"]).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


# ---------------------------------------------------------------- troca de preços e kits (sem IA)
NUMW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "um": 1, "uma": 1, "dois": 2, "duas": 2, "três": 3, "tres": 3,
        "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "doze": 12}
WNUM_EN = {v: k for k, v in list(NUMW.items())[:12]}
KIT_NOUN = r"(?:bottles?|jars?|kits?|packs?|packages?|boxes|box|pouch(?:es)?|months?|units?|potes?|frascos?|caixas?|meses|m[eê]s)"
from plataforma.valores import RX_PRICE, currency, format_amount, input_amount, price_key
RX_QTY = re.compile(r"\b(?P<n>\d{1,2}|" + "|".join(NUMW) + r")(?P<sep>[\s-])(?P<adj>(?:free|extra|more|bonus|additional|full|grátis|gratuitos?)\s)?(?P<noun>" + KIT_NOUN + r")\b", re.I)
RX_BARE = re.compile(r"(?<![\w$.,-])(?<!phase )(?<!step )(?<!number )(?P<n>\d{1,2}|" + "|".join(NUMW) + r")(?![\w%-]|\.\d|,\d)"
                     r"(?!\s?(?:pm|am|p\.m|a\.m|%|weeks?|days?|months?|years?|hours?|minutes?|seconds?|times|x|insulin|shots?|pounds?|kg|lbs?|steps?|phases?|percent)\b)", re.I)
RX_UNIT = re.compile(r"^\W{0,3}(?:per|a|each|for each|/)\s?(?:bottle|jar|unit|kit|pack|month|frasco|pote|unidade)|^\W{0,3}each\b|^\W{0,3}cada\b", re.I)
KIT_CTX = re.compile(r"\b(?:bottles?|jars?|kits?|packs?|packages?|supply|order|price|discount|save|only|pay|free|potes?|frascos?|pre[çc]o)\b", re.I)


def _price_key(m):
    return price_key(m)


def _family(noun):
    n = noun.lower()
    if re.match(r"(month|mes|mês)", n):
        return "meses"
    if re.match(r"(kit|pack|package|box|caixa)", n):
        return "kits"
    return "frascos"


def _qty_val(t):
    return int(t) if t.isdigit() else NUMW.get(t.lower())


def detect_prices(d):
    """Valores e quantidades de kit citados na fala, com o contexto de cada um."""
    vals, qtys, kits, frs = {}, {}, [], []
    for sw in sentences(d.get("words") or []):
        text = " ".join(w["text"] for w in sw)
        pm, qm = list(RX_PRICE.finditer(text)), list(RX_QTY.finditer(text))
        if not pm and not qm:
            continue
        kit_ctx = bool(qm) or bool(KIT_CTX.search(text))
        for m in pm:
            k = _price_key(m)
            v = vals.setdefault(k, {"valor": k, "vezes": 0, "kit": False, "por_unidade": False, "exemplo": text[:160]})
            v["vezes"] += 1
            v["kit"] = v["kit"] or kit_ctx
            if RX_UNIT.search(text[m.end():m.end() + 22]):
                v["por_unidade"] = True
        for m in qm:
            q = _qty_val(m.group("n"))
            if q is None:
                continue
            fam = _family(m.group("noun"))
            x = qtys.setdefault(f"{q}|{fam}", {"chave": f"{q}|{fam}", "qtd": q, "tipo": fam, "vezes": 0,
                                               "exemplo": text[:160], "formas": []})
            x["vezes"] += 1
            if m.group(0) not in x["formas"]:
                x["formas"].append(m.group(0))
            # preço mais próximo na mesma frase = provável preço deste kit
            if pm and fam != "meses":
                near = min(pm, key=lambda p: abs(p.start() - m.start()))
                kits.append({"qtd": q, "preco": _price_key(near),
                             "por_unidade": bool(RX_UNIT.search(text[near.end():near.end() + 22])), "frase": text[:160]})
        frs.append({"speaker": sw[0].get("speaker") or "A", "start": sw[0]["start"], "end": sw[-1]["end"], "text": text})
    seen, uniq = set(), []
    for k in kits:
        key = (k["qtd"], k["preco"], k["por_unidade"])
        if key not in seen:
            seen.add(key); uniq.append(k)
    return {"valores": sorted(vals.values(), key=lambda v: (not v["kit"], -v["vezes"])),
            "quantidades": sorted(qtys.values(), key=lambda q: (q["tipo"] == "meses", q["tipo"], q["qtd"])), "kits": uniq, "frases_com_valor": len(frs)}


def _fmt_new_price(orig, new):
    new = format_amount(new, currency(orig))
    if orig.group("brl") or orig.group("brl_word"):
        return f"R${new}" if orig.group("brl") else f"{new} {orig.group('brl_word')}"
    if orig.group("cur"):
        return f"{orig.group('cur')}{new}"
    return f"{new} {orig.group('word') or orig.group('spoken_currency')}"


def swap_prices(text, mapa_p, mapa_q):
    changed = []

    def rp(m):
        k = _price_key(m)
        value = str(mapa_p.get(k) or "").strip()
        if not value:
            return m.group(0)
        new, symbol = input_amount(value)
        if symbol and symbol != currency(m):
            raise ValueError(f"A moeda de {value} é diferente da original ({m.group(0)}).")
        if Decimal(new) == Decimal(k):
            return m.group(0)
        out = _fmt_new_price(m, new)
        changed.append(f"{m.group(0)} → {out}")
        return out

    def rq(m):
        q = _qty_val(m.group("n"))
        new = (mapa_q.get(f"{q}|{_family(m.group('noun'))}") or "").strip()
        if q is None or not new or not new.isdigit() or int(new) == q:
            return m.group(0)
        n = int(new)
        num = m.group("n")
        word = num if num.isdigit() else None
        if word is None:
            w = WNUM_EN.get(n, str(n)) if num.lower() in WNUM_EN.values() else str(n)
            num_out = w.capitalize() if num[0].isupper() else w
        else:
            num_out = str(n)
        noun = m.group("noun")
        if m.group("sep") == " ":  # "3 bottles" ↔ "1 bottle"; com hífen ("6-bottle") fica no singular
            if n == 1 and noun.lower().endswith("s") and not noun.lower().endswith("ss"):
                noun = noun[:-1]
            elif n != 1 and not noun.lower().endswith("s"):
                noun = noun + "s"
        out = f"{num_out}{m.group('sep')}{m.group('adj') or ''}{noun}"
        changed.append(f"{m.group(0)} → {out}")
        return out

    original = text
    text = RX_PRICE.sub(rp, text)
    text = RX_QTY.sub(rq, text)
    olds = {int(k.split("|")[0]) for k, v in mapa_q.items() if (v or "").strip() and k.split("|")[1] != "meses"}
    rest = RX_PRICE.sub(" ", RX_QTY.sub(" ", original))
    revisar = [m.group(0) for m in RX_BARE.finditer(rest) if _qty_val(m.group("n")) in olds]
    return text, changed, revisar


def write_prices(out, d, mapa_p, mapa_q, do_cut, pad_ms=120, ignorar=()):
    from plataforma import otimizacao as OT
    only_values=OT.active(out)
    res, ign, prev_ch = [], {int(x) for x in ignorar or []}, False
    for sw in sentences(d.get("words") or []):
        text = " ".join(w["text"] for w in sw)
        new, ch, rev = swap_prices(text, mapa_p, mapa_q)
        # número solto só vira alerta em frase de oferta ou logo depois de uma frase que teve troca de kit
        if rev and not (ch or prev_ch or KIT_CTX.search(text)):
            rev = []
        prev_ch = bool(ch)
        if int(sw[0]["start"]) in ign:
            continue
        if ch or (rev and not only_values):
            res.append({"n": len(res) + 1, "speaker": sw[0].get("speaker") or "A", "start": sw[0]["start"],
                        "end": sw[-1]["end"], "text": text, "novo": new, "trocas": ch,
                        "revisar": [f"“{r}” pode ser quantidade de kit — confira" for r in rev]})
    n = len(res)
    nrev = sum(1 for r in res if r["revisar"])
    resumo = (f"[TROCA DE PREÇOS E KITS]\n\nQuantas frases: {n}\n\nTempo estimado: {math.ceil(n / 15) + 1 if n else 0} horas"
              + (f"\n\nPara revisar à mão: {nrev}" if nrev else ""))
    (out / "precos_TROCA.txt").write_text(resumo + "\n\n" + "\n".join(f"{r['n']}. {r['text']}" for r in res) + "\n")
    (out / "precos_TROCA_NOVO.txt").write_text("\n".join(f"{r['n']}. [Speaker {r['speaker']}] {r['novo']}" for r in res) + "\n")
    src = next(iter(out.glob("_fonte.*")), None)
    aviso = None
    if do_cut and res:
        if src:
            folder = out / "FRASES_PRECOS"
            if folder.exists():
                shutil.rmtree(folder)
            folder.mkdir()
            for r in res:
                name = f"{r['n']:03d}_speaker{r['speaker']}_{ts_short(r['start'])}.mp3"
                cut_wav_then_mp3(src, r["start"], r["end"], folder / name, pad_ms)
                r["file"] = f"FRASES_PRECOS/{name}"
        else:
            aviso = "Esta transcrição é antiga e não guardou o áudio original — transcreva de novo para cortar as frases."
    (out / "precos_TROCA.json").write_text(json.dumps({"mapa_precos": mapa_p, "mapa_qtd": mapa_q, "resumo": resumo,
                                                      "frases": res}, ensure_ascii=False, indent=2))
    return res, resumo, aviso


# ---------------------------------------------------------------- alinhar com a timeline do Premiere
def parse_srt(text):
    cues = []
    for b in re.split(r"\n\s*\n", text.replace("\r", "").strip()):
        ls = [l for l in b.strip().split("\n") if l.strip()]
        k = next((i for i, l in enumerate(ls) if "-->" in l), None)
        if k is None:
            continue
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", ls[k])
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        a = ((g[0] * 60 + g[1]) * 60 + g[2]) * 1000 + g[3]
        z = ((g[4] * 60 + g[5]) * 60 + g[6]) * 1000 + g[7]
        txt = re.sub(r"<[^>]+>|\[[^\]]*\]", " ", " ".join(ls[k + 1:]))
        cues.append((a, z, txt))
    return cues


def srt_word_stream(cues):
    toks, times = [], []
    for a, z, txt in cues:
        ws = txt.split()
        tot = sum(len(w) for w in ws) or 1
        cum = 0
        for w in ws:
            n = norm(w)
            mid = a + (cum + len(w) / 2) / tot * (z - a)
            cum += len(w)
            if n:
                toks.append(n); times.append(mid)
    return toks, times


def tc(ms, fps):
    """Timecode HH:MM:SS:FF (com drop-frame ';' para 29.97/59.94)."""
    drop = abs(fps - 29.97) < 0.01 or abs(fps - 59.94) < 0.01
    nom = round(fps)
    frames = int(round(ms / 1000 * fps))
    if drop:
        d = 2 if nom == 30 else 4
        per10, per1 = nom * 600 - d * 9, nom * 60 - d
        q, r = divmod(frames, per10)
        frames += d * 9 * q + (d * ((r - d) // per1) if r > d else 0)
    f = frames % nom; sec = frames // nom
    sep = ";" if drop else ":"
    return f"{sec//3600:02d}:{sec//60%60:02d}:{sec%60:02d}{sep}{f:02d}"


def align_to_timeline(d, phrases, srt_text, fps):
    cues = parse_srt(srt_text)
    if not cues:
        raise ValueError("Não consegui ler esse .srt (confira se é o arquivo exportado do Premiere).")
    s_tok, s_t = srt_word_stream(cues)
    words = [w for w in d["words"] if norm(w["text"])]
    a_tok = [norm(w["text"]) for w in words]
    a_mid = [(w["start"] + w["end"]) / 2 for w in words]
    sm = SequenceMatcher(None, a_tok, s_tok, autojunk=False)
    pairs = []  # (índice da palavra no áudio, offset timeline - áudio em ms)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            pairs.append((blk.a + k, s_t[blk.b + k] - a_mid[blk.a + k]))
    pairs.sort()
    import bisect, statistics
    idx = [p[0] for p in pairs]
    out = []
    for ph in phrases:
        i0 = next((i for i, w in enumerate(words) if w["start"] >= ph["start"] - 2), 0)
        i1 = max(i for i, w in enumerate(words) if w["end"] <= ph["end"] + 2)
        inside = [o for i, o in pairs[bisect.bisect_left(idx, i0):bisect.bisect_right(idx, i1)]]
        conf = len(inside) / max(1, i1 - i0 + 1)
        if inside:
            off = statistics.median(inside)
        else:  # frase não achada no SRT: usa o deslocamento do trecho vizinho mais próximo
            j = bisect.bisect_left(idx, i0)
            near = [pairs[k][1] for k in (j - 1, j) if 0 <= k < len(pairs)]
            off = near[0] if len(near) == 1 else min(near, key=lambda o: abs(o)) if near else 0
        t_in, t_out = ph["start"] + off, ph["end"] + off
        status = "ok" if conf >= 0.6 else ("revisar" if conf >= 0.25 else "nao_encontrada")
        out.append({**{k: ph[k] for k in ("n", "speaker", "text") if k in ph}, "novo": ph.get("novo"),
                    "file": ph.get("file"), "audio_in": ph["start"], "audio_out": ph["end"],
                    "tl_in": max(0, round(t_in)), "tl_out": max(0, round(t_out)), "offset_ms": round(off),
                    "tc_in": tc(max(0, t_in), fps), "tc_out": tc(max(0, t_out), fps),
                    "confianca": round(conf, 2), "status": status})
    return out, round(sm.ratio(), 3)


def jsx_premiere(items):
    data = json.dumps([{"n": i["n"], "inS": round(i["tl_in"] / 1000, 3), "outS": round(i["tl_out"] / 1000, 3),
                        "label": f"TROCA {i['n']:03d} · {i['text'][:60]}", "novo": i.get("novo") or "",
                        "status": i["status"]} for i in items], ensure_ascii=False)
    return """// ============================================================================
// TROCA DE POTES — gerado pelo Fatiador de Speakers  (ExtendScript para Premiere Pro)
// Abra a SEQUÊNCIA da VSL no Premiere e rode este arquivo.
//
// MODE:
//   "MARCADORES"  -> só cria um marcador com duração em cada frase (não altera nada). COMECE POR AQUI.
//   "CORTAR"      -> corta (razor) o início e o fim de cada frase nas trilhas de áudio CUT_TRACKS.
//   "TROCAR"      -> corta, tira o áudio antigo (sem ripple) e coloca o áudio novo do MiniMax no lugar.
// Faça "Salvar como" do projeto antes de usar CORTAR/TROCAR. Cmd+Z desfaz.
// ============================================================================
var CFG = {
  MODE: "MARCADORES",
  AUDIO_TRACK: 0,          // trilha de áudio que recebe o áudio novo (0 = A1, 1 = A2, ...)
  CUT_TRACKS: [0],         // trilhas de áudio onde o trecho antigo é cortado/removido
  AUDIO_DIR: "",           // pasta com os áudios novos (001_..., 002_...). Vazio = o script pergunta.
  INCLUIR_REVISAR: false,  // true = também processa frases com alinhamento incerto
  TOL: 0.06                // tolerância em segundos para achar o trecho cortado
};
var ITEMS = __DATA__;
var FPS_TC = __FPS__;      // frame rate usado só para montar o timecode do corte

(function () {
  var seq = app.project.activeSequence;
  if (!seq) { alert("Abra a sequência da VSL e rode de novo."); return; }
  var log = [], feitos = 0;
  function pad3(n) { return (n < 10 ? "00" : (n < 100 ? "0" : "")) + n; }
  function p2(x) { return (x < 10 ? "0" : "") + x; }
  function tcOf(sec) {                      // timecode HH:MM:SS:FF (drop-frame em 29.97/59.94)
    var fps = FPS_TC, nom = Math.round(fps), fr = Math.round(sec * fps);
    var drop = (Math.abs(fps - 29.97) < 0.01 || Math.abs(fps - 59.94) < 0.01);
    if (drop) { var d = (nom === 30) ? 2 : 4, per10 = nom * 600 - d * 9, per1 = nom * 60 - d;
      var q = Math.floor(fr / per10), r = fr % per10;
      fr += d * 9 * q + (r > d ? d * Math.floor((r - d) / per1) : 0); }
    var s = Math.floor(fr / nom);
    return p2(Math.floor(s / 3600)) + ":" + p2(Math.floor(s / 60) % 60) + ":" + p2(s % 60) + (drop ? ";" : ":") + p2(fr % nom);
  }
  function usable(it) {
    if (it.status === "nao_encontrada") return false;
    if (it.status === "revisar" && !CFG.INCLUIR_REVISAR) return false;
    return true;
  }

  // ---------------- MARCADORES (sempre) ----------------
  for (var i = 0; i < ITEMS.length; i++) {
    var it = ITEMS[i];
    if (it.status === "nao_encontrada") { log.push(pad3(it.n) + ": não encontrada na timeline (pulada)"); continue; }
    var m = seq.markers.createMarker(it.inS);
    m.name = it.label;
    m.comments = (it.novo ? "NOVO: " + it.novo : "") + (it.status === "revisar" ? "  [REVISAR: alinhamento incerto]" : "");
    try { var t = new Time(); t.seconds = it.outS; m.end = t; } catch (e) {}
    feitos++;
  }

  // ---------------- CORTAR / TROCAR ----------------
  if (CFG.MODE === "CORTAR" || CFG.MODE === "TROCAR") {
    app.enableQE();
    var q = qe.project.getActiveSequence();
    var folder = null;
    if (CFG.MODE === "TROCAR") {
      folder = CFG.AUDIO_DIR ? new Folder(CFG.AUDIO_DIR) : Folder.selectDialog("Escolha a pasta com os áudios novos (001_..., 002_...)");
      if (!folder) { alert("Nenhuma pasta escolhida. Só os marcadores foram criados."); return; }
    }
    var cortadas = 0, trocadas = 0;
    for (var j = ITEMS.length - 1; j >= 0; j--) {      // do fim para o começo: o que já foi feito não desloca o que falta
      var x = ITEMS[j];
      if (!usable(x)) continue;
      // 1) razor no início e no fim, nas trilhas de áudio escolhidas
      var pts = [tcOf(x.inS), tcOf(x.outS)];
      for (var k = 0; k < pts.length; k++)
        for (var c = 0; c < CFG.CUT_TRACKS.length; c++)
          try { q.getAudioTrackAt(CFG.CUT_TRACKS[c]).razor(pts[k]); } catch (e) { log.push(pad3(x.n) + ": razor falhou (" + e + ")"); }
      cortadas++;
      if (CFG.MODE !== "TROCAR") continue;
      // 2) tira o áudio antigo (sem ripple) nas trilhas de corte
      for (var c2 = 0; c2 < CFG.CUT_TRACKS.length; c2++) {
        var tr = seq.audioTracks[CFG.CUT_TRACKS[c2]];
        for (var n = tr.clips.numItems - 1; n >= 0; n--) {
          var ci = tr.clips[n];
          if (ci.start.seconds >= x.inS - CFG.TOL && ci.end.seconds <= x.outS + CFG.TOL) { try { ci.remove(false, false); } catch (e) { log.push(pad3(x.n) + ": não removeu o trecho antigo"); } }
        }
      }
      // 3) acha o áudio novo, importa e coloca no ponto de entrada
      var files = folder.getFiles(pad3(x.n) + "_*");
      var f = null;
      for (var z = 0; z < files.length; z++) if (/\\.(mp3|wav|m4a|aif|aiff)$/i.test(files[z].name)) { f = files[z]; break; }
      if (!f) { log.push(pad3(x.n) + ": áudio novo não encontrado na pasta"); continue; }
      app.project.importFiles([f.fsName], true, app.project.getInsertionBin(), false);
      var item = null, kids = app.project.rootItem.children;
      for (var y = kids.numItems - 1; y >= 0; y--) if (kids[y].name === f.name || kids[y].name === f.name.replace(/\\.[^.]+$/, "")) { item = kids[y]; break; }
      if (!item) { log.push(pad3(x.n) + ": não consegui importar " + f.name); continue; }
      var dest = seq.audioTracks[CFG.AUDIO_TRACK];
      try { dest.overwriteClip(item, x.inS); } catch (e1) { try { var tt = new Time(); tt.seconds = x.inS; dest.overwriteClip(item, tt); } catch (e2) { log.push(pad3(x.n) + ": não colocou o áudio novo"); continue; } }
      try { var dur = item.getOutPoint().seconds - item.getInPoint().seconds; if (dur > (x.outS - x.inS) + 0.25) log.push(pad3(x.n) + ": áudio novo é " + (dur - (x.outS - x.inS)).toFixed(1) + "s mais longo que o espaço (pode cobrir o trecho seguinte)"); } catch (e3) {}
      trocadas++;
    }
    log.unshift("Marcadores: " + feitos + " | cortadas: " + cortadas + (CFG.MODE === "TROCAR" ? " | áudios trocados: " + trocadas : ""));
  } else {
    log.unshift("Marcadores criados: " + feitos + " (nenhum corte feito; troque CFG.MODE para CORTAR ou TROCAR).");
  }
  $.writeln(log.join("\\n"));
  alert(log.join("\\n"));
})();
""".replace("__DATA__", data)


# ---------------------------------------------------------------- pipeline
def transcribe(jid, src, lang, speakers, keyterms=()):
    key = api_key()
    h = {"authorization": key}

    set_state(jid, step="Enviando arquivo para o AssemblyAI…", pct=5)
    with open(src, "rb") as f:
        r = requests.post(f"{API}/upload", headers=h, data=f, timeout=600)
    r.raise_for_status()
    url = r.json()["upload_url"]

    payload = {"audio_url": url, "speaker_labels": True, "punctuate": True, "format_text": True}
    if keyterms:
        payload["keyterms_prompt"] = list(keyterms)
    if lang and lang != "auto":
        payload["language_code"] = lang
    else:
        payload["language_detection"] = True
    if speakers:
        payload["speakers_expected"] = int(speakers)
    else:
        # sem número informado: exige pelo menos 2 vozes, senão áudios com narrador dominante
        # (depoimentos curtos) saem como um speaker só
        payload["speaker_options"] = {"min_speakers_expected": 2, "max_speakers_expected": 10}
    r = requests.post(f"{API}/transcript", headers={**h, "content-type": "application/json"},
                      json=payload, timeout=60)
    r.raise_for_status()
    tid = r.json()["id"]

    t0 = time.time()
    while True:
        r = requests.get(f"{API}/transcript/{tid}", headers=h, timeout=60)
        r.raise_for_status()
        d = r.json()
        if d["status"] == "completed":
            return d
        if d["status"] == "error":
            raise RuntimeError(f"AssemblyAI: {d.get('error')}")
        el = int(time.time() - t0)
        set_state(jid, step=f"Transcrevendo e separando speakers… ({el}s)",
                  pct=min(10 + el // 3, 60))
        time.sleep(3)


def build_srt(utts, max_chars=84, max_ms=6000):
    """Legendas a partir das palavras de cada fala, quebrando por tamanho/tempo/pontuação."""
    cues = []
    for u in utts:
        cur = []
        for w in u.get("words", []):
            cur.append(w)
            text = " ".join(x["text"] for x in cur)
            dur = cur[-1]["end"] - cur[0]["start"]
            if len(text) >= max_chars or dur >= max_ms or re.search(r"[.?!]$", w["text"]) and len(text) > 25:
                cues.append((cur[0]["start"], cur[-1]["end"], u["speaker"], text)); cur = []
        if cur:
            cues.append((cur[0]["start"], cur[-1]["end"], u["speaker"], " ".join(x["text"] for x in cur)))
    out = []
    for i, (a, b, spk, t) in enumerate(cues, 1):
        out.append(f"{i}\n{ts_srt(a)} --> {ts_srt(b)}\n[{spk}] {t}\n")
    return "\n".join(out)


def split_utt(u, max_ms):
    """Divide uma fala em trechos de no máximo max_ms, cortando de preferência no fim de frase
    ou na maior pausa; nunca no meio de uma palavra. max_ms<=0 => fala inteira."""
    words = u.get("words") or []
    whole = [{"speaker": u["speaker"], "start": u["start"], "end": u["end"], "text": u["text"]}]
    if max_ms <= 0 or u["end"] - u["start"] <= max_ms or not words:
        return whole
    pieces, i = [], 0
    while i < len(words):
        start = words[i]["start"]
        if words[-1]["end"] - start <= max_ms:
            j = len(words)
        else:
            lim = max(k for k in range(i, len(words)) if words[k]["end"] - start <= max_ms) if words[i]["end"] - start <= max_ms else i
            cand = range(i, lim + 1)
            half = [k for k in cand if words[k]["end"] - start >= max_ms * 0.5]
            sent = [k for k in half if re.search(r"[.?!]$", words[k]["text"])]
            if sent:
                k = sent[-1]
            elif half and lim + 1 < len(words):
                k = max(half, key=lambda k: words[k + 1]["start"] - words[k]["end"] if k + 1 < len(words) else 0)
            else:
                k = lim
            j = k + 1
        seg = words[i:j]
        pieces.append({"speaker": u["speaker"], "start": seg[0]["start"], "end": seg[-1]["end"],
                       "text": " ".join(w["text"] for w in seg)})
        i = j
    if len(pieces) > 1 and pieces[-1]["end"] - pieces[-1]["start"] < 1500:  # sobra minúscula: cola no anterior
        last = pieces.pop(); pieces[-1]["end"] = last["end"]; pieces[-1]["text"] += " " + last["text"]
    return pieces


def cut(src, a_ms, b_ms, dst, pad_ms):
    a = max(0, a_ms - pad_ms) / 1000
    b = (b_ms + pad_ms) / 1000
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(src),
                    "-vn", "-ac", "2", "-ar", "44100", "-c:a", "libmp3lame", "-q:a", "2", str(dst)],
                   check=True)


def concat(files, dst):
    lst = dst.with_suffix(".txt")
    lst.write_text("".join(f"file '{str(f).replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n" for f in files))
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c:a", "libmp3lame", "-q:a", "2", str(dst)], check=True)
    lst.unlink()


def run_job(jid, src, orig_name, lang, speakers, pad_ms, min_ms, max_ms=0, prod=None, second_half=False, studio_started=None):
    started_studio = studio_started or time.time()
    notification_start = time.monotonic()
    notification_status = 'erro'
    try:
        set_state(jid, step="Extraindo somente o áudio da segunda metade…" if second_half else "Extraindo somente o áudio do arquivo inteiro…", pct=3)
        asr_src, selection = RECORTE.prepare(src, FFMPEG, PLATAFORMA.M.FFPROBE, second_half)
        set_state(jid, recorte_transcricao=selection)
        from plataforma.mencoes import names as product_names
        hints = (prod or {})
        terms = [] if hints.get('otimizacao') else product_names(hints.get('product'), hints.get('aliases'))
        terms = list({t.casefold(): t for t in reversed(terms[:20]) if 3 <= len(t) <= 50}.values())
        raw = transcribe(jid, asr_src, lang, speakers, keyterms=terms) if terms else transcribe(jid, asr_src, lang, speakers)
        d = RECORTE.restore_times(raw, selection)
        from plataforma import projetos as PROJ
        project_name = ((prod or {}).get('projeto') or Path(orig_name).stem).strip()
        product_name = (prod or {}).get('novo') or (prod or {}).get('product') or ''
        out = STORAGE.current("fatiador") / PROJ.folder_name(project_name, product_name)
        out.mkdir(parents=True)
        PROJ.create_meta(out, project_name, (prod or {}).get('product', ''), (prod or {}).get('novo', ''))
        if prod and prod.get("otimizacao"):
            from plataforma import otimizacao as OT
            OT.prepare(out,prod["product"])
        if prod and 'nomenclatura' in prod:
            from plataforma import identidade_entrega as ID
            ID.save(out,prod['nomenclatura'])
            EQUIPE_API.project_created(out,prod.get('editor_profile'),prod['nomenclatura']['editor'])
        utts = d.get("utterances") or []
        if not utts:
            raise RuntimeError("A transcrição voltou sem separação de speakers (áudio curto ou sem fala?).")

        set_state(jid, step="Salvando transcrição…", pct=65)
        from plataforma.diagnostico import atomic_text
        atomic_text(out / "transcricao_bruta.json", json.dumps(d, ensure_ascii=False, indent=2))
        atomic_text(out / "transcricao_speakers.txt",
            "\n\n".join(f"[{ts_short(u['start'])}] [Speaker {u['speaker']}] {u['text']}" for u in utts))
        atomic_text(out / "transcricao_texto_corrido.txt", d.get("text") or "")
        atomic_text(out / "legendas.srt", build_srt(utts))

        # decodifica uma vez para WAV: corte preciso e sem erro do encoder no fim do arquivo
        set_state(jid, step="Preparando áudio para os cortes…", pct=66)
        wav = src.with_suffix(".work.wav")
        subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(asr_src), "-vn", "-ac", "1", "-ar", "24000",
                        "-c:a", "pcm_s16le", str(wav)], check=True)

        speakers_found = sorted({u["speaker"] for u in utts})
        pieces = [p for u in utts for p in split_utt(u, max_ms)]
        clips, total = [], len(pieces)
        per_spk = {s: [] for s in speakers_found}
        for i, u in enumerate(pieces, 1):
            set_state(jid, step=f"Fatiando trechos… {i}/{total}", pct=65 + int(30 * i / total))
            if u["end"] - u["start"] < min_ms:
                continue
            folder = out / f"SPEAKER_{u['speaker']}"
            folder.mkdir(exist_ok=True)
            name = f"{i:03d}_{ts_short(u['start'])}_{slug(u['text'])}.mp3"
            cut(wav, max(0, u["start"] - selection["inicio_ms"]), max(0, u["end"] - selection["inicio_ms"]), folder / name, pad_ms)
            per_spk[u["speaker"]].append(folder / name)
            clips.append({"n": i, "speaker": u["speaker"], "start": u["start"], "end": u["end"],
                          "text": u["text"], "file": f"SPEAKER_{u['speaker']}/{name}"})

        frases, resumo_f, detectado = None, None, None
        shutil.move(str(src), str(out / f"_fonte{src.suffix}"))
        if prod is not None and not prod.get("otimizacao") and not prod.get("product"):
            set_state(jid, step="Identificando o produto original…", pct=93)
            detectado = detect_product(d)
            ambiguous = detectado and any(
                candidate['mencoes'] * 3 >= detectado['mencoes'] * 2 for candidate in detectado['alternativas']
            )
            if detectado and prod.get('automatico') and ambiguous:
                detectado['confirmar'] = True
            if detectado and not detectado.get('confirmar'):
                prod = {**prod, "product": detectado["product"], "aliases": detectado["aliases"]}
        if prod and prod.get("otimizacao"):
            frases=[]
            resumo_f="Otimização de preços e kits: informe os valores novos na etapa Falas. Menções ao produto não foram buscadas."
        elif prod and prod.get("product"):
            set_state(jid, step="Achando as frases com o nome do produto…", pct=94)
            frases, resumo_f = write_phrases(
                out, d, prod["product"], prod.get("aliases", ""), prod.get("novo", ""), prod.get("cut", True), pad_ms,
                progress=lambda i, n: set_state(jid, step=f"Cortando frases do produto… {i}/{n}"))

        set_state(jid, step="Juntando as falas de cada speaker…", pct=96)
        summary = []
        for s, files in per_spk.items():
            dur = sum(c["end"] - c["start"] for c in clips if c["speaker"] == s)
            entry = {"speaker": s, "falas": len(files), "duracao_s": round(dur / 1000, 1), "completo": None}
            if files:
                dst = out / f"SPEAKER_{s}_TODAS_AS_FALAS.mp3"
                concat(files, dst)
                entry["completo"] = dst.name
            summary.append(entry)
        (out / "resumo.json").write_text(json.dumps({"arquivo": orig_name, "idioma": d.get("language_code"),
                                                     "speakers": summary, "falas": clips, "recorte_transcricao": selection},
                                                    ensure_ascii=False, indent=2))
        from plataforma import studio as STUDIO
        STUDIO.create(out, started_studio)
        # Falhas da busca visual não podem converter uma transcrição concluída em erro.
        from plataforma import deteccao_visual as DV, trocas as TROCAS
        try:
            DV.write(out, DV.load(out) | {'automatico': (prod or {}).get('auto_visual', True)})
            if prod and not prod.get('otimizacao') and prod.get('product'):
                if not TROCAS.plan_path(out).exists(): TROCAS.build(out, prod['product'])
                if not prod.get('automatico'):DV.automatic(out, prod.get('auto_visual', True))
        except Exception as visual_error:
            from plataforma.diagnostico import redact
            DV.write(out, DV.load(out) | {'auto_erro': redact(str(visual_error))})
        if prod and prod.get('automatico'):
            from plataforma import automatico as AUTO
            try:AUTO.initialize(out, prod['automatico'], prod.get('product'))
            except (OSError, ValueError):
                # A transcrição e a configuração já foram salvas. O projeto pode retomar pela interface.
                pass
        set_state(jid, status="done", step="Pronto!", pct=100, folder=out.name,
                  language=d.get("language_code"), speakers=summary, clips=clips,
                  frases=frases, resumo_frases=resumo_f, produto=(prod or {}).get("product"),
                  produto_aliases=(prod or {}).get("aliases"), detectado=detectado,
                  produto_novo=(prod or {}).get("novo"),
                  duration=round((d.get("audio_duration") or 0)), recorte_transcricao=selection, metricas=RECORTE.metrics(frases or [], selection["duracao_original_s"]))
        notification_status = 'concluido'
        if (prod or {}).get('editor_profile'):
            try:
                from plataforma import relatorio_ripagem
                relatorio_ripagem.record_operation(out, jid, 'transcricao', notification_status, time.monotonic() - notification_start)
            except OSError:
                pass
    except Exception as e:  # noqa: BLE001
        set_state(jid, status="error", step=str(e), pct=100)
    finally:
        for f in (src, src.with_suffix(".work.wav"), src.with_suffix(".transcricao.mp3")):
            try:
                f.unlink()
            except OSError:
                pass
        if not (prod or {}).get('automatico') or notification_status == 'erro':
            from plataforma import notificacoes
            notificacoes.finished('Transcrição e separação de falas', notification_status, time.monotonic() - notification_start)


# ---------------------------------------------------------------- servidor
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        notice = getattr(self, '_task_notice', None)
        if notice:
            self._task_notice = None
            from plataforma import notificacoes
            title, start = notice
            notificacoes.finished(title, 'concluido' if 200 <= code < 300 else 'erro', time.monotonic() - start, body)
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def local_request(self):
        from plataforma.diagnostico import local_request
        if local_request(self.headers, self.server.server_address[1]):return True
        self.send(403, {"erro": "Acesso permitido somente pelo próprio Ripagem Maker neste computador."})
        return False

    def do_GET(self):
        if not self.local_request():return
        p = urlparse(self.path)
        if EQUIPE_API.handle(self, 'GET', p.path):return
        if not EQUIPE_API.authorize(self, 'GET', p.path):return
        from plataforma import ferramentas_api as FERR
        if FERR.handle(self, "GET", lambda: list(JOBS.values())):return
        if p.path == '/api/limpeza':
            from plataforma import limpeza
            return self.send(200,limpeza.status())
        if p.path == '/api/integracoes':
            from plataforma import credenciais
            return self.send(200,credenciais.overview())
        if p.path == '/api/atualizacoes/disponivel':
            from plataforma import atualizacoes, equipe_auth
            try:
                return self.send(200, atualizacoes.available())
            except equipe_auth.AuthError as error:
                return self.send(error.status_code, {'erro': str(error)})
            except ValueError as error:
                return self.send(502, {'erro': str(error)})
        if p.path == '/api/versao':
            from plataforma import atualizacoes
            return self.send(200,atualizacoes.status(runtime=RUNTIME_VERSION))
        if p.path == '/api/assembly-chave':
            from plataforma import credenciais
            return self.send(200,credenciais.status())
        if p.path == "/api/ajustes":
            return self.send(200, STORAGE.status())
        if p.path.startswith('/fatiador/visual-media/'):
            try:
                from plataforma import visuais as VIS
                parts=unquote(p.path[len('/fatiador/visual-media/'):]).split('/')
                if len(parts)!=2:raise ValueError('Material inválido.')
                out=STORAGE.job_folder(parts[0])
                if not STORAGE.is_job(out):raise ValueError('Trabalho não encontrado.')
                state=VIS.load(out);asset=next((a for a in state['assets'] if a['id']==parts[1]),None)
                if not asset:raise ValueError('Material não encontrado.')
                file=Path(asset['path']).resolve()
                if not file.is_relative_to(Path(state['root']).resolve()) or not file.is_file():raise ValueError('Material indisponível.')
                return PLATAFORMA._send_file(self,file)
            except (ValueError,KeyError,TypeError) as e:return self.send(404,{'erro':str(e)})
        if p.path == "/fatiador/salvos":
            folders = list(dict.fromkeys(d.name for d in sorted((d for root in STORAGE.roots("fatiador") if root.exists() for d in root.iterdir()), key=lambda d: d.stat().st_mtime, reverse=True)
                       if d.is_dir() and (d / "transcricao_bruta.json").exists() and (d / "resumo.json").exists()))
            details=[]
            from plataforma import trocas as T
            for name in folders[:12]:
                out=STORAGE.job_folder(name)
                try:
                    plan=T.load(out);selected=[r for r in plan['itens'] if r.get('aprovado')];ready=bool(selected) and all(r.get('audio',{}).get('aprovado') for r in selected)
                    details.append({'pasta':name,'produto':plan.get('produto_novo') or plan.get('produto'),'atualizado':out.stat().st_mtime,'etapa':'Takes / entrega' if ready else 'Falas'})
                except (OSError,ValueError,KeyError):details.append({'pasta':name,'produto':name,'etapa':'Transcrição'})
            return self.send(200, {"pastas": folders,"trabalhos":details})
        if p.path == "/fatiador":
            return self.send(200, (BASE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if p.path == "/api/desktop/status":
            from plataforma import ml_core as _desktop_jobs
            active = sum(j.get("status") in ("running", "queued", "processando", "fila") for j in list(JOBS.values()))
            active += sum(j.status in ("na_fila", "fila", "executando", "running", "queued", "processando") for j in list(_desktop_jobs.JOBS.values()))
            from plataforma import atualizacoes
            return self.send(200, {"ativas": active, "atualizacao_pendente": atualizacoes.PENDING})
        if PLATAFORMA.handle(self, "GET"):
            return
        if p.path.startswith("/status/"):
            jid = p.path.split("/")[-1]
            return self.send(200, JOBS.get(jid, {"status": "error", "step": "job não encontrado"}))
        if p.path.startswith("/fatiador/baixar-projeto/"):
            try:
                out = STORAGE.job_folder(unquote(p.path.rsplit("/",1)[1]))
                if not STORAGE.is_job(out):
                    return self.send(404, {"erro": "Projeto não encontrado."})
                target = out.parent / (out.name + ".zip")
                tmp = target.with_name("." + uuid.uuid4().hex + ".zip.tmp")
                try:
                    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as z:
                        for entry in out.rglob("*"):
                            if entry.is_file() and not entry.is_symlink() and entry.resolve().is_relative_to(out.resolve()):
                                z.write(entry, entry.relative_to(out))
                    tmp.replace(target)
                finally:
                    tmp.unlink(missing_ok=True)
                return PLATAFORMA._send_file(self, target, download=True)
            except (ValueError, OSError) as e:
                return self.send(400, {"erro": "Não foi possível preparar o ZIP do projeto: " + str(e)})
        if p.path.startswith("/files/"):
            rel = unquote(p.path[len("/files/"):])
            f = STORAGE.resolve("fatiador",rel)
            if not any(f.is_relative_to(root) for root in STORAGE.roots("fatiador")) or not f.is_file():
                return self.send(404, {"erro": "não encontrado"})
            return PLATAFORMA._send_file(self,f,download='dl=1' in (p.query or ''))
        if p.path.startswith("/open/"):
            rel = unquote(p.path[len("/open/"):])
            f = STORAGE.resolve("fatiador",rel)
            if not any(f.is_relative_to(root) for root in STORAGE.roots("fatiador")) or not f.exists():return self.send(404,{'erro':'Pasta ou arquivo não encontrado: '+str(f)})
            try:
                from plataforma.sistema import abrir
                abrir(f)
                return self.send(200,{'ok':True,'arquivo':str(f)})
            except OSError:return self.send(400,{'erro':'Não foi possível abrir. Copie o caminho: '+str(f)})
        self.send(404, {"erro": "rota inválida"})

    def do_POST(self):
        if not self.local_request():return
        p = urlparse(self.path)
        if EQUIPE_API.handle(self, 'POST', p.path):return
        if not EQUIPE_API.authorize(self, 'POST', p.path):return
        from plataforma import atualizacoes, notificacoes
        if p.path in notificacoes.SYNC_TASKS:
            self._task_notice = (notificacoes.SYNC_TASKS[p.path], time.monotonic())
        if atualizacoes.PENDING:return self.send(409,{'erro':'Atualização aplicada. Feche e abra o aplicativo antes de continuar.'})
        if p.path == '/upload/check':
            from plataforma.uploads import check
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 1024:raise ValueError('Consulta de envio inválida. Selecione o arquivo novamente.')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):raise ValueError('Consulta de envio inválida.')
                return self.send(200, check(body.get('bytes'), UPLOADS))
            except (ValueError, TypeError, OSError) as error:
                return self.send(400, {'erro': str(error)})
        if p.path in ('/api/atualizar', '/api/atualizacoes/instalar'):
            from plataforma import equipe_auth, limpeza
            try:
                expected = None
                size = int(self.headers.get('Content-Length', 0))
                if p.path.endswith('/instalar'):
                    if not 0 < size <= 1024:
                        raise ValueError('Informe a versão disponível.')
                    body = json.loads(self.rfile.read(size))
                    expected = body.get('versao') if isinstance(body, dict) else None
                    atualizacoes.number(expected)
                    if limpeza.active(legacy=JOBS.values()) or STORAGE.MAINTENANCE:
                        return self.send(409, {'erro': 'Aguardando as tarefas terminarem.', 'aguardar': True})
                    data = atualizacoes.fetch_available(expected)
                else:
                    if not 0 < size <= atualizacoes.MAX_BYTES:
                        raise ValueError('Escolha um ZIP de atualização com até 25 MB.')
                    data = self.rfile.read(size)
                    if len(data) != size:
                        raise ValueError('Upload incompleto.')
                with STORAGE.LOCK:
                    if atualizacoes.PENDING:
                        return self.send(409, {'erro': 'Reabra o aplicativo para concluir a atualização.'})
                    if STORAGE.MAINTENANCE or limpeza.active(legacy=JOBS.values()):
                        return self.send(409, {'erro': 'Aguardando as tarefas terminarem.', 'aguardar': True})
                    STORAGE.MAINTENANCE = True
                    try:
                        result = atualizacoes.apply(data, expected=expected)
                    finally:
                        STORAGE.MAINTENANCE = False
                return self.send(200, result)
            except equipe_auth.AuthError as error:
                return self.send(error.status_code, {'erro': str(error)})
            except (ValueError, OSError) as error:
                return self.send(400, {'erro': str(error)})

        if STORAGE.MAINTENANCE and not (p.path.startswith('/api/ml/job/') and p.path.endswith('/cancelar')):
            return self.send(409,{'erro':'A limpeza está em andamento. Aguarde antes de iniciar ou alterar trabalhos.'})
        if p.path in ('/api/limpeza/analisar','/api/limpeza/executar'):
            from plataforma import limpeza
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size>4096:raise ValueError('Solicitação inválida.')
                body=json.loads(self.rfile.read(size) or b'{}')
                with STORAGE.LOCK:
                    if limpeza.active(legacy=JOBS.values()):raise ValueError('Aguarde as tarefas em andamento antes de analisar ou limpar.')
                    def clean(job):
                        return limpeza.maintenance(job,lambda:limpeza.analyze(job) if p.path.endswith('/analisar') else limpeza.execute(job,body.get('token')),lambda:list(JOBS.values()))
                    job=PLATAFORMA.M.submit('limpeza','Analisar espaço' if p.path.endswith('/analisar') else 'Limpeza segura de materiais',clean,'render')
                return self.send(200,job.to_dict())
            except (ValueError,OSError) as e:return self.send(400,{'erro':str(e)})
        if p.path == '/api/integracoes':
            from plataforma import credenciais as C
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=2048:raise ValueError('Solicitação inválida.')
                data=json.loads(self.rfile.read(size));provider=data.get('servico');action=data.get('acao')
                if action=='salvar':result=C.save(data.get('chave'),provider)
                elif action=='remover':
                    result=C.remove(provider)
                    from plataforma import vozes
                    with vozes.KEY_LOCK:vozes.KEYS.pop(provider,None)
                elif action=='testar':result=C.test(provider)
                else:raise ValueError('Escolha salvar, remover ou testar.')
                return self.send(200,result)
            except (ValueError,RuntimeError,OSError) as e:return self.send(400,{'erro':str(e)})
        if p.path == '/api/assembly-chave':
            from plataforma import credenciais
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=2048:return self.send(400,{'erro':'Requisição inválida.'})
                body=json.loads(self.rfile.read(size))
                return self.send(200,credenciais.save(body.get('chave')))
            except (ValueError,RuntimeError,OSError):
                return self.send(400,{'erro':'Não foi possível salvar. Cole somente a chave do AssemblyAI e confira a permissão de gravação da pasta do app.'})
        if p.path == "/api/ajustes":
            try:
                with STORAGE.LOCK:
                    if any(j.status in ('na_fila','executando') for j in PLATAFORMA.M.JOBS.values()) or any(j.get('status')=='running' for j in JOBS.values()):
                        return self.send(409,{'erro':'Aguarde as tarefas em andamento terminarem antes de mudar a pasta.'})
                    data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or b'{}')
                    result=STORAGE.save_margin(data['margem_fala_ms']) if 'margem_fala_ms' in data else STORAGE.save_visual_margin(data['margem_visual_ms']) if 'margem_visual_ms' in data else STORAGE.save(data.get('pasta_principal',''))
                    PLATAFORMA.M.OUT_DIR=STORAGE.current('montagens');PLATAFORMA.M.VID_DIR=STORAGE.current('videos')
                    return self.send(200,result)
            except (ValueError,OSError) as e:return self.send(400,{'erro':str(e)})
        from plataforma import ferramentas_api as FERR
        if FERR.handle(self, "POST", lambda: list(JOBS.values())):return
        if p.path.startswith("/api/") and PLATAFORMA.handle(self, "POST"):
            return
        if TROCAS_API.handle(self, p.path, STORAGE.current("fatiador")):
            return
        if p.path == "/fatiador/corrigir-srt":
            try:
                from plataforma import srt_corretor as SRT
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                out = STORAGE.job_folder(body["folder"])
                if not STORAGE.is_job(out):
                    return self.send(404, {"erro": "Trabalho não encontrado. Reabra a transcrição primeiro."})
                text = body.get("srt", "")
                if len(text) > 5_000_000:
                    return self.send(400, {"erro": "SRT muito grande. Limite: 5 milhões de caracteres."})
                SRT.parse(text)
                product = body.get("product", "").strip()
                corrected, report = SRT.product_only(text, product, body.get("novo", "").strip(), body.get("aliases", ""))
                tag = uuid.uuid4().hex[:8]
                stem = slug(Path(body.get("nome", "legendas.srt")).stem, 70)
                filename = f"{stem}_corrigido_{tag}.srt"
                reportname = f"{stem}_correcoes_{tag}.json"
                (out / filename).write_bytes(corrected.encode("utf-8"))
                (out / reportname).write_text(json.dumps(report, ensure_ascii=False, indent=2))
                from plataforma import trocas as T
                if T.plan_path(out).exists():
                    with T.LOCK:
                        plan=T.load(out);plan['validacao_srt']={'arquivo':filename,'relatorio':reportname,'produto':product,'novo':body.get('novo','').strip(),'resquicios':report['resquicios'],'alterados':report['alterados'],'montagem_assinatura':T.preview_signature(out)};T.write(T.plan_path(out),plan)
                return self.send(200, report | {"arquivo": filename, "relatorio": reportname})
            except (ValueError, KeyError) as e:
                return self.send(400, {"erro": str(e)})
            except Exception as e:
                return self.send(500, {"erro": str(e)})
        if p.path == "/fatiador/reabrir":
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                out = STORAGE.job_folder(body["folder"])
                if not STORAGE.is_job(out):
                    return self.send(404, {"erro": "pasta não encontrada"})
                summary = json.loads((out / "resumo.json").read_text())
                raw = json.loads((out / "transcricao_bruta.json").read_text())
                from plataforma import projetos as PROJ
                try:PROJ.write_meta(out, aberto_em=time.time())
                except OSError:pass
                jf = max(out.glob("frases_*.json"), key=lambda f: f.stat().st_mtime, default=None)
                phrases = json.loads(jf.read_text()) if jf else {}
                return self.send(200, {"folder": out.name, "speakers": summary.get("speakers", []),
                    "clips": summary.get("falas", []), "language": raw.get("language_code"),
                    "duration": raw.get("audio_duration", 0), "recorte_transcricao": raw.get("recorte_transcricao"), "produto": phrases.get("produto", ""),
                    "produto_novo": phrases.get("produto_novo", ""), "produto_aliases": phrases.get("produto_aliases", ""), "frases": phrases.get("frases", []),
                    "resumo_frases": phrases.get("resumo", ""), "metricas": RECORTE.metrics(phrases.get("frases", []), float(raw.get("audio_duration") or 0))})
            except Exception as e:
                return self.send(400, {"erro": str(e)})
        if p.path == "/fatiador/premiere":
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                out = STORAGE.job_folder(body["folder"])
                if not STORAGE.is_job(out):
                    return self.send(404, {"erro": "pasta não encontrada"})
                product = body.get("product", "").strip()
                if not product:
                    return self.send(400, {"erro": "Informe o produto e identifique os trechos primeiro."})
                jf = out / ("frases_" + slug(product, 30).upper() + ".json")
                if not jf.exists():
                    return self.send(400, {"erro": "Busque os trechos desse produto antes de exportar."})
                d = json.loads((out / "transcricao_bruta.json").read_text())
                fps = float(body.get("fps") or 30)
                if not math.isfinite(fps) or fps <= 0 or fps > 120:
                    return self.send(400, {"erro": "FPS inválido."})
                result = export_fatiador_premiere(out, d, json.loads(jf.read_text())["frases"], product,
                    body.get("aliases", ""), bool(body.get("precos")), fps)
                return self.send(200, result)
            except Exception as e:
                return self.send(500, {"erro": str(e)})
        if p.path == "/alinhar":
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                out = STORAGE.job_folder(body["folder"])
                if not STORAGE.is_job(out):
                    return self.send(404, {"erro": "pasta não encontrada"})
                fps = float(body.get("fps") or 24)
                jf = max(out.glob("frases_*.json"), key=lambda f: f.stat().st_mtime, default=None)
                if not jf:
                    return self.send(400, {"erro": "Ainda não há lista de frases nessa transcrição. Busque o produto primeiro."})
                phrases = json.loads(jf.read_text())["frases"]
                d = json.loads((out / "transcricao_bruta.json").read_text())
                items, sim = align_to_timeline(d, phrases, body["srt"], fps)
                tag = jf.stem.replace("frases_", "")
                csv = "n,speaker,in,out,duracao_s,status,confianca,texto,texto_novo,arquivo\n" + "\n".join(
                    ",".join('"' + str(v).replace('"', '""') + '"' for v in (
                        i["n"], i["speaker"], i["tc_in"], i["tc_out"], round((i["tl_out"] - i["tl_in"]) / 1000, 2),
                        i["status"], i["confianca"], i["text"], i.get("novo") or "", i.get("file") or "")) for i in items)
                (out / f"timeline_{tag}.csv").write_text(csv, encoding="utf-8-sig")
                nom = round(fps)
                (out / f"premiere_{tag}.jsx").write_text(jsx_premiere(items).replace("__FPS__", str(fps)))
                (out / f"timeline_{tag}.json").write_text(json.dumps(items, ensure_ascii=False, indent=2))
                return self.send(200, {"itens": items, "similaridade": sim, "csv": f"timeline_{tag}.csv",
                                       "jsx": f"premiere_{tag}.jsx"})
            except Exception as e:  # noqa: BLE001
                return self.send(500, {"erro": str(e)})
        if p.path in ("/precos", "/precos/aplicar"):
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                out = STORAGE.job_folder(body["folder"])
                if not STORAGE.is_job(out):
                    return self.send(404, {"erro": "pasta não encontrada"})
                d = json.loads((out / "transcricao_bruta.json").read_text())
                if p.path == "/precos":
                    return self.send(200, detect_prices(d))
                from plataforma import automatico as AUTO
                if AUTO.active(out):return self.send(409, {'erro':'Pause a execução automática antes de alterar os preços.'})
                frases, resumo, aviso = write_prices(out, d, body.get("precos", {}), body.get("quantidades", {}),
                                                     bool(body.get("cut", True)), ignorar=body.get("ignorar", []))
                return self.send(200, {"frases": frases, "resumo": resumo, "aviso": aviso})
            except ValueError as e:
                return self.send(400, {"erro": str(e)})
            except Exception as e:  # noqa: BLE001
                return self.send(500, {"erro": str(e)})
        if p.path == "/frases":
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                out = STORAGE.job_folder(body["folder"])
                if not STORAGE.is_job(out):
                    return self.send(404, {"erro": "pasta não encontrada"})
                d = json.loads((out / "transcricao_bruta.json").read_text())
                from plataforma import otimizacao as OT, automatico as AUTO
                if AUTO.active(out):return self.send(409, {'erro':'Pause a execução automática antes de alterar as falas.'})
                if OT.active(out):
                    return self.send(400, {'erro':'Este trabalho altera somente preços e kits. A busca por menções ao produto está desativada.'})
                frases, resumo = write_phrases(out, d, body["product"].strip(), body.get("aliases", ""),
                                               (body.get("novo") or "").strip(), bool(body.get("cut", True)), 120)
                return self.send(200, {"frases": frases, "resumo": resumo, "metricas": RECORTE.metrics(frases, float(d.get("audio_duration") or 0))})
            except Exception as e:  # noqa: BLE001
                return self.send(500, {"erro": str(e)})
        if p.path != "/upload":
            return self.send(404, {"erro": "rota inválida"})
        name = unquote(self.headers.get("X-Filename", "audio"))
        lang = self.headers.get("X-Lang", "auto")
        spk = self.headers.get("X-Speakers", "")
        pad = int(self.headers.get("X-Pad-Ms", "120") or 120)
        min_ms = int(self.headers.get("X-Min-Ms", "300") or 300)
        max_ms = int(float(self.headers.get("X-Max-S", "0") or 0) * 1000)
        prod = {"projeto": unquote(self.headers.get("X-Projeto", "")).strip()[:80], "product": unquote(self.headers.get("X-Product", "")).strip(),
                "aliases": unquote(self.headers.get("X-Aliases", "")),
                "novo": unquote(self.headers.get("X-New-Product", "")).strip(),
                "cut": self.headers.get("X-Cut-Phrases", "1") == "1", "auto_visual": self.headers.get("X-Auto-Visual", "1") != "0"}
        from plataforma import identidade_entrega as ID
        try:
            prod['nomenclatura']=ID.for_new_project(json.loads(unquote(self.headers.get('X-Nomenclatura','{}'))), self.editor_profile)
            prod['editor_profile']=self.editor_profile
        except (ValueError,TypeError):return self.send(400,{'erro':'Confira os dados da nomenclatura antes de transcrever: número de VSL, copy, editor e pitch manual.'})
        prod["otimizacao"] = self.headers.get("X-Optimization", "0") == "1"
        if prod["otimizacao"]:
            prod["product"] = prod["product"] or prod["novo"] or "Otimização de preços"
            prod["novo"] = prod["product"]
        auto = self.headers.get('X-Ripagem-Automatica')
        if auto is not None:
            from plataforma import automatico as AUTO
            try:
                if len(auto) > 12000:raise ValueError('A configuração do modo automático é muito longa.')
                if not prod['otimizacao'] and not prod['novo']:raise ValueError('Informe o produto novo antes de iniciar.')
                prod['automatico'] = AUTO.validate(json.loads(unquote(auto)), prod['otimizacao'])
            except (ValueError, TypeError, AttributeError, OSError) as error:
                return self.send(400, {'erro': str(error)})
        UPLOADS.mkdir(exist_ok=True)
        dst = UPLOADS / f"{uuid.uuid4().hex}{Path(name).suffix}"
        from plataforma.uploads import receive
        try:
            receive(self.rfile, self.headers.get("Content-Length", 0), dst)
            if auto is not None:
                from plataforma import trocas as T
                if not T.probe(dst)['video']:raise ValueError('Use um vídeo com áudio no modo automático.')
        except (ValueError, OSError, RuntimeError) as error:
            dst.unlink(missing_ok=True)
            return self.send(400, {'erro': str(error)})
        studio_started = time.time()
        try:
            proposed = float(self.headers.get('X-Studio-Start', '0')) / 1000
            if math.isfinite(proposed) and 0 <= studio_started - proposed <= 86400: studio_started = proposed
        except (ValueError, TypeError): pass
        jid = uuid.uuid4().hex[:10]
        with STORAGE.LOCK:
            if STORAGE.MAINTENANCE:
                dst.unlink(missing_ok=True)
                return self.send(409,{'erro':'Aguarde a limpeza terminar antes de transcrever.'})
            JOBS[jid] = {"status": "running", "step": "Arquivo recebido", "pct": 2, "name": name}
            threading.Thread(target=run_job, args=(jid, dst, name, lang, spk, pad, min_ms, max_ms, prod, self.headers.get("X-Second-Half", "0") == "1", studio_started), daemon=True).start()
        self.send(200, {"job": jid})


if __name__ == "__main__":
    OUT_ROOT.mkdir(exist_ok=True)
    try:
        api_key()
    except RuntimeError as e:  # só o fatiador usa a chave; o resto da plataforma é 100% local
        print(f"Aviso: {e} O fatiador vai pedir a chave quando for usado.")
    from plataforma import diagnostico as _DIAG_START
    _DIAG_START.startup()
    # A página carrega ~25 scripts de uma vez; a fila padrão (5) pode recusar conexões e deixar a tela sem parte dos módulos.
    ThreadingHTTPServer.request_queue_size = 64
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    url = f"http://localhost:{PORT}"
    print(f"App rodando em {url}  (Ctrl+C para fechar)", flush=True)
    if not os.environ.get("DRSTUDIO_EMBED"):  # dentro do Ripagem Maker.app a janela é nativa
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
