# -*- coding: utf-8 -*-
"""Tests for the held-out topic eval split (training/build_eval.py + clean)."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'training'))

import build_eval          # noqa: E402
import clean_dataset       # noqa: E402

EVAL = os.path.join(ROOT, 'training', 'data', 'topics_eval.jsonl')
KEYS = os.path.join(ROOT, 'training', 'data', 'topics_eval_keys.json')
CLEAN = os.path.join(ROOT, 'training', 'data', 'amharic_sft.clean.jsonl')


def _write(tmp, name, payload):
    path = os.path.join(tmp, name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(payload)
    return path


class KeyNormalisationTest(unittest.TestCase):
    def test_both_modules_agree(self):
        self.assertEqual(build_eval._key('  Hello   World '),
                         clean_dataset._key('  Hello   World '))


class LoadHoldoutTest(unittest.TestCase):
    def test_reads_keys_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, 'keys.json', json.dumps(['ፍጥነት', 'Battle of Adwa']))
            keys = clean_dataset._load_holdout(path)
        self.assertEqual(keys, {'ፍጥነት', 'battle of adwa'})

    def test_reads_eval_jsonl(self):
        row = {'messages': [{'role': 'user', 'content': 'Who was Menelik II?'},
                            {'role': 'assistant', 'content': '…'}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, 'eval.jsonl', json.dumps(row) + '\n')
            keys = clean_dataset._load_holdout(path)
        self.assertEqual(keys, {'who was menelik ii?'})


@unittest.skipUnless(os.path.exists(EVAL) and os.path.exists(KEYS),
                     'run training/build_eval.py first')
class EvalSplitDataTest(unittest.TestCase):
    def test_eval_file_is_well_formed(self):
        with open(EVAL, encoding='utf-8') as f:
            for line in f:
                msgs = json.loads(line)['messages']
                self.assertGreaterEqual(len(msgs), 3)
                self.assertEqual(msgs[-1]['role'], 'assistant')
                self.assertTrue(msgs[-1]['content'].strip())

    @unittest.skipUnless(os.path.exists(CLEAN), 'clean set not built')
    def test_no_eval_question_leaks_into_training(self):
        with open(KEYS, encoding='utf-8') as f:
            hold = set(json.load(f))
        self.assertTrue(hold)
        leaks = 0
        with open(CLEAN, encoding='utf-8') as f:
            for line in f:
                for m in json.loads(line)['messages']:
                    if m['role'] == 'user':
                        if clean_dataset._key(m['content']) in hold:
                            leaks += 1
                        break
        self.assertEqual(leaks, 0)


if __name__ == '__main__':
    unittest.main()
