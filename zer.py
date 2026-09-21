#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zer.py — "Zer" (ዘር, *seed*), the bilingual Amharic/English brain.

Wraps the existing Amharic assistant and adds:

  * automatic language detection (Ge'ez script → am, Latin → en)
  * English replies when the user writes (or speaks) English
  * Amharic replies (unchanged rule/LLM brain) when the user writes Amharic
  * an optional real LLM that is told to answer in the user's own language

Used by the /api/chat and /api/voice endpoints, and by the speech pipeline.
"""

import re

ETHIOPIC_RE = re.compile(r'[\u1200-\u137F]')
LATIN_RE = re.compile(r'[A-Za-z]')

ASSISTANT_NAME = 'ዘር'
ASSISTANT_NAME_EN = 'Zer'

ZER_SYSTEM = (
    "You are Zer (ዘር), a helpful bilingual (Amharic/English) AI assistant. "
    "LANGUAGE: always reply in the SAME language the user wrote in — Amharic in "
    "Ge'ez script, or English — and never mix scripts or switch language on your "
    "own. "
    "QUALITY: reason the question through step by step before answering, then "
    "give a direct, accurate, on-topic answer. Never invent facts, names, "
    "numbers or sources; if you are unsure, say so plainly and give what you do "
    "know. Stay on the user's topic — do not pad, repeat or wander. "
    "FORMAT: open with a one-sentence answer, then explain with 3-6 short bullet "
    "points (each starting with •), add one concrete example, and finish with a "
    "brief conclusion. Use headings, numbered steps, a table or a code fence "
    "when they genuinely help. "
    "LENGTH: give a substantive answer — aim for 4-8 sentences (about 200-350 "
    "words) unless the user explicitly asks to be brief; expand further when they "
    "ask for depth, a long list, or a full artifact. Do not stop after one or two "
    "sentences. "
    "For requests to write code, a poem, a story, an essay, a plan, a website or "
    "an email, produce the complete finished piece. When writing code you may "
    "use Amharic comments, Amharic string literals and even Amharic identifiers "
    "(Ethiopic names are valid in Python, JavaScript and most languages)."
)

def detect_language(text):
    """Return 'am', 'en' or 'unknown' from the script used in ``text``."""
    text = text or ''
    am = len(ETHIOPIC_RE.findall(text))
    en = len(LATIN_RE.findall(text))
    if am and en:
        return 'am' if am >= en else 'en'
    if am:
        return 'am'
    if en:
        return 'en'
    return 'unknown'


def _normalize_lang(lang):
    if not lang:
        return None
    lang = str(lang).lower().split('-')[0].split('_')[0]
    if lang in ('am', 'amh', 'amharic'):
        return 'am'
    if lang in ('en', 'eng', 'english'):
        return 'en'
    return None


def _resolve_language(text, lang=None):
    """Decide the reply language, letting the script override a wrong STT guess.

    Ge'ez script is an essentially perfect Amharic signal, so it always wins:
    a Whisper/voice guess of ``en`` must never send Amharic text down the
    English path. When the script is not decisive we trust an explicit
    ``lang`` (the caller's setting or the STT result), and only then fall back
    to the script.
    """
    script = detect_language(text)
    provided = _normalize_lang(lang)
    if script == 'am':
        return 'am'
    if provided:
        return provided
    return script



class Zer:
    """Bilingual chat brain: Amharic rule/LLM brain + English answers."""

    name = ASSISTANT_NAME
    name_en = ASSISTANT_NAME_EN

    def __init__(self):
        from chatbot import AmharicAssistant
        self._am = AmharicAssistant()

    # -- learned translations (taught in /review) -------------------------
    def _learned_reply(self, text):
        """Answer directly from the glossary humans taught, when asked."""
        try:
            from learning import answer as learned_answer
        except Exception:
            return None
        result = learned_answer(text)
        return result[0] if result else None

    def _learned_hints(self, text):
        try:
            from learning import hints
            return hints(text)
        except Exception:
            return []

    # -- English ----------------------------------------------------------
    def _english_llm(self, text, history=None, use_llm=True, on_delta=None):
        if not use_llm:
            return None
        try:
            from llm import chat as llm_chat
            from llm import chat_stream as llm_chat_stream
        except Exception:
            return None
        system = ZER_SYSTEM + (
            " The user is writing in English. Reply in English only, using Latin "
            "letters — do not output any Amharic/Ge'ez characters. Begin "
            "immediately with the answer, with no preamble.")
        learned = self._learned_hints(text)
        if learned:
            system += (" The user has personally taught you these Amharic→English "
                       "translations — always use their wording: " +
                       "; ".join(learned) + ".")
        hist = []
        for turn in (history or [])[-6:]:
            if not isinstance(turn, dict):
                continue
            role = turn.get('role')
            content = str(turn.get('content') or '').strip()
            if role in ('user', 'assistant') and content:
                hist.append({'role': role, 'content': content})
        if on_delta:
            parts = []
            for delta in llm_chat_stream(system, text, hist):
                if delta:
                    parts.append(delta)
                    on_delta(delta)
            return ''.join(parts).strip() or None
        return llm_chat(system, text, hist)

    def _english_offline(self, text):
        """Answer English from Zer's own data — no model, no translation."""
        try:
            import english_brain
            return english_brain.respond(text, assistant=self._am)['reply']
        except Exception:
            return ("I'm here and happy to help! Ask me about technology, "
                    "science, Ethiopia or Amharic words, give me some math, or "
                    "ask me to write code.")

    # -- public -----------------------------------------------------------
    def respond(self, text, lang=None, history=None, use_llm=True, on_delta=None):
        text = (text or '').strip()
        if not text:
            return {'reply': 'ምን ልርዳህ? / How can I help?', 'source': 'empty',
                    'confidence': 1.0, 'lang': lang or 'unknown', 'followups': []}

        resolved = _resolve_language(text, lang)

        # Use translations the user taught us, before anything else.
        learned = self._learned_reply(text)
        if learned:
            return {'reply': learned, 'source': 'learned', 'confidence': 0.95,
                    'lang': resolved if resolved != 'unknown' else 'am', 'followups': []}

        if resolved == 'am':
            result = self._am.respond(text, use_llm=use_llm, on_delta=on_delta)
            result['lang'] = 'am'
            return result

        # English (or unknown → treat as English when Latin/other)
        reply = self._english_llm(text, history=history, use_llm=use_llm,
                                  on_delta=on_delta)
        source = 'llm'
        if not reply:
            reply = self._english_offline(text)
            source = 'rules_en'
        return {'reply': reply, 'source': source, 'confidence': 0.9,
                'lang': resolved if resolved != 'unknown' else 'en', 'followups': []}


_singleton = None


def get_zer():
    global _singleton
    if _singleton is None:
        _singleton = Zer()
    return _singleton
