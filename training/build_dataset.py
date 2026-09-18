#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_dataset.py — turn Zer's own data into an Amharic chat dataset (JSONL).

Sources (all already in this repo):
  * data/knowledge_base.json   — 54 intents: patterns → responses, dictionary
  * data/rich_answers.json     — deep, structured answers per topic
  * data/user_translations.json— translations humans taught (if present)
  * codegen.py                 — Amharic coding recipes (codegen output)

Output: training/data/amharic_sft.jsonl, one chat example per line:
  {"messages":[{"role":"system",...},{"role":"user",...},{"role":"assistant",...}]}

Run:  python3 training/build_dataset.py
This is a *seed* set for a first LoRA pass; real quality needs larger corpora
(see training/README.md).
"""
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
OUT = os.path.join(ROOT, 'training', 'data', 'amharic_sft.jsonl')
sys.path.insert(0, ROOT)

try:
    from codegen import RECIPES, generate as code_generate
except Exception:
    RECIPES, code_generate = [], None

SYSTEM = (
    "Your name is Zer (ዘር), an Ethiopian AI assistant; 'ዘር' means 'seed'. "
    "Always answer in the SAME language the user used: Amharic → Amharic in Ge'ez "
    "script, English → English. Be warm, accurate and thorough. When writing code "
    "you may use Amharic comments, strings and identifiers."
)

LANG_ASK = {
    'python': 'ፓይቶን', 'javascript': 'ጃቫስክሪፕት', 'html': 'HTML',
    'css': 'CSS', 'sql': 'SQL', 'bash': 'Bash', 'git': 'Git',
}


def load(name, default):
    path = os.path.join(DATA, name)
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def example(user, assistant, source):
    return {'messages': [
        {'role': 'system', 'content': SYSTEM},
        {'role': 'user', 'content': user.strip()},
        {'role': 'assistant', 'content': assistant.strip()},
    ], '_source': source}


def kb_examples(kb):
    out = []
    for intent in kb.get('intents', []):
        pats = [p for p in intent.get('patterns', []) if p.strip()]
        resp = [r for r in intent.get('responses', []) if r.strip()]
        if not pats or not resp:
            continue
        for p in pats:
            out.append(example(p, random.choice(resp), 'kb'))
    return out


def rich_examples(kb, rich):
    pats_by_tag = {i['tag']: i.get('patterns', []) for i in kb.get('intents', [])}
    out = []
    for tag, entry in rich.get('answers', {}).items():
        parts = [entry.get('summary', '')]
        points = [p for p in entry.get('points', []) if p]
        if points:
            parts.append('ዋና ነጥቦች፦\n' + '\n'.join('• ' + p for p in points))
        if entry.get('example'):
            parts.append('ምሳሌ፦ ' + entry['example'])
        answer = '\n\n'.join(p for p in parts if p)
        if not answer:
            continue
        questions = pats_by_tag.get(tag) or [f'ስለ {tag} ንገረኝ']
        for q in questions[:4]:
            out.append(example(q, answer, 'rich'))
    return out


def dict_examples(kb):
    out = []
    for word, meaning in (kb.get('dictionary') or {}).items():
        out.append(example(f'«{word}» ምን ማለት ነው?', f'«{word}» ማለት፡ {meaning}', 'dictionary'))
    return out


def translation_examples():
    data = load('user_translations.json', {}) or {}
    out = []
    for rec in data.get('translations', []) or []:
        am = (rec.get('text') or '').strip()
        en = (rec.get('corrected') or rec.get('original') or '').strip()
        if am and en:
            out.append(example(f'{am} ምን ማለት ነው?', f'{am} = {en}', 'translation'))
            out.append(example(f'translate {am} to English', f'{am} = {en}', 'translation'))
    return out


def code_examples():
    if not code_generate:
        return []
    out = []
    for keys, _title, sources in RECIPES:
        keyword = keys[0]
        for lang, source_lang in (('python', 'python'), ('javascript', 'javascript')):
            if source_lang not in sources:
                continue
            q = f'በ{LANG_ASK[lang]} {keyword} ኮድ ጻፍልኝ'
            reply = code_generate(q)
            if reply:
                out.append(example(q, reply, 'code'))
        # language-specific recipes (html/css/sql/bash/git) use their own language
        only = set(sources) - {'python', 'javascript'}
        for lang in only:
            q = f'በ{LANG_ASK.get(lang, lang)} {keyword} ጻፍልኝ'
            reply = code_generate(q)
            if reply:
                out.append(example(q, reply, 'code'))
    return out


def conversation_examples():
    """Real user conversations exported by `manage.py export_training_data`."""
    path = os.path.join(ROOT, 'training', 'data', 'conversations.jsonl')
    out = []
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                msgs = obj.get('messages')
                if isinstance(msgs, list) and len(msgs) >= 3:
                    out.append({'messages': msgs, '_source': 'conversation'})
    except (OSError, ValueError):
        pass
    return out


def main():
    random.seed(7)
    kb = load('knowledge_base.json', {})
    rich = load('rich_answers.json', {})

    examples = (kb_examples(kb) + rich_examples(kb, rich) + dict_examples(kb)
                + translation_examples() + code_examples() + conversation_examples())

    # de-duplicate identical (user, assistant) pairs
    seen, unique = set(), []
    for ex in examples:
        key = (ex['messages'][1]['content'], ex['messages'][2]['content'])
        if key in seen:
            continue
        seen.add(key)
        unique.append(ex)
    random.shuffle(unique)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        for ex in unique:
            f.write(json.dumps({'messages': ex['messages']}, ensure_ascii=False) + '\n')

    from collections import Counter
    counts = Counter(ex['_source'] for ex in unique)
    print(f'wrote {len(unique)} examples → {os.path.relpath(OUT, ROOT)}')
    for k, v in counts.most_common():
        print(f'  {k}: {v}')
    return len(unique)


if __name__ == '__main__':
    main()
