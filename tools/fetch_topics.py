#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_topics.py — build a factual, sourced knowledge set for Zer.

Turns a curated list of Wikipedia articles (English, plus the Amharic
interlanguage article when one exists) into instruction→answer SFT pairs on:

  * Ethiopian history and Ethiopia's place in Pan-Africanism / the diaspora
  * Black American history, racism and the civil-rights struggle
  * logic, reasoning and formal systems
  * free will, determinism and moral responsibility
  * power, sovereignty and political systems

Text is CC BY-SA 4.0 (Wikipedia). Every example's source article and revision
URL are recorded in `training/data/topics_manifest.json`; do not strip that
attribution. Only the article *lead* (intro) is used, so answers stay short,
factual and encyclopaedic rather than essay-length.

    python3 tools/fetch_topics.py
    python3 tools/fetch_topics.py --out training/data/topics_sft.jsonl
    python3 tools/fetch_topics.py --categories ethiopian_history,logic

Pure stdlib. Raw responses are cached under .hf-cache/topics/ so re-runs are
cheap and polite to Wikipedia.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, 'training', 'data', 'topics_sft.jsonl')
DEFAULT_MANIFEST = os.path.join(ROOT, 'training', 'data', 'topics_manifest.json')
CACHE = os.environ.get('ZER_TOPICS_CACHE') or \
    os.path.join(ROOT, '.hf-cache', 'topics')

_UA = {'User-Agent': 'Zer-topic-corpus/1.0 '
      '(https://github.com/ZebraCodeX/amharic-nlp-chatbot; open Amharic assistant)'}
LICENSE = 'CC BY-SA 4.0'

SYSTEM = (
    "Your name is Zer (ዘር), an Ethiopian AI assistant; 'ዘር' means 'seed'. "
    "Answer in the SAME language the user used: Amharic → Amharic in Ge'ez "
    "script, English → English. Be accurate, fair and give context."
)

# category -> [(english article title, english question templates)]
# Amharic templates are applied automatically when an Amharic article exists.
CATEGORIES = {
    'ethiopian_history': [
        ('History of Ethiopia', ['What is the history of Ethiopia?',
                                 'Give an overview of Ethiopian history.']),
        ('Kingdom of Aksum', ['What was the Kingdom of Aksum?',
                              'Explain the Kingdom of Aksum.']),
        ('Ethiopian Empire', ['What was the Ethiopian Empire?']),
        ('Zagwe dynasty', ['What was the Zagwe dynasty?']),
        ('Solomonic dynasty', ['What is the Solomonic dynasty?']),
        ('Battle of Adwa', ['What was the Battle of Adwa?',
                            'Why is the Battle of Adwa important?']),
        ('First Italo-Ethiopian War', ['What was the First Italo-Ethiopian War?']),
        ('Second Italo-Ethiopian War', ['What was the Second Italo-Ethiopian War?']),
        ('Menelik II', ['Who was Menelik II?']),
        ('Tewodros II', ['Who was Tewodros II?']),
        ('Yohannes IV', ['Who was Yohannes IV?']),
        ('Haile Selassie', ['Who was Haile Selassie?']),
        ('Derg', ['What was the Derg?']),
        ('Ethiopian Civil War', ['What was the Ethiopian Civil War?']),
        ('Ethiopian Orthodox Tewahedo Church',
         ['What is the Ethiopian Orthodox Tewahedo Church?']),
        ('Beta Israel', ['Who are the Beta Israel?']),
        ('Oromo people', ['Who are the Oromo people?']),
        ('Amhara people', ['Who are the Amhara people?']),
        ('Tigrayans', ['Who are the Tigrayan people?']),
        ('Grand Ethiopian Renaissance Dam',
         ['What is the Grand Ethiopian Renaissance Dam?']),
        ('Addis Ababa', ['What is Addis Ababa?']),
    ],
    'pan_africanism': [
        ('Pan-Africanism', ['What is Pan-Africanism?',
                            'Explain Pan-Africanism.']),
        ('Ethiopianism', ['What is Ethiopianism?']),
        ('African diaspora', ['What is the African diaspora?']),
        ('Negritude', ['What was Negritude?']),
        ('Rastafari', ['What is Rastafari?']),
        ('Marcus Garvey', ['Who was Marcus Garvey?']),
        ('W. E. B. Du Bois', ['Who was W. E. B. Du Bois?']),
        ('Organization of African Unity',
         ['What was the Organization of African Unity?']),
        ('African Union', ['What is the African Union?']),
        ('Kwame Nkrumah', ['Who was Kwame Nkrumah?']),
        ('Black nationalism', ['What is Black nationalism?']),
        ('Back-to-Africa movement', ['What was the Back-to-Africa movement?']),
    ],
    'black_american_history': [
        ('Slavery in the United States',
         ['What was slavery in the United States?',
          'How were enslaved Black people treated in the United States?']),
        ('Atlantic slave trade', ['What was the Atlantic slave trade?']),
        ('Reconstruction era', ['What was the Reconstruction era?']),
        ('Jim Crow laws', ['What were the Jim Crow laws?',
                           'How did Jim Crow laws affect Black Americans?']),
        ('Civil rights movement', ['What was the civil rights movement?']),
        ('Racism in the United States',
         ['How has racism affected Black people in the United States?',
          'What is racism in the United States?']),
        ('Great Migration (African American)',
         ['What was the Great Migration?']),
        ('Redlining', ['What is redlining?']),
        ('Mass incarceration in the United States',
         ['What is mass incarceration in the United States?']),
        ('Black Lives Matter', ['What is Black Lives Matter?']),
        ('Martin Luther King Jr.', ['Who was Martin Luther King Jr.?']),
        ('Malcolm X', ['Who was Malcolm X?']),
        ('Harriet Tubman', ['Who was Harriet Tubman?']),
        ('Frederick Douglass', ['Who was Frederick Douglass?']),
        ('Rosa Parks', ['Who was Rosa Parks?']),
        ('Thirteenth Amendment to the United States Constitution',
         ['What did the Thirteenth Amendment do?']),
        ('Fourteenth Amendment to the United States Constitution',
         ['What did the Fourteenth Amendment do?']),
        ('Brown v. Board of Education',
         ['What was Brown v. Board of Education?']),
        ('Voting Rights Act of 1965', ['What was the Voting Rights Act of 1965?']),
        ('Black Panther Party', ['What was the Black Panther Party?']),
    ],
    'logic_and_reasoning': [
        ('Logic', ['What is logic?', 'Explain logic.']),
        ('Propositional calculus', ['What is propositional calculus?']),
        ('First-order logic', ['What is first-order logic?']),
        ('Formal fallacy', ['What is a formal fallacy?']),
        ('Syllogism', ['What is a syllogism?']),
        ('Deductive reasoning', ['What is deductive reasoning?']),
        ('Inductive reasoning', ['What is inductive reasoning?']),
        ('Abductive reasoning', ['What is abductive reasoning?']),
        ('Critical thinking', ['What is critical thinking?']),
        ("Gödel's incompleteness theorems",
         ["What are Gödel's incompleteness theorems?"]),
        ("Occam's razor", ["What is Occam's razor?"]),
        ('Causality', ['What is causality?']),
    ],
    'free_will_and_philosophy': [
        ('Free will', ['What is free will?', 'Explain the problem of free will.']),
        ('Determinism', ['What is determinism?']),
        ('Compatibilism', ['What is compatibilism?']),
        ('Libertarianism (metaphysics)',
         ['What is libertarianism in metaphysics?']),
        ('Moral responsibility', ['What is moral responsibility?']),
        ('Agency (philosophy)', ['What is agency in philosophy?']),
        ('Consciousness', ['What is consciousness?']),
        ('Existentialism', ['What is existentialism?']),
        ('Stoicism', ['What is Stoicism?']),
    ],
    'power_and_politics': [
        ('Power (social and political)',
         ['What is power in politics and society?']),
        ('Political power', ['What is political power?']),
        ('Sovereignty', ['What is sovereignty?']),
        ('Social contract', ['What is the social contract?']),
        ('Democracy', ['What is democracy?']),
        ('Authoritarianism', ['What is authoritarianism?']),
        ('Separation of powers', ['What is the separation of powers?']),
        ('Soft power', ['What is soft power?']),
        ('Hard power', ['What is hard power?']),
        ('Hegemony', ['What is hegemony?']),
        ('Colonialism', ['What is colonialism?']),
        ('Decolonization', ['What is decolonization?']),
    ],
}

AM_QUESTIONS = ['ስለ {t} አብራራልኝ።', '{t} ምንድን ነው?', 'ስለ {t} ንገረኝ።']

_CITE = re.compile(r'\[\d+\]')
_WS = re.compile(r'\s+')
DAB = re.compile(r'may refer to', re.I)


def _get(host, params, cache_name):
    params = {**params, 'format': 'json'}
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.sha1((host + json.dumps(params, sort_keys=True))
                       .encode()).hexdigest()[:20]
    path = os.path.join(CACHE, f'{cache_name}_{key}.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    url = f'https://{host}/w/api.php?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_UA)
    delay = 2.0
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == 4:
                raise
            wait = float(exc.headers.get('Retry-After') or delay)
            print(f'  [rate-limit] sleeping {wait:.0f}s …', flush=True)
            time.sleep(wait)
            delay = min(delay * 2, 60)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    time.sleep(0.8)
    return data


def _page(host, params, cache_name):
    data = _get(host, params, cache_name)
    pages = (data.get('query') or {}).get('pages') or {}
    for page in pages.values():
        return page
    return None


def _extract(page, max_chars):
    if not page or 'missing' in page:
        return ''
    text = _CITE.sub('', page.get('extract') or '')
    text = _WS.sub(' ', text.replace('\n', ' ')).strip()
    if len(text) < 180 or DAB.search(text[:200]):
        return ''
    if len(text) > max_chars:
        text = text[:max_chars]
        cut = text.rfind('. ')
        text = text[:cut + 1] if cut > 200 else text
    return text


def _am_title(en_title):
    page = _page('en.wikipedia.org',
                 {'action': 'query', 'prop': 'langlinks', 'redirects': 1,
                  'lllang': 'am', 'titles': en_title}, 'll')
    if not page:
        return ''
    links = page.get('langlinks') or []
    return links[0]['*'] if links else ''


def _example(user, answer, url):
    return {'messages': [
        {'role': 'system', 'content': SYSTEM},
        {'role': 'user', 'content': user},
        {'role': 'assistant', 'content': answer},
    ], '_source': 'topic', '_url': url}


def build(categories, max_chars):
    examples, manifest = [], {}
    for cat in categories:
        if cat not in CATEGORIES:
            print(f'[warn] unknown category {cat!r}')
            continue
        print(f'[{cat}]')
        for title, questions in CATEGORIES[cat]:
            page = _page('en.wikipedia.org',
                         {'action': 'query', 'prop': 'extracts', 'exintro': 1,
                          'explaintext': 1, 'redirects': 1, 'titles': title},
                         'en')
            en = _extract(page, max_chars)
            if not en:
                print(f'  [skip] {title} (no usable lead)')
                continue
            url = 'https://en.wikipedia.org/wiki/' + urllib.parse.quote(
                (page.get('title') or title).replace(' ', '_'))
            manifest[title] = {'language': 'en',
                               'title': page.get('title') or title,
                               'url': url, 'license': LICENSE,
                               'chars': len(en)}
            for q in questions:
                examples.append(_example(q, en, url))

            am_title = _am_title(title)
            if not am_title:
                print(f'  ✓ {title} (en only)')
                continue
            am_page = _page('am.wikipedia.org',
                            {'action': 'query', 'prop': 'extracts', 'exintro': 1,
                             'explaintext': 1, 'redirects': 1,
                             'titles': am_title}, 'am')
            am = _extract(am_page, max_chars)
            if not am:
                print(f'  ✓ {title} (en; am lead unusable)')
                continue
            am_url = 'https://am.wikipedia.org/wiki/' + urllib.parse.quote(
                (am_page.get('title') or am_title).replace(' ', '_'))
            manifest[title + ' (am)'] = {'language': 'am',
                                         'title': am_page.get('title') or am_title,
                                         'url': am_url, 'license': LICENSE,
                                         'chars': len(am)}
            for tpl in AM_QUESTIONS:
                examples.append(_example(tpl.format(t=am_title), am, am_url))
            print(f'  ✓ {title} (en+am)')
    return examples, manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--manifest', default=DEFAULT_MANIFEST)
    ap.add_argument('--categories', default='all',
                    help='comma list of categories, or "all"')
    ap.add_argument('--max-chars', type=int, default=3000)
    args = ap.parse_args()

    cats = list(CATEGORIES) if args.categories == 'all' else \
        [c.strip() for c in args.categories.split(',') if c.strip()]
    examples, manifest = build(cats, args.max_chars)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        for ex in examples:
            f.write(json.dumps({'messages': ex['messages']},
                               ensure_ascii=False) + '\n')
    with open(args.manifest, 'w', encoding='utf-8') as f:
        json.dump({'license': LICENSE, 'source': 'Wikipedia',
                   'generated': time.strftime('%Y-%m-%d'),
                   'articles': manifest}, f, ensure_ascii=False, indent=2)

    print(f'\n→ {len(examples)} SFT examples from {len(manifest)} articles '
          f'({args.out})')
    print(f'→ attribution manifest {args.manifest}')
    return 0 if examples else 1


if __name__ == '__main__':
    raise SystemExit(main())
