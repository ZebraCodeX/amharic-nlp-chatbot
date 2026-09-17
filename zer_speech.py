#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zer_speech.py — open-source speech engine for Zer (Amharic + English).

Speech-to-text:  faster-whisper (OpenAI Whisper on CTranslate2) with automatic
                 language detection → Amharic ('am') or English ('en').
Text-to-speech:  Meta MMS-TTS VITS models (facebook/mms-tts-amh / -eng) when
                 torch+transformers are installed, otherwise eSpeak NG (a small,
                 always-available OSS synthesizer that supports Amharic).

Every provider is optional and lazily loaded: if a library/model is missing the
function returns a clear "unavailable" result and the web client falls back to
the browser's Web Speech API. Nothing here is required for the text app to work.

Env knobs:
    ZER_WHISPER_MODEL   tiny | base | small | medium | large-v3   (default base)
    ZER_WHISPER_DEVICE  cpu | cuda                               (default cpu)
    ZER_WHISPER_COMPUTE int8 | int8_float16 | float16 | float32  (default int8)
    ZER_TTS             auto | mms | espeak | none               (default auto)
    HF_HOME             where STT/TTS models are cached (set to a volume)
"""

import io
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import wave

_lock = threading.RLock()
_whisper = None
_mms_models = {}
_whisper_failed = False
_mms_failed = False

SUPPORTED_LANGS = ('am', 'en')


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _whisper_model_name():
    return os.environ.get('ZER_WHISPER_MODEL', 'base')


def _espeak_bin():
    return shutil.which('espeak-ng') or shutil.which('espeak')


# Default tunable parameters per language. `rate` = words/min, `pitch` 0..99,
# `volume` 0..200, `gap` = extra word gap (ms * 10) — all eSpeak NG options.
DEFAULT_PARAMS = {
    'am': {'voice': 'am', 'rate': 145, 'pitch': 45, 'volume': 130, 'gap': 0},
    'en': {'voice': 'en-us', 'rate': 165, 'pitch': 50, 'volume': 120, 'gap': 0},
}

# eSpeak NG vocal variants, so users can pick a different "voice type".
_VARIANTS = [
    ('+m1', 'male 1'), ('+m2', 'male 2'), ('+m3', 'male 3'),
    ('+f1', 'female 1'), ('+f2', 'female 2'), ('+f3', 'female 3'),
    ('+f4', 'female 4'), ('+croak', 'croak'), ('+whisper', 'whisper'),
]

_LANG_LABEL = {'am': 'አማርኛ', 'en': 'English'}


def voices():
    """Available TTS voices + tunable ranges for the client's voice settings."""
    found = []
    binary = _espeak_bin()
    if binary:
        try:
            out = subprocess.run([binary, '--voices'], capture_output=True,
                                 text=True, timeout=10).stdout
            for line in out.splitlines()[1:]:
                parts = line.split()
                if len(parts) < 4:
                    continue
                lang = parts[1]
                if lang.split('-')[0] not in SUPPORTED_LANGS:
                    continue
                found.append({'value': lang, 'lang': lang.split('-')[0],
                              'label': lang})
        except Exception:
            found = []

    # Guarantee a usable list even without eSpeak (client falls back gracefully).
    base = {v['value'] for v in found}
    for value in ('am', 'en-us', 'en-gb', 'en'):
        if value not in base:
            found.append({'value': value, 'lang': value.split('-')[0], 'label': value})

    # Add vocal variants for the English voices (and Amharic where supported).
    expanded = []
    for v in found:
        expanded.append(v)
        if v['lang'] == 'en':
            for suffix, label in _VARIANTS:
                expanded.append({'value': f"{v['value']}{suffix}", 'lang': 'en',
                                 'label': f"{v['value']} {label}"})

    ordered = sorted(expanded, key=lambda v: (v['lang'] != 'am', v['value']))
    return {
        'voices': ordered,
        'defaults': DEFAULT_PARAMS,
        'ranges': {
            'rate': [80, 300],
            'pitch': [0, 99],
            'volume': [0, 200],
            'gap': [0, 20],
        },
        'engine': 'mms' if tts_available() and os.environ.get('ZER_TTS', 'auto') in ('auto', 'mms') and _has_mms() else ('espeak' if _espeak_bin() else 'none'),
    }


def _has_mms():
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except Exception:
        return False


def _mms_ids(lang):
    return 'facebook/mms-tts-amh' if lang == 'am' else 'facebook/mms-tts-eng'


def normalize_lang(code):
    """'en-US'→'en', 'Amharic'→None-safe; empty → None (auto-detect)."""
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


_PROMPTS = {
    'am': 'ሰላም። እንዴት ነህ? እኔ ዘር ነኝ።',
    'en': 'Hello. How are you? I am Zer.',
}


def detect_spoken_language(text, fallback=None):
    """Amharic (Ge'ez) and English use different scripts, so the transcript's
    script is a near-perfect language signal. Falls back to Whisper's guess."""
    am = sum(1 for c in text if '\u1200' <= c <= '\u137f')
    en = sum(1 for c in text if ('a' <= c.lower() <= 'z'))
    if am and am >= en:
        return 'am'
    if en and en > am:
        return 'en'
    return fallback


def transcribe_bytes(data, filename='audio.webm', language=None):
    """Transcribe an audio blob and return {text, language, …}.

    ``language=None`` lets Whisper auto-detect; the result is then reconciled
    against the transcript's script so Amharic speech is never mistaken for
    English (and vice versa).
    """
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
# text-to-speech
# ---------------------------------------------------------------------------
def _resample_pcm(pcm, factor):
    """Speed up (factor>1) or slow down (factor<1) 16-bit mono PCM."""
    if not pcm or abs(factor - 1.0) < 1e-3:
        return pcm
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


def _synthesize_mms(text, lang, rate=None, volume=None):
    global _mms_failed
    if _mms_failed:
        return None
    with _lock:
        try:
            import torch
            from transformers import VitsModel, AutoTokenizer
        except Exception:
            _mms_failed = True
            return None
        model_id = _mms_ids(lang)
        try:
            entry = _mms_models.get(model_id)
            if entry is None:
                model = VitsModel.from_pretrained(model_id)
                tokenizer = AutoTokenizer.from_pretrained(model_id)
                model.eval()
                entry = (model, tokenizer)
                _mms_models[model_id] = entry
            model, tokenizer = entry
            inputs = tokenizer(text, return_tensors='pt')
            with torch.no_grad():
                waveform = model(**inputs).waveform[0].cpu().numpy()
            gain = 1.0 if not volume else max(0.0, min(2.0, float(volume) / 100.0))
            pcm = (waveform * 32767 * gain).clip(-32768, 32767).astype('<i2').tobytes()
            if rate:
                pcm = _resample_pcm(pcm, max(0.5, min(2.5, float(rate) / 150.0)))
            buf = io.BytesIO()
            with wave.open(buf, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(model.config.sampling_rate)
                wf.writeframes(pcm)
            return buf.getvalue(), 'audio/wav', f'mms:{model_id.split("/")[-1]}'
        except Exception:
            return None


def _synthesize_espeak(text, lang, voice=None, rate=None, pitch=None,
                       volume=None, gap=None):
    binary = _espeak_bin()
    if not binary:
        return None
    defaults = DEFAULT_PARAMS.get(lang, DEFAULT_PARAMS['am'])
    voice = voice or defaults['voice']
    rate = defaults['rate'] if rate is None else rate
    pitch = defaults['pitch'] if pitch is None else pitch
    volume = defaults['volume'] if volume is None else volume
    gap = defaults['gap'] if gap is None else gap
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


def _placeholder_wav():
    """A short silence so clients always get valid audio for an empty reply."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(struct.pack('<%dh' % 800, *([0] * 800)))
    return buf.getvalue()


def synthesize(text, lang='am', voice=None, rate=None, pitch=None,
               volume=None, gap=None):
    """Return (audio_bytes, mimetype, provider) or (None, None, None).

    ``rate`` (words/min), ``pitch`` (0-99), ``volume`` (0-200) and ``gap`` let
    the caller tune the voice; ``voice`` picks a specific eSpeak voice/variant.
    """
    text = (text or '').strip()
    if not text:
        return _placeholder_wav(), 'audio/wav', 'silence'
    lang = normalize_lang(lang) or 'am'
    choice = os.environ.get('ZER_TTS', 'auto').lower()

    if choice in ('auto', 'mms'):
        result = _synthesize_mms(text, lang, rate=rate, volume=volume)
        if result:
            return result
    if choice in ('auto', 'espeak'):
        result = _synthesize_espeak(text, lang, voice=voice, rate=rate,
                                    pitch=pitch, volume=volume, gap=gap)
        if result:
            return result
    return None, None, None


def tts_available():
    choice = os.environ.get('ZER_TTS', 'auto').lower()
    if choice in ('auto', 'mms'):
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
            return True
        except Exception:
            pass
    if choice in ('auto', 'espeak') and _espeak_bin():
        return True
    return False


# ---------------------------------------------------------------------------
# status (drives the client's graceful fallback)
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
            'mms': os.environ.get('ZER_TTS', 'auto') in ('auto', 'mms'),
            'espeak': bool(_espeak_bin()),
            'languages': list(SUPPORTED_LANGS),
        },
    }
