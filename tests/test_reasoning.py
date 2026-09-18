# -*- coding: utf-8 -*-
"""Tests for the deterministic reasoning layer (computes, doesn't retrieve)."""
import unittest

import reasoning


class ReasoningTest(unittest.TestCase):
    def test_amharic_word_problem_subtract(self):
        self.assertIn('3', reasoning.solve('5 ወንድሞቼ አሉኝ 2ቱ ሄዱ ስንት ቀሩ?', 'am'))

    def test_multiplication_word_problem(self):
        self.assertIn('36', reasoning.solve('3 ሳጥን እያንዳንዱ 12 ብር ስንት ነው?', 'am'))

    def test_comparison(self):
        self.assertIn('5', reasoning.solve('5 እና 3 ትልቁ ማን ነው?', 'am'))

    def test_percentage(self):
        self.assertIn('20', reasoning.solve('የ200 10 በመቶ ስንት ነው?', 'am'))

    def test_average(self):
        self.assertIn('6', reasoning.solve('አማካይ 4 6 8 ስንት ነው?', 'am'))

    def test_fact_lookup(self):
        self.assertIn('299,792,458', reasoning.solve('የብርሃን ፍጥነት ስንት ነው?', 'am'))

    def test_english_subtraction(self):
        out = reasoning.solve('i have 5 and give away 2, how many are left', 'en')
        self.assertIn('3', out)

    def test_pi_is_not_matched_inside_words(self):
        # 'ethiopia' contains 'pi' — a substring match would be wrong.
        out = reasoning.solve('how many people live in ethiopia', 'en')
        self.assertNotIn('3.14159', out or '')
        self.assertIn('120', out or '')

    def test_unknown_reply_is_honest(self):
        out = reasoning.unknown_reply('100 ዶላር ስንት ብር ነው?', 'am')
        self.assertIsNotNone(out)
        self.assertNotIn('ጊዜ', out)          # not a time/date essay

    def test_unrelated_question_is_not_a_fact(self):
        self.assertIsNone(reasoning.solve('ስለ ፍቅር ንገረኝ', 'am'))


if __name__ == '__main__':
    unittest.main()
