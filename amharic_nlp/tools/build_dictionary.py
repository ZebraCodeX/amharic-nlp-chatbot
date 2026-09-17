#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild `data/amharic_words.json` as a per-letter Amharic dictionary.

Reads the existing flat word list and adds an index grouped by the first fidel
family ("letter"), while keeping `words` for backwards compatibility:

    {
      "count": 20000,
      "letters":    [{"letter": "ሀ", "count": 1234}, ...],   # fidel order
      "by_letter":  {"ሀ": [{"w": "...", "f": 42}, ...], ...},
      "words":      [ ... flat, frequency order ... ]
    }

Usage:  python3 -m amharic_nlp.tools.build_dictionary
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from amharic_nlp.letters import family_order, letter_of   # noqa: E402

WORDS_PATH = os.path.join(ROOT, 'data', 'amharic_words.json')
OTHER = 'ሌላ'


def build(path=WORDS_PATH):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    words = data.get('words', [])

    groups = {}
    for entry in words:
        letter = letter_of(entry.get('w', '')) or OTHER
        groups.setdefault(letter, []).append(entry)

    ordered = family_order()
    letters = [{'letter': lt, 'count': len(groups[lt])} for lt in ordered if lt in groups]
    letters += [{'letter': lt, 'count': len(groups[lt])}
                for lt in sorted(k for k in groups if k not in ordered)]

    out = {
        'count': len(words),
        'letters': letters,
        'by_letter': {row['letter']: groups[row['letter']] for row in letters},
        'words': words,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    return out


if __name__ == '__main__':
    result = build()
    print(f'built {result["count"]} words into {len(result["letters"])} letters:')
    print('  ' + ' '.join(f'{r["letter"]}:{r["count"]}' for r in result['letters']))
