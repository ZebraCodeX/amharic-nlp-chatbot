#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_english_kb.py — compile an English mirror of the Amharic knowledge base.

The runtime never translates or calls a model: this tool bakes an
`data/knowledge_base_en.json` once, offline of any request, so the assistant can
answer English questions from its own data. The translator is only a *build*
tool here — it makes the AI better, it is not on the serving path.

Usage:
    python3 tools/build_english_kb.py            # uses the network (MyMemory)
    python3 tools/build_english_kb.py --offline  # keep Amharic text as-is
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
KB = os.path.join(DATA, 'knowledge_base.json')
OUT = os.path.join(DATA, 'knowledge_base_en.json')
CACHE = os.path.join(DATA, '.kb_en_cache.json')

_UA = {'User-Agent': 'Zer-English-KB-builder/1.0'}

# Hand-written English answers for the conversational intents — machine
# translation is fine for topics, but greetings must read naturally.
OVERRIDES = {
    'greeting': [
        "Hello! I'm Zer, your Amharic AI assistant. What would you like to talk about?",
        "Welcome! I speak Amharic and English — ask me anything.",
        "Hi there! How can I help you today?",
    ],
    'goodbye': [
        "Goodbye! Come back any time.",
        "See you soon — I'm here whenever you have a question.",
    ],
    'thanks': [
        "You're welcome! Ask me anything else.",
        "Happy to help!",
    ],
    'how_are_you': [
        "I'm always good — thanks for asking! How are you?",
        "I'm doing great and ready to help. How about you?",
    ],
    'who_are_you': [
        "I'm Zer (ዘር) — an Ethiopian AI assistant. 'Zer' means 'seed' in Amharic. "
        "I answer in Amharic or English and I work without needing another model.",
    ],
    'your_name': [
        "My name is Zer (ዘር) — it means 'seed'. Just call me Zer!",
    ],
    'your_age': [
        "I'm always new — I keep improving. My knowledge is built from Amharic "
        "books, news, conversation and more.",
    ],
    'origin': [
        "I come from the world of language technology — built for Amharic first.",
    ],
    'capabilities': [
        "I can: chat in Amharic and English, do math, explain topics, define "
        "Amharic words, write code (Python, JavaScript, HTML, CSS, SQL, Bash), "
        "create poems, stories and websites, tell the time and the Ethiopian "
        "date, and hold a live voice conversation — just say 'Hey Zer'.",
    ],
    'help': [
        "Sure! Ask me a question, give me a math problem, request code, or say "
        "'write a poem about ...'. I answer in Amharic or English.",
    ],
    'ai': [
        "AI (artificial intelligence) is the field of building computer systems "
        "that can do tasks which normally need human intelligence — understanding "
        "language, recognising images, learning from data and making decisions. "
        "I'm an example: I understand Amharic and English and answer questions.",
    ],
    'ethiopia': [
        "Ethiopia is a country in the Horn of Africa with a very long history — "
        "it is the birthplace of coffee, home to the ancient Ge'ez script and the "
        "Ethiopic calendar, and it has more than 80 languages.",
    ],
    'small_talk': [
        "I'm here and happy to chat! What's on your mind?",
    ],
}

# English trigger phrases per intent (used by the matcher, alongside the
# machine-translated Amharic patterns).
KEYWORDS = {
    'greeting': ['hello', 'hi', 'hey', 'good morning', 'good evening', 'salam'],
    'goodbye': ['bye', 'goodbye', 'see you', 'farewell', 'good night'],
    'thanks': ['thanks', 'thank you', 'thx', 'appreciate it'],
    'how_are_you': ['how are you', 'how are you doing', 'how is it going'],
    'who_are_you': ['who are you', 'what are you', 'introduce yourself'],
    'your_name': ['your name', "what's your name", 'what is your name'],
    'your_age': ['how old are you', 'your age'],
    'origin': ['where are you from', 'where do you come from'],
    'capabilities': ['what can you do', 'your capabilities', 'what do you do',
                     'what are you able to do'],
    'help': ['help', 'can you help', 'i need help'],
    'meaning_of_life': ['meaning of life', 'purpose of life'],
    'love': ['love', 'what is love'],
    'friendship': ['friendship', 'friend'],
    'happiness': ['happiness', 'happy'],
    'money': ['money', 'finance', 'wealth'],
    'education': ['education', 'school', 'learning', 'study'],
    'science': ['science'],
    'technology': ['technology', 'tech'],
    'ai': ['artificial intelligence', 'what is ai', 'machine learning'],
    'ethiopia': ['ethiopia', 'ethiopian'],
    'africa': ['africa'],
    'health': ['health', 'healthy', 'fitness'],
    'food': ['food', 'recipe', 'cooking', 'eat'],
    'coffee': ['coffee', 'buna'],
    'sky_weather': ['weather', 'sky', 'rain', 'climate'],
    'time_day': ['time', 'what time', 'date', 'what day'],
    'math': ['math', 'mathematics', 'calculate', 'arithmetic'],
    'joke': ['joke', 'make me laugh', 'funny'],
    'praise': ['well done', 'good job', 'bravo'],
    'i_love_you': ['i love you'],
    'programming_intro': ['programming', 'coding', 'program'],
    'python_lang': ['python'],
    'javascript_lang': ['javascript', 'js'],
    'web_dev': ['web development', 'website', 'html', 'css'],
    'git': ['git', 'github', 'version control'],
    'algorithms': ['algorithm', 'data structure', 'sorting'],
    'book_writing': ['write a book', 'book writing', 'writing a novel'],
    'story_writing': ['write a story', 'short story', 'tell me a story'],
    'character_creation': ['create a character', 'character'],
    'essay': ['write an essay', 'essay'],
    'physics': ['physics'],
    'biology': ['biology'],
    'chemistry': ['chemistry'],
    'business': ['business', 'entrepreneur', 'startup'],
    'economy': ['economy', 'economics'],
    'geography': ['geography', 'countries'],
    'amharic_grammar': ['amharic grammar', 'geez grammar', 'grammar'],
    'language_learning': ['learn amharic', 'language learning', 'learn a language'],
    'stars_planets': ['stars', 'planets', 'space', 'universe'],
    'music_art': ['music', 'art', 'song', 'painting'],
    'sports': ['sports', 'football', 'soccer', 'running'],
    'internet_media': ['internet', 'social media', 'media', 'online'],
}


def _load_cache():
    try:
        with open(CACHE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    with open(CACHE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)


def _mymemory(text, cache):
    text = text.strip()
    if not text:
        return ''
    if text in cache:
        return cache[text]
    url = 'https://api.mymemory.translated.net/get?' + urllib.parse.urlencode(
        {'q': text, 'langpair': 'am|en', 'mt': '1'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers=_UA), timeout=15) as r:
                data = json.loads(r.read().decode('utf-8'))
            out = (data.get('responseData') or {}).get('translatedText') or ''
            if data.get('responseStatus') == 200 and out:
                out = out.strip()
                cache[text] = out
                return out
        except Exception:
            pass
        time.sleep(1.0 + attempt)
    return ''


def translate_to_en(text, cache, offline=False):
    if offline:
        return text
    return _mymemory(text, cache) or text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--offline', action='store_true',
                    help='do not call the network; keep Amharic text')
    args = ap.parse_args()

    with open(KB, encoding='utf-8') as f:
        kb = json.load(f)

    cache = _load_cache()
    out_intents = []
    total = 0
    for intent in kb.get('intents', []):
        tag = intent.get('tag')
        patterns = intent.get('patterns', [])
        responses = intent.get('responses', [])
        en_patterns = []
        for p in patterns:
            en = translate_to_en(p, cache, args.offline)
            if en and en not in en_patterns:
                en_patterns.append(en)
            total += 1
        # hand-written keywords first (they match best)
        for kw in KEYWORDS.get(tag, []):
            if kw not in en_patterns:
                en_patterns.insert(0, kw)
        if tag in OVERRIDES:
            en_responses = list(OVERRIDES[tag])
        else:
            en_responses = []
            for r in responses:
                en = translate_to_en(r, cache, args.offline)
                if en and en not in en_responses:
                    en_responses.append(en)
                total += 1
            if not en_responses:
                en_responses = list(responses)
        out_intents.append({'tag': tag, 'patterns': en_patterns,
                            'responses': en_responses})
        _save_cache(cache)
        sys.stderr.write(f'\r  translated {total} strings … {tag}')

    out_dict = {}
    for word, definition in (kb.get('dictionary') or {}).items():
        definitions = definition if isinstance(definition, list) else [definition]
        glosses = [translate_to_en(d, cache, args.offline) for d in definitions]
        out_dict[word] = [g for g in glosses if g] or definitions
    _save_cache(cache)

    payload = {
        'assistant': kb.get('assistant', {}),
        'intents': out_intents,
        'dictionary': out_dict,
        'meta': {'generated_by': 'tools/build_english_kb.py',
                 'offline': bool(args.offline)},
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    sys.stderr.write(f'\nwrote {OUT} ({len(out_intents)} intents, '
                     f'{len(out_dict)} dictionary words)\n')


if __name__ == '__main__':
    main()
