#!/usr/bin/env python3
"""
Transcrição LOCAL (sem internet, sem API) — roda como processo separado para poder ser cancelada.

Uso: asr_worker.py <audio_16k_mono.wav> <saida.json> --engine mlx|fw --lang auto|en|pt|... [--cuts 180.2,361.0]
Imprime no stdout linhas "PROGRESS <0..1>" e "STEP <texto>" para o processo pai.

Motores:
  mlx  -> mlx-whisper (large-v3-turbo) na GPU do Apple Silicon. Padrão: mais rápido e mais preciso aqui.
  fw   -> faster-whisper (CPU, int8). Alternativa quando o MLX não está disponível.
"""
import argparse
import json
import sys
import wave

import numpy as np

SR = 16000
MLX_MODEL = "mlx-community/whisper-large-v3-turbo"


def say(kind, value):
    print(f"{kind} {value}", flush=True)


def load_wav(path):
    with wave.open(path, "rb") as w:
        if w.getframerate() != SR or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit("O WAV precisa ser 16 kHz, mono, 16 bits (o app gera assim).")
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def clean_words(words):
    out = []
    for w in words:
        raw = w["w"]
        t = raw.strip()
        if not t:
            continue
        # o Whisper parte palavras em pedaços ("$10" + ",000"); pedaço sem espaço inicial continua a palavra anterior
        if out and not raw[:1].isspace() and w["s"] - out[-1]["e"] < 0.3:
            out[-1]["w"] += t
            out[-1]["e"] = round(max(out[-1]["e"], w["e"]), 3)
            continue
        if w["e"] <= w["s"]:
            continue
        if out and w["s"] < out[-1]["e"]:  # sobreposição mínima entre blocos
            w["s"] = out[-1]["e"]
            if w["e"] <= w["s"]:
                continue
        out.append({"w": t, "s": round(w["s"], 3), "e": round(w["e"], 3), "p": round(w.get("p", 1.0), 3)})
    return out


def run_mlx(audio, lang, cuts):
    import mlx_whisper
    total = len(audio) / SR
    bounds = [0.0] + [c for c in cuts if 0 < c < total] + [total]
    words, detected = [], None
    for k in range(len(bounds) - 1):
        a, b = bounds[k], bounds[k + 1]
        say("STEP", f"Transcrevendo localmente (GPU) — bloco {k + 1}/{len(bounds) - 1}")
        chunk = audio[int(a * SR):int(b * SR)]
        if len(chunk) < SR * 0.3:
            continue
        use_lang = None if (lang == "auto" and detected is None) else (detected or lang)
        r = mlx_whisper.transcribe(chunk, path_or_hf_repo=MLX_MODEL, word_timestamps=True,
                                   language=use_lang, condition_on_previous_text=False, verbose=None)
        detected = detected or r.get("language") or (lang if lang != "auto" else None)
        for seg in r.get("segments", []):
            for w in seg.get("words", []):
                words.append({"w": w["word"], "s": float(w["start"]) + a, "e": float(w["end"]) + a,
                              "p": float(w.get("probability", 1.0))})
        say("PROGRESS", round(b / total, 4))
    return clean_words(words), detected or lang


def run_fw(audio, lang):
    from faster_whisper import WhisperModel
    total = len(audio) / SR
    model_name = "small.en" if lang == "en" else "medium"
    say("STEP", f"Carregando faster-whisper ({model_name}, CPU)")
    m = WhisperModel(model_name, device="cpu", compute_type="int8")
    segs, info = m.transcribe(audio, word_timestamps=True, language=None if lang == "auto" else lang,
                              vad_filter=True)
    words = []
    say("STEP", "Transcrevendo localmente (CPU)")
    for s in segs:
        for w in s.words or []:
            words.append({"w": w.word, "s": float(w.start), "e": float(w.end), "p": float(w.probability)})
        say("PROGRESS", round(min(1.0, s.end / total), 4))
    return clean_words(words), info.language


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("out")
    ap.add_argument("--engine", default="mlx")
    ap.add_argument("--lang", default="auto")
    ap.add_argument("--cuts", default="")
    a = ap.parse_args()
    audio = load_wav(a.wav)
    cuts = [float(x) for x in a.cuts.split(",") if x.strip()]
    engine = a.engine
    if engine == "mlx":
        try:
            import mlx_whisper  # noqa: F401
        except Exception:
            engine = "fw"
            say("STEP", "MLX indisponível — usando faster-whisper (CPU)")
    if engine == "mlx":
        words, lang = run_mlx(audio, a.lang, cuts)
    else:
        words, lang = run_fw(audio, a.lang)
    json.dump({"engine": engine, "model": MLX_MODEL if engine == "mlx" else "faster-whisper",
               "language": lang, "words": words}, open(a.out, "w"), ensure_ascii=False)
    say("PROGRESS", 1.0)
    say("DONE", len(words))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"ERROR {e}", flush=True)
        sys.exit(1)
