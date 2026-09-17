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
    "Your name is Zer (ዘር), an Ethiopian AI assistant; 'ዘር' means 'seed'. "
    "Always answer in the SAME language the user used: Amharic → Amharic in Ge'ez "
    "script, English → English. Never mix scripts. Be warm, accurate and thorough: "
    "give a short opening answer, then a few concrete points, and an example when "
    "useful. If the user asks for code, poems, stories or plans, produce the full "
    "artifact."
)

# Short offline English rules so the assistant still works without an LLM.
_EN_GREET = re.compile(r'\b(hi|hey|hello|good (morning|afternoon|evening)|salam)\b', re.I)
_EN_THANKS = re.compile(r'\b(thanks|thank you|thx)\b', re.I)
_EN_WHO = re.compile(r"\b(who are you|your name|what are you|what'?s your name)\b", re.I)
_EN_CAPS = re.compile(r'\b(what can you do|help|capabilities|features)\b', re.I)
_EN_BYE = re.compile(r'\b(bye|goodbye|see you)\b', re.I)


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
    def _english_llm(self, text, history=None, use_llm=True):
        if not use_llm:
            return None
        try:
            from llm import chat as llm_chat
        except Exception:
            return None
        system = ZER_SYSTEM + " The user is writing in English."
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
        return llm_chat(system, text, hist)

    def _english_offline(self, text):
        t = text.strip()
        if _EN_THANKS.search(t):
            return "You're welcome! Ask me anything else."
        if _EN_WHO.search(t):
            return (f"I'm {ASSISTANT_NAME} ({ASSISTANT_NAME_EN}) — an Ethiopian AI assistant. "
                    "'ዘር' means 'seed' in Amharic. I speak Amharic and English, can do math, "
                    "explain topics, write Amharic/English code, and translate.")
        if _EN_CAPS.search(t):
            return ("I can: chat in Amharic and English, do math, define Amharic words, "
                    "translate Amharic⇄English, write code and creative text, and hold a "
                    "live voice conversation — just say 'Hey Zer'.")
        if _EN_GREET.search(t):
            return f"Hello! I'm {ASSISTANT_NAME_EN} (ዘር). What would you like to talk about?"
        if _EN_BYE.search(t):
            return "Goodbye! Come back any time."
        math = self._am._try_math(text)
        if math:
            return math
        return ("I can answer that best with a language model connected, but I'm running "
                "offline right now. Ask me about Amharic words, math, or say 'what can you do'.")

    # -- public -----------------------------------------------------------
    def respond(self, text, lang=None, history=None, use_llm=True):
        text = (text or '').strip()
        if not text:
            return {'reply': 'ምን ልርዳህ? / How can I help?', 'source': 'empty',
                    'confidence': 1.0, 'lang': lang or 'unknown', 'followups': []}

        resolved = _normalize_lang(lang) or detect_language(text)
        if resolved == 'unknown':
            resolved = detect_language(text)

        # Use translations the user taught us, before anything else.
        learned = self._learned_reply(text)
        if learned:
            return {'reply': learned, 'source': 'learned', 'confidence': 0.95,
                    'lang': resolved if resolved != 'unknown' else 'am', 'followups': []}

        if resolved == 'am':
            result = self._am.respond(text, use_llm=use_llm)
            result['lang'] = 'am'
            return result

        # English (or unknown → treat as English when Latin/other)
        reply = self._english_llm(text, history=history, use_llm=use_llm)
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
