#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
training.py — end-to-end corpus training pipeline for the Amharic NLP app.

Turns the raw corpora under `amharic_nlp/corpora/{books,movies,articles,other}`
into the learned artifacts the chat server consumes:

    data/nl_model.json       n-gram model (unigram/bigram/trigram/starters)
    data/amharic_words.json  top vocabulary (spelling dictionary for the UI)
    data/vocabulary.txt      every observed word + its frequency
    data/sentences.json      frequent sentence bank (type-ahead completions)
    data/corpus_stats.json   per-domain training statistics

Usage:
    python3 -m amharic_nlp.training
    python3 -m amharic_nlp.training --corpora amharic_nlp/corpora \\
            --bible /tmp/amharic_bible.json --limit 200000
    python3 -m amharic_nlp.training --list-corpora   # what's on disk

Fully offline. Pure stdlib. Run `amharic_nlp.tools.download_corpora` first if
you want the bundled free sources.
"""

import argparse
import json
import os
from collections import Counter

from . import model as ngram
from . import corpus as corpuslib
from . import DATA_DIR, CORPORA_DIR

DOMAINS = ('books', 'movies', 'articles', 'other')


def collect(path, bible_path=None, limit=None, per_domain=None):
    """Stream all corpus sentences with per-domain stats.

    Returns (sentences, stats) where stats[domain] =
    {'files': n, 'sentences': n, 'tokens': n, 'unique_words': n}.

    `limit` caps the total sentences; `per_domain` caps each domain (so one
    giant dump can't crowd out the other sources).
    """
    sentences = []
    stats = {}
    token_counts = {}
    uniq = {}

    def add_sentence(domain, s):
        sentences.append(s)
        token_counts[domain] = token_counts.get(domain, 0)
        toks = ngram.tokenize(s)
        token_counts[domain] = token_counts.get(domain, 0) + len(toks)
        d = uniq.setdefault(domain, Counter())
        d.update(toks)

    domains = [d for d in DOMAINS if os.path.isdir(os.path.join(path, d))]
    if not domains:
        raise SystemExit(f'No corpus domain dirs found under {path!r}. '
                         'Run: python3 -m amharic_nlp.tools.download_corpora')

    for d in domains:
        domain_dir = os.path.join(path, d)
        for name in sorted(os.listdir(domain_dir)):
            fp = os.path.join(domain_dir, name)
            if not os.path.isfile(fp) or name.endswith('.gitkeep') \
                    or name.endswith('.json'):
                continue
            n = 0
            for s in corpuslib.iter_corpus_dir(os.path.join(domain_dir, name),
                                               limit=per_domain or limit):
                add_sentence(d, s)
                n += 1
                if per_domain and n >= per_domain:
                    break
                if limit and len(sentences) >= limit:
                    break
            if stats.get(d):
                stats[d]['sentences'] += n
                stats[d]['files'] += 1
            else:
                stats[d] = {'files': 1, 'sentences': n}
            if limit and len(sentences) >= limit:
                break
        if limit and len(sentences) >= limit:
            break

    for d, u in uniq.items():
        stats[d]['tokens'] = token_counts.get(d, 0)
        stats[d]['unique_words'] = len(u)

    if bible_path and os.path.exists(bible_path):
        bible_d = stats.get('books', {'files': 0, 'sentences': 0})
        n = 0
        for s in corpuslib.bible(bible_path):
            if len(ngram.tokenize(s)) < 2:
                continue
            add_sentence('books', s)
            n += 1
            if per_domain and n >= per_domain:
                break
            if limit and len(sentences) >= limit:
                break
        stats['books'] = {
            'files': bible_d['files'] + 1,
            'sentences': bible_d['sentences'] + n,
            'tokens': token_counts.get('books', 0),
            'unique_words': len(uniq.get('books', Counter())),
        }

    return sentences, stats


def top_vocabulary(sentences, top=20000, min_len=1, max_len=22):
    """Frequency-ranked dictionary: folded-deduplicated, keeps top spellings."""
    unigram = Counter()
    for s in sentences:
        unigram.update(w for w in ngram.tokenize(s) if min_len <= len(w) <= max_len)

    normalizer = _normalizer()

    # dedupe homophones: each folded form keeps its most frequent spelling
    best = {}
    for word, c in unigram.most_common():
        key = normalizer.normalize(word)
        if key not in best:
            best[key] = (word, c)
    ranked = sorted(best.values(), key=lambda x: (x[1], x[0]), reverse=True)
    return [{'w': w, 'f': c} for w, c in ranked[:top]], unigram


def _normalizer():
    from .toolkit import AmharicNormalizer
    return AmharicNormalizer()


def sentence_bank(sentences, out_path, min_freq=2, top=60000):
    """Persist the most common sentences (used for type-ahead completion)."""
    bank = Counter(s for s in sentences if len(s) >= 2)
    top_sents = [{'t': s, 'f': c} for s, c in bank.most_common(top)
                 if c >= min_freq]
    payload = {'count': len(top_sents), 'sentences': top_sents}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    return payload


def train(corpora=None, bible_path=None, limit=None, out_dir=DATA_DIR,
          top_words=20000, ngram_caps=None, per_domain=None):
    """Run the whole pipeline and report a stats summary dict."""
    corpora = corpora or CORPORA_DIR
    os.makedirs(out_dir, exist_ok=True)

    sentences, stats = collect(corpora, bible_path, limit=limit,
                               per_domain=per_domain)
    if not sentences:
        raise SystemExit('No sentences collected — is the corpus folder empty?')

    caps = ngram_caps or {}
    ngram.build_from_sentences(
        sentences,
        out=os.path.join(out_dir, 'nl_model.json'),
        **caps,
    )

    words, unigram = top_vocabulary(sentences, top=top_words)

    with open(os.path.join(out_dir, 'amharic_words.json'), 'w',
              encoding='utf-8') as f:
        json.dump({'count': len(words), 'words': words}, f,
                  ensure_ascii=False, separators=(',', ':'))

    with open(os.path.join(out_dir, 'vocabulary.txt'), 'w',
              encoding='utf-8') as f:
        for w, c in unigram.most_common():
            f.write(f'{w}\t{c}\n')

    bank = sentence_bank(sentences, os.path.join(out_dir, 'sentences.json'))

    summary = {
        'domains': stats,
        'total_sentences': len(sentences),
        'total_tokens': sum(d['tokens'] for d in stats.values()),
        'total_unique_words': len(unigram),
        'dictionary_words': len(words),
        'sentence_bank': bank['count'],
        'data_dir': out_dir,
    }
    with open(os.path.join(out_dir, 'corpus_stats.json'), 'w',
              encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def _print_summary(s):
    print('=== corpus training summary ===')
    for d, st in s['domains'].items():
        print(f'  {d:9s} sentences={st["sentences"]:>8d} '
              f'tokens={st["tokens"]:>10,d} files={st["files"]}')
    print(f'  total    sentences={s["total_sentences"]:>8d} '
          f'tokens={s["total_tokens"]:>10,d} unique_words={s["total_unique_words"]}')
    print(f'  dictionary={s["dictionary_words"]} words, '
          f'sentence bank={s["sentence_bank"]}')


def main():
    ap = argparse.ArgumentParser(description='Train the Amharic NLP model.')
    ap.add_argument('--corpora', default=CORPORA_DIR,
                    help='raw corpus root (default: amharic_nlp/corpora)')
    ap.add_argument('--bible', default=None,
                    help='amharic-bible-json file (adds book prose)')
    ap.add_argument('--limit', type=int, default=None,
                    help='stop after N total sentences (for huge dumps)')
    ap.add_argument('--per-domain', type=int, default=None,
                    help='cap each corpus domain at N sentences (balanced mix)')
    ap.add_argument('--out', default=DATA_DIR, help='artifact directory')
    ap.add_argument('--top-words', type=int, default=20000,
                    help='dictionary size (default 20000)')
    ap.add_argument('--max-uni', type=int, default=30000,
                    help='unigram words kept in nl_model.json')
    ap.add_argument('--max-prev', type=int, default=36000,
                    help='predictor (prev-word) vocabulary size')
    ap.add_argument('--list-corpora', action='store_true',
                    help='show what is on disk in corpora/ and exit')
    args = ap.parse_args()

    if args.list_corpora:
        for d in DOMAINS + ('(root)',):
            p = os.path.join(args.corpora, d if d != '(root)' else '')
            if not os.path.isdir(p):
                continue
            files = [n for n in sorted(os.listdir(p))
                     if os.path.isfile(os.path.join(p, n)) and not n.endswith('.gitkeep')]
            print(f'{d}: {", ".join(files) or "(empty)"}')
        return

    summary = train(corpora=args.corpora, bible_path=args.bible,
                    limit=args.limit, out_dir=args.out, top_words=args.top_words,
                    per_domain=args.per_domain,
                    ngram_caps={'max_uni': args.max_uni,
                                'max_prev_vocab': args.max_prev})
    _print_summary(summary)


if __name__ == '__main__':
    main()