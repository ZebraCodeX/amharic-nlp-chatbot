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


def transcribe_bytes(data, filename='audio.webm', language=None):
    """Transcribe an audio blob. Returns dict or {'error': …}.

    ``language=None`` lets Whisper auto-detect (this is what drives the
    "reply in the language the user spoke" behaviour).
    """
    if not data:
        return {'error': 'empty audio'}
    model = _load_whisper()
    if model is None:
        return {'error': 'speech-to-text unavailable (install faster-whisper)'}

    suffix = os.path.splitext(filename or '')[1] or '.webm'
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
            fh.write(data)
            tmp = fh.name
        segments, info = model.transcribe(
            tmp, language=normalize_lang(language), beam_size=1,
            vad_filter=True, condition_on_previous_text=False)
        text = ' '.join(s.text.strip() for s in segments).strip()
        return {
            'text': text,
            'language': normalize_lang(info.language),
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
def _synthesize_mms(text, lang):
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
            pcm = (waveform * 32767).astype('<i2').tobytes()
            buf = io.BytesIO()
            with wave.open(buf, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(model.config.sampling_rate)
                wf.writeframes(pcm)
            return buf.getvalue(), 'audio/wav', f'mms:{model_id.split("/")[-1]}'
        except Exception:
            return None


def _synthesize_espeak(text, lang):
    binary = _espeak_bin()
    if not binary:
        return None
    voice = 'am' if lang == 'am' else 'en-us'
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as fh:
            tmp = fh.name
        subprocess.run([binary, '-v', voice, '-s', '155', '-p', '45', '-w', tmp, text],
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


def synthesize(text, lang='am'):
    """Return (audio_bytes, mimetype, provider) or (None, None, None)."""
    text = (text or '').strip()
    if not text:
        return _placeholder_wav(), 'audio/wav', 'silence'
    lang = normalize_lang(lang) or 'am'
    choice = os.environ.get('ZER_TTS', 'auto').lower()

    if choice in ('auto', 'mms'):
        result = _synthesize_mms(text, lang)
        if result:
            return result
    if choice in ('auto', 'espeak'):
        result = _synthesize_espeak(text, lang)
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
