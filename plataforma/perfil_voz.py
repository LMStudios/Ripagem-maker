"""Assinatura simples de voz (timbre e tom) para conferir a diarização.

Não identifica pessoas: só compara trechos do mesmo vídeo entre si. Serve para
1) avisar quando uma fala parece ser de outro speaker (a diarização errou) e
2) escolher trechos coerentes para a amostra usada na clonagem.
Toda falha de leitura devolve “sem evidência”; nunca bloqueia o fluxo."""
import subprocess

import numpy as np

SR = 16000
_FRAME, _HOP, _NFFT, _BANDS = 400, 160, 512, 26


def _mel_bank():
    mel = lambda f: 2595 * np.log10(1 + f / 700)
    inv = lambda m: 700 * (10 ** (m / 2595) - 1)
    points = inv(np.linspace(mel(80), mel(7600), _BANDS + 2))
    bins = np.floor((_NFFT + 1) * points / SR).astype(int)
    bank = np.zeros((_BANDS, _NFFT // 2 + 1))
    for i in range(_BANDS):
        a, b, c = bins[i], bins[i + 1], bins[i + 2]
        if b > a:
            bank[i, a:b] = (np.arange(a, b) - a) / (b - a)
        if c > b:
            bank[i, b:c] = (c - np.arange(b, c)) / (c - b)
    return bank


_BANK = _mel_bank()
_DCT = np.cos(np.pi / _BANDS * (np.arange(_BANDS) + .5)[None, :] * np.arange(1, 14)[:, None])


def decode(ffmpeg, src, start_s, length_s):
    """Áudio mono 16 kHz de um trecho; None se não puder ler."""
    if length_s <= 0:
        return None
    try:
        raw = subprocess.run([ffmpeg, '-v', 'error', '-ss', f'{max(0, start_s):.3f}', '-t', f'{length_s:.3f}', '-i', str(src),
                              '-map', '0:a:0', '-vn', '-ac', '1', '-ar', str(SR), '-f', 's16le', '-'],
                             capture_output=True, timeout=60, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768 if raw else None


def features(signal):
    """Vetor de timbre (média e variação dos MFCC) + tom (mediana do F0). None se houver pouca fala."""
    if signal is None or len(signal) < SR:
        return None
    count = 1 + (len(signal) - _FRAME) // _HOP
    frames = np.lib.stride_tricks.as_strided(signal, (count, _FRAME), (signal.strides[0] * _HOP, signal.strides[0]))
    frames = frames * np.hamming(_FRAME)
    energy = 10 * np.log10(np.mean(frames ** 2, axis=1) + 1e-10)
    speech = (energy > energy.max() - 30) & (energy > -55)
    if speech.sum() < 40:
        return None
    frames = frames[speech]
    power = np.abs(np.fft.rfft(frames, _NFFT)) ** 2
    logmel = np.log(power @ _BANK.T + 1e-8)
    mfcc = logmel @ _DCT.T
    # Tom: autocorrelação por quadro entre 70 e 400 Hz, só nos quadros com periodicidade clara.
    lo, hi = SR // 400, SR // 70
    spec = np.fft.rfft(frames, 2 * _NFFT)
    ac = np.fft.irfft(np.abs(spec) ** 2)[:, :hi + 1]
    ac = ac / (ac[:, :1] + 1e-10)
    lag = lo + np.argmax(ac[:, lo:hi + 1], axis=1)
    strength = ac[np.arange(len(ac)), lag]
    voiced = strength > .45
    pitch = np.log(SR / np.median(lag[voiced])) if voiced.sum() >= 15 else np.nan
    return np.concatenate([mfcc.mean(0), .5 * mfcc.std(0), [pitch]])


def _scale(vectors):
    data = np.array(vectors)
    filled = np.where(np.isnan(data), np.nanmean(data, axis=0), data)
    std = np.nanstd(filled, axis=0)
    std[~np.isfinite(std) | (std < 1e-6)] = 1
    weights = np.ones(data.shape[1]); weights[-1] = 3  # o tom pesa como três coeficientes de timbre
    return weights / std


def _distance(a, b, scale):
    mask = ~(np.isnan(a) | np.isnan(b))
    return float(np.sqrt(np.mean(((a - b) * scale)[mask] ** 2)))


class Profiles:
    """Centróides por speaker a partir das falas mais longas atribuídas a cada um."""

    def __init__(self, by_speaker):
        self.items = {s: [v for v in vs if v is not None] for s, vs in by_speaker.items()}
        self.items = {s: vs for s, vs in self.items.items() if len(vs) >= 2}
        every = [v for vs in self.items.values() for v in vs]
        self.ok = len(self.items) >= 2 and len(every) >= 4
        if not self.ok:
            return
        self.scale = _scale(every)
        self.center = {s: np.nanmedian(np.array(vs), axis=0) for s, vs in self.items.items()}
        self.spread = {s: max(float(np.median([self.distance(v, s) for v in vs])), .35) for s, vs in self.items.items()}

    def distance(self, vector, speaker):
        return _distance(vector, self.center[speaker], self.scale)

    def suggest(self, vector, assigned):
        """Outro speaker quando a voz do trecho está claramente mais perto dele do que do atribuído."""
        if not self.ok or vector is None or assigned not in self.center:
            return None
        own = self.distance(vector, assigned)
        others = sorted((self.distance(vector, s), s) for s in self.center if s != assigned)
        if not others:
            return None
        best, speaker = others[0]
        if own > 1.8 * self.spread[assigned] and best < .7 * own:
            return speaker
        return None

    def coherent(self, vector, speaker):
        """O trecho combina com a própria voz do speaker (para amostras de clonagem)."""
        if not self.ok or speaker not in self.center:
            return True
        if vector is None:
            return False
        return self.distance(vector, speaker) <= 1.6 * self.spread[speaker] and self.suggest(vector, speaker) is None


def utterance_bounds(u):
    """Início e fim da fala pelas palavras (sem respiro de outra pessoa nas bordas), em segundos."""
    words = [w for w in u.get('words') or [] if 'start' in w and 'end' in w]
    a = words[0]['start'] if words else u['start']
    b = words[-1]['end'] if words else u['end']
    return a / 1000, max(0, b - a) / 1000


def build(ffmpeg, src, utterances, per_speaker=10, cancel=None):
    """Perfis dos speakers + vetores das falas avaliadas, {id(u): vetor}."""
    by_speaker, vectors = {}, {}
    ranked = sorted(utterances, key=lambda u: u['end'] - u['start'], reverse=True)
    for u in ranked:
        speaker = str(u.get('speaker') or '')
        if not speaker or len(by_speaker.setdefault(speaker, [])) >= per_speaker:
            continue
        start, length = utterance_bounds(u)
        if length < 1.5:
            continue
        if cancel and cancel():
            break
        vector = features(decode(ffmpeg, src, start, min(length, 20)))
        vectors[id(u)] = vector
        by_speaker[speaker].append(vector)
    return Profiles(by_speaker), vectors
