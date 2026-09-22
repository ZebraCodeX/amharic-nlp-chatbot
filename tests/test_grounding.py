# -*- coding: utf-8 -*-
"""Tests for offline grounding (retrieval from Zer's own local data)."""
import os
import unittest

import grounding


class GroundingTest(unittest.TestCase):
    def setUp(self):
        grounding.clear_cache()

    def test_finds_fact_in_english(self):
        facts = grounding.retrieve('what is the speed of light?', 'en')
        self.assertTrue(facts)
        self.assertIn('299,792,458', facts[0])

    def test_finds_fact_in_amharic(self):
        facts = grounding.retrieve('የብርሃን ፍጥነት ስንት ነው?', 'am')
        self.assertTrue(facts)
        self.assertIn('299,792,458', facts[0])

    def test_answer_matches_requested_language(self):
        en = grounding.retrieve('speed of light', 'en')[0]
        am = grounding.retrieve('speed of light', 'am')[0]
        self.assertNotEqual(en, am)

    def test_unrelated_query_returns_nothing(self):
        self.assertEqual(grounding.context('write me a haiku about rain', 'en'), '')

    def test_context_block_is_model_ready(self):
        ctx = grounding.context('speed of light', 'en')
        self.assertIn('299,792,458', ctx)

    def test_deduplicates(self):
        facts = grounding.retrieve('speed of light', 'en', limit=5)
        self.assertEqual(len(facts), len(set(facts)))


class LlmGroundingToggleTest(unittest.TestCase):
    def test_grounded_system_appends_and_respects_toggle(self):
        import llm
        user = 'speed of light'
        grounded = llm._grounded_system('SYS', user, 'en')
        self.assertIn('299,792,458', grounded)

        os.environ['ZER_GROUNDING'] = '0'
        try:
            self.assertEqual(llm._grounded_system('SYS', user, 'en'), 'SYS')
        finally:
            os.environ.pop('ZER_GROUNDING', None)


if __name__ == '__main__':
    unittest.main()
