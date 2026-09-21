#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zer_speech.py — open-source speech engine for Zer (Amharic + English).

Speech-to-text:  faster-whisper (OpenAI Whisper on CTranslate2) with automatic
                 language detection.

Text-to-speech (human-sounding neural voices, best-first):
    * MMS-TTS   — Meta's neural VITS models; the strong option for **Amharic**
                  (`facebook/mms-tts-amh`) and a solid English voice.
    * Piper     — fast, natural ONNX voices for **English**
                  (en_US-amy / ryan, en_GB-alan).
    * eSpeak NG — small rule-based fallback so audio always works.

A voice is addressed as "<provider>:<id>", e.g. `mms:am`, `piper:en_US-amy-medium`,
`espeak:am+f3`, or simply `auto` to pick the best available for the language.

Env:
    ZER_TTS             auto | mms | piper | espeak | none   (default auto)
    ZER_MMS_AMH_MODEL   default facebook/mms-tts-amh
    ZER_MMS_ENG_MODEL   default facebook/mms-tts-eng
    ZER_WHISPER_MODEL   tiny | base | small | medium | large-v3 (default base)
    HF_HOME             where STT/TTS models are cached (put on the volume)
"""

import io
import os
import re
import shutil
import struct
import subprocess
import tempfile
import threading
import urllib.request
import wave

_lock = threading.RLock()
_whisper = None
_mms_models = {}
_piper_ready = set()
_whisper_failed = False
_mms_fail_count = 0
_mms_error = None
_piper_error = None
_uroman = None
_MMS_MAX_FAILS = int(os.environ.get('ZER_MMS_MAX_FAILS', '3'))

SUPPORTED_LANGS = ('am', 'en')

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _whisper_model_name():
    return os.environ.get('ZER_WHISPER_MODEL', 'base')


def _espeak_bin():
    return shutil.which('espeak-ng') or shutil.which('espeak')


def _romanize(text, lcode='amh'):
    """MMS-TTS expects Latin (uroman-romanized) text for non-Latin scripts."""
    global _uroman
    try:
        if _uroman is None:
            from uroman import Uroman
            _uroman = Uroman()
        return _uroman.romanize_string(text, lcode=lcode)
    except Exception:
        return text


def _mms_ids(lang):
    if lang == 'am':
        return os.environ.get('ZER_MMS_AMH_MODEL', 'facebook/mms-tts-amh')
    return os.environ.get('ZER_MMS_ENG_MODEL', 'facebook/mms-tts-eng')


def _cache_dir(sub):
    base = os.environ.get('HF_HOME') or os.path.join(tempfile.gettempdir(), 'zer-cache')
    path = os.path.join(base, sub)
    os.makedirs(path, exist_ok=True)
    return path


def normalize_lang(code):
    if not code:
        return None
    code = str(code).strip().lower().split('-')[0].split('_')[0]
    if code in ('amh', 'amharic'):
        return 'am'
    if code in ('eng', 'english'):
        return 'en'
    return code or None


# ---------------------------------------------------------------------------
# speech-to-text
# ---------------------------------------------------------------------------
_PROMPTS = {
    'am': 'ሰላም። እንዴት ነህ? እኔ ዘር ነኝ።',
    'en': 'Hello. How are you? I am Zer.',
}


def detect_spoken_language(text, fallback=None):
    """Amharic (Ge'ez) and English use different scripts, so the transcript's
    script is a near-perfect language signal. Falls back to Whisper's guess."""
    am = sum(1 for c in text if '\u1200' <= c <= '\u137f')
    en = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    if am and am >= en:
        return 'am'
    if en and en > am:
        return 'en'
    return fallback


def _load_whisper():
    global _whisper, _whisper_failed
    with _lock:
        if _whisper is not None or _whisper_failed:
            return _whisper
        try:
            from faster_whisper import WhisperModel
            _whisper = WhisperModel(
                _whisper_model_name(),
                device=os.environ.get('ZER_WHISPER_DEVICE', 'cpu'),
                compute_type=os.environ.get('ZER_WHISPER_COMPUTE', 'int8'),
            )
        except Exception:
            _whisper_failed = True
            _whisper = None
        return _whisper


def stt_available():
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return _whisper is not None


def transcribe_bytes(data, filename='audio.webm', language=None):
    """Transcribe an audio blob and return {text, language, …}."""
    if not data:
        return {'error': 'empty audio'}
    model = _load_whisper()
    if model is None:
        return {'error': 'speech-to-text unavailable (install faster-whisper)'}

    forced = normalize_lang(language)
    suffix = os.path.splitext(filename or '')[1] or '.webm'
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
            fh.write(data)
            tmp = fh.name
        segments, info = model.transcribe(
            tmp, language=forced, beam_size=1, vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=_PROMPTS.get(forced) if forced else None)
        text = ' '.join(s.text.strip() for s in segments).strip()
        whisper_lang = normalize_lang(info.language)
        lang = forced or detect_spoken_language(text, whisper_lang) or whisper_lang

        # Auto mode: Whisper sometimes romanizes Amharic or guesses a third
        # language. Re-run forced-Amharic and keep it when it recovers Ge'ez,
        # so Amharic speech never lands on the English path by mistake.
        if forced is None and (not text or lang not in ('am', 'en')):
            am_segments, am_info = model.transcribe(
                tmp, language='am', beam_size=1, vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=_PROMPTS['am'])
            am_text = ' '.join(s.text.strip() for s in am_segments).strip()
            if am_text and detect_spoken_language(am_text) == 'am':
                segments, info, text = am_segments, am_info, am_text
                whisper_lang = normalize_lang(am_info.language) or whisper_lang
                lang = 'am'

        return {
            'text': text,
            'language': lang,
            'whisper_language': whisper_lang,
            'language_probability': round(float(info.language_probability), 3),
            'duration': round(float(info.duration), 2),
            'provider': f'faster-whisper:{_whisper_model_name()}',
        }
    except Exception as exc:  # pragma: no cover - depends on codecs
        return {'error': f'transcription failed: {exc}'}
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# text-to-speech — providers
# ---------------------------------------------------------------------------
def _resample_pcm(pcm, factor):
    """Speed up (factor>1) or slow down (factor<1) 16-bit mono PCM.

    Prefers a band-limited resampler (soxr, then the stdlib ``audioop``) so
    changing the speaking rate never adds the metallic aliasing artefacts that
    make a voice sound synthetic; linear interpolation is only a last resort.
    """
    if not pcm or abs(factor - 1.0) < 1e-3:
        return pcm
    factor = max(0.5, min(2.5, float(factor)))
    # A factor > 1 means "speak faster", i.e. fewer output samples.
    # 1) soxr — high quality, if installed.
    try:
        import numpy as np
        import soxr
        src = np.frombuffer(pcm[:len(pcm) - (len(pcm) % 2)], dtype='<i2')
        out = soxr.resample(src.astype('float32'), 1.0, 1.0 / factor)
        return np.clip(out, -32768, 32767).astype('<i2').tobytes()
    except Exception:
        pass
    # 2) stdlib audioop.ratecv (CPython <= 3.12).
    try:
        import audioop
        outrate = max(1, int(round(1000.0 / factor)))
        return audioop.ratecv(pcm, 2, 1, 1000, outrate, None)[0]
    except Exception:
        pass
    # 3) linear interpolation (fallback).
    import array
    src = array.array('h')
    src.frombytes(pcm[:len(pcm) - (len(pcm) % 2)])
    if not src:
        return pcm
    n = max(1, int(len(src) / factor))
    out = array.array('h', bytes(2 * n))
    for i in range(n):
        pos = i * factor
        j = int(pos)
        frac = pos - j
        out[i] = int(src[j] * (1 - frac) + src[j + 1] * frac) if j + 1 < len(src) else src[-1]
    return out.tobytes()


def _wav_bytes(pcm, rate):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _post_process(wav_bytes, rate=None, volume=None):
    """Normalise, rate-adjust and de-click a 16-bit mono WAV.

    A consistent, peak-normalised level with short fades keeps the neural voice
    sounding natural instead of quiet/harsh at the edges.
    """
    try:
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
            sr = wf.getframerate()
            pcm = wf.readframes(wf.getnframes())
        if not pcm:
            return wav_bytes
        # Peak-normalise for an even, present level.
        try:
            import audioop
            peak = audioop.max(pcm, 2)
            if peak:
                target = int(0.93 * 32767)
                if abs(peak - target) > 200:
                    pcm = audioop.mul(pcm, 2, min(4.0, target / float(peak)))
        except Exception:
            pass
        if volume is not None:
            gain = max(0.0, min(2.0, float(volume) / 100.0))
            if abs(gain - 1.0) > 1e-3:
                try:
                    import audioop
                    pcm = audioop.mul(pcm, 2, gain)
                except Exception:
                    import array
                    a = array.array('h')
                    a.frombytes(pcm[:len(pcm) - (len(pcm) % 2)])
                    for i, v in enumerate(a):
                        a[i] = max(-32768, min(32767, int(v * gain)))
                    pcm = a.tobytes()
        if rate is not None:
            pcm = _resample_pcm(pcm, max(0.5, min(2.5, float(rate) / 150.0)))
        # Short fade in/out removes the click that otherwise starts every clip.
        try:
            import array
            a = array.array('h')
            a.frombytes(pcm[:len(pcm) - (len(pcm) % 2)])
            n = len(a)
            f = int(sr * 0.012)
            if f and n > 2 * f:
                for i in range(f):
                    g = i / float(f)
                    a[i] = int(a[i] * g)
                    a[n - 1 - i] = int(a[n - 1 - i] * g)
            pcm = a.tobytes()
        except Exception:
            pass
        return _wav_bytes(pcm, sr)
    except Exception:
        return wav_bytes


def _has_torch():
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except Exception:
        return False


# Split on Amharic (። ፧ ፨) and Latin sentence punctuation. Long fragments are
# further split so each neural call stays short and prosodically clean.
_SENT_RE = re.compile(r'[^።፧፨.!?\n]+[።፧፨.!?]*')


def _chunks(text, max_chars=180):
    """Sentences/clauses to synthesise, so pauses land in natural places."""
    text = (text or '').strip()
    if not text:
        return []
    parts = [m.group(0).strip() for m in _SENT_RE.finditer(text)]
    parts = [p for p in parts if p]
    # Split overly long sentences at a comma/space so one call stays short.
    split = []
    for s in parts:
        while len(s) > max_chars:
            cut = max(s.rfind('፣', 0, max_chars), s.rfind(',', 0, max_chars),
                      s.rfind(' ', 0, max_chars))
            if cut < 40:
                cut = max_chars
            split.append(s[:cut + 1].strip())
            s = s[cut + 1:].strip()
        if s:
            split.append(s)
    # Keep sentences separate so a short breath falls between them; only merge
    # fragments too tiny to carry their own prosody.
    out = []
    for s in split:
        if out and len(out[-1]) < 12:
            out[-1] = (out[-1] + ' ' + s).strip()
        else:
            out.append(s)
    return out or [text]


def _load_mms(lang):
    """Load (model, tokenizer) for a language; cached and thread-safe."""
    model_id = _mms_ids(lang)
    entry = _mms_models.get(model_id)
    if entry is None:
        from transformers import VitsModel, AutoTokenizer
        model = VitsModel.from_pretrained(model_id)
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model.eval()
        entry = (model, tokenizer)
        _mms_models[model_id] = entry
    return entry


def _synthesize_mms(text, lang, rate=None, volume=None):
    global _mms_fail_count, _mms_error
    if _mms_fail_count >= _MMS_MAX_FAILS:
        return None
    with _lock:
        try:
            import numpy as np
            import torch
        except Exception as exc:
            _mms_fail_count = _MMS_MAX_FAILS
            _mms_error = f'import: {exc!r}'[:400]
            return None
        model_id = _mms_ids(lang)
        try:
            model, tokenizer = _load_mms(lang)
            sr = int(model.config.sampling_rate)
            # Long replies are synthesised sentence by sentence with a natural
            # breath between them — far more human than one flat utterance.
            chunks = _chunks(text)
            pieces = []
            for idx, chunk in enumerate(chunks):
                prepared = _romanize(chunk, 'amh') if lang == 'am' else chunk
                inputs = tokenizer(prepared, return_tensors='pt')
                if inputs['input_ids'].numel() == 0:
                    continue
                with torch.no_grad():
                    waveform = model(**inputs).waveform[0].cpu().numpy()
                pieces.append(np.asarray(waveform, dtype='float32'))
                if idx < len(chunks) - 1:
                    tail = chunk.rstrip()[-1:] or ''
                    gap = 0.30 if tail in '?!' else (0.18 if tail in '.።' else 0.12)
                    pieces.append(np.zeros(int(sr * gap), dtype='float32'))
            if not pieces:
                raise ValueError('tokenizer produced no tokens')
            waveform = np.concatenate(pieces)
            pcm = (np.clip(waveform, -1.0, 1.0) * 32767).astype('<i2').tobytes()
            audio = _post_process(_wav_bytes(pcm, sr), rate=rate, volume=volume)
            _mms_fail_count = 0
            return audio, 'audio/wav', f'mms:{model_id.split("/")[-1]}'
        except Exception as exc:
            _mms_fail_count += 1
            _mms_error = f'{type(exc).__name__}: {exc}'[:500]
            return None


def warm_tts(lang='am'):
    """Pre-load the neural voice so the first reply does not pay the load."""
    if not _provider_available('mms'):
        return False
    try:
        _load_mms(lang)
        return True
    except Exception as exc:
        global _mms_error
        _mms_error = f'{type(exc).__name__}: {exc}'[:400]
        return False


# Piper English voices (the repo path inside rhasspy/piper-voices).
PIPER_VOICES = {
    'en_US-amy-medium': 'en/en_US/amy/medium/en_US-amy-medium',
    'en_US-ryan-high': 'en/en_US/ryan/high/en_US-ryan-high',
    'en_US-lessac-medium': 'en/en_US/lessac/medium/en_US-lessac-medium',
    'en_GB-alan-medium': 'en/en_GB/alan/medium/en_GB-alan-medium',
}
_PIPER_BASE = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/'


def _piper_ensure(key):
    rel = PIPER_VOICES[key]
    d = _cache_dir('piper')
    base = os.path.join(d, os.path.basename(rel))
    onnx, conf = base + '.onnx', base + '.onnx.json'
    if not (os.path.exists(onnx) and os.path.exists(conf)):
        for url, dest in ((_PIPER_BASE + rel + '.onnx', onnx),
                          (_PIPER_BASE + rel + '.onnx.json', conf)):
            urllib.request.urlretrieve(url, dest)
    return onnx, conf


def _piper_available():
    return shutil.which('piper') is not None


def _synthesize_piper(text, key='en_US-amy-medium', rate=None, volume=None):
    global _piper_error
    if not _piper_available():
        return None
    if key not in PIPER_VOICES:
        key = 'en_US-amy-medium'
    try:
        onnx, conf = _piper_ensure(key)
    except Exception:
        return None
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as fh:
            tmp = fh.name
        subprocess.run(['piper', '-m', onnx, '-c', conf, '-f', tmp],
                       input=text.encode('utf-8'), check=True,
                       capture_output=True, timeout=90)
        with open(tmp, 'rb') as fh:
            audio = _post_process(fh.read(), rate=rate, volume=volume)
        return audio, 'audio/wav', f'piper:{key}'
    except Exception as exc:
        _piper_error = f'{type(exc).__name__}: {exc}'[:400]
        return None
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _synthesize_espeak(text, lang, voice=None, rate=None, pitch=None,
                       volume=None, gap=None):
    binary = _espeak_bin()
    if not binary:
        return None
    voice = voice or ('am' if lang == 'am' else 'en-us')
    rate = 150 if rate is None else rate
    pitch = 45 if pitch is None else pitch
    volume = 130 if volume is None else volume
    gap = 0 if gap is None else gap
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as fh:
            tmp = fh.name
        subprocess.run([binary, '-v', str(voice), '-s', str(int(rate)),
                        '-p', str(int(pitch)), '-a', str(int(volume)),
                        '-g', str(int(gap)), '-w', tmp, text],
                       check=True, capture_output=True, timeout=30)
        with open(tmp, 'rb') as fh:
            return fh.read(), 'audio/wav', f'espeak-ng:{voice}'
    except Exception:
        return None
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _provider_available(name):
    if name == 'mms':
        return _has_torch()
    if name == 'piper':
        return _piper_available()
    if name == 'espeak':
        return bool(_espeak_bin())
    return False


def _espeak_voices():
    binary = _espeak_bin()
    out = []
    if not binary:
        return out
    try:
        listing = subprocess.run([binary, '--voices'], capture_output=True,
                                 text=True, timeout=10).stdout
        seen = set()
        for line in listing.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 4:
                continue
            code = parts[1]
            if code.split('-')[0] not in SUPPORTED_LANGS or code in seen:
                continue
            seen.add(code)
            out.append({'value': f'espeak:{code}', 'lang': code.split('-')[0],
                        'label': f'eSpeak · {code}'})
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# public TTS API
# ---------------------------------------------------------------------------
def _dispatch(provider, vid, text, lang, rate, pitch, volume, gap):
    if provider == 'mms':
        return _synthesize_mms(text, lang, rate=rate, volume=volume)
    if provider == 'piper':
        return _synthesize_piper(text, vid or 'en_US-amy-medium', rate=rate, volume=volume)
    if provider == 'espeak':
        return _synthesize_espeak(text, lang, voice=vid, rate=rate, pitch=pitch,
                                  volume=volume, gap=gap)
    return None


def _candidate_order(lang, voice):
    """Resolve the "<provider>:<id>" voice (or 'auto') into a fallback chain."""
    requested = (voice or '').strip()
    prov = vid = None
    if ':' in requested:
        prov, vid = requested.split(':', 1)
    elif requested and requested not in ('auto', ''):
        prov, vid = 'espeak', requested      # back-compat: bare eSpeak voice

    choice = os.environ.get('ZER_TTS', 'auto').lower()
    if choice == 'none':
        return []
    allowed = {'auto': {'mms', 'piper', 'espeak'}}.get(choice, {choice})

    best = [('mms', None), ('espeak', None)]
    if lang == 'en':
        best = [('piper', 'en_US-amy-medium'), ('mms', None), ('espeak', None)]

    chain = []
    if prov and prov in allowed:
        chain.append((prov, vid))
    for item in best:
        if item[0] in allowed and item not in chain:
            chain.append(item)
    # Per-language MMS id, in case provider was given without an id.
    return chain


def synthesize(text, lang='am', voice=None, rate=None, pitch=None,
               volume=None, gap=None):
    """Return (audio_bytes, mimetype, provider) or (None, None, None)."""
    text = (text or '').strip()
    if not text:
        return _wav_bytes(struct.pack('<800h', *([0] * 800)), 16000), 'audio/wav', 'silence'
    lang = normalize_lang(lang) or 'am'

    for provider, vid in _candidate_order(lang, voice):
        try:
            result = _dispatch(provider, vid, text, lang, rate, pitch, volume, gap)
        except Exception:
            result = None
        if result:
            return result
    return None, None, None


def tts_available():
    return any(_provider_available(p) for p in ('mms', 'piper', 'espeak'))


def voices():
    """Available TTS voices + tunable ranges for the client."""
    out = []
    if _provider_available('mms'):
        out.append({'value': 'mms:am', 'lang': 'am', 'label': 'MMS · አማርኛ (neural)'})
        out.append({'value': 'mms:en', 'lang': 'en', 'label': 'MMS · English (neural)'})
    if _provider_available('piper'):
        labels = {
            'en_US-amy-medium': 'Amy · US English (natural)',
            'en_US-ryan-high': 'Ryan · US English (expressive)',
            'en_US-lessac-medium': 'Lessac · US English',
            'en_GB-alan-medium': 'Alan · UK English',
        }
        for key, label in labels.items():
            out.append({'value': f'piper:{key}', 'lang': 'en', 'label': f'{label} · Piper'})
    out += _espeak_voices()
    if not out:
        out = [
            {'value': 'espeak:am', 'lang': 'am', 'label': 'eSpeak · አማርኛ (fallback)'},
            {'value': 'espeak:en-us', 'lang': 'en', 'label': 'eSpeak · English (fallback)'},
        ]

    providers = [p for p in ('mms', 'piper', 'espeak') if _provider_available(p)]
    return {
        'voices': out,
        'defaults': {
            'am': {'voice': 'mms:am' if _provider_available('mms') else 'espeak:am',
                   'rate': 145, 'pitch': 45, 'volume': 130, 'gap': 0},
            'en': {'voice': 'piper:en_US-amy-medium' if _provider_available('piper')
                   else ('mms:en' if _provider_available('mms') else 'espeak:en-us'),
                   'rate': 165, 'pitch': 50, 'volume': 120, 'gap': 0},
        },
        'ranges': {'rate': [80, 300], 'pitch': [0, 99], 'volume': [0, 200], 'gap': [0, 20]},
        'engine': '+'.join(providers) or 'none',
    }


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
def status():
    return {
        'stt': {
            'available': stt_available(),
            'provider': f'faster-whisper:{_whisper_model_name()}',
            'model': _whisper_model_name(),
            'loaded': _whisper is not None,
            'languages': list(SUPPORTED_LANGS),
        },
        'tts': {
            'available': tts_available(),
            'mms': _provider_available('mms'),
            'piper': _provider_available('piper'),
            'espeak': _provider_available('espeak'),
            'languages': list(SUPPORTED_LANGS),
            'mms_error': _mms_error,
            'piper_error': _piper_error,
        },
    }
