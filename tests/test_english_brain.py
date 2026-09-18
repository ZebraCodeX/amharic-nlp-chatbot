# -*- coding: utf-8 -*-
"""Tests for the self-contained English brain (no LLM, no translation)."""
import unittest


class EnglishBrainTest(unittest.TestCase):
    def setUp(self):
        import english_brain
        self.brain = english_brain

    def test_kb_is_compiled(self):
        self.assertTrue(self.brain.available())

    def test_never_mentions_a_model(self):
        for text in ('hello', 'tell me about the cosmos', 'who are you'):
            reply = self.brain.respond(text)['reply'].lower()
            self.assertNotIn('language model', reply)
            self.assertNotIn('offline right now', reply)

    def test_greeting_and_identity(self):
        self.assertEqual(self.brain.respond('hello')['lang'], 'en')
        self.assertIn('ethiopian', self.brain.respond('who are you')['reply'].lower())

    def test_math_in_words_and_digits(self):
        self.assertIn('8', self.brain.respond('what is 5 plus 3')['reply'])
        self.assertIn('96', self.brain.respond('12 times 8')['reply'])

    def test_capabilities_are_listed(self):
        reply = self.brain.respond('what can you do')['reply']
        self.assertIn('chat', reply.lower())

    def test_amharic_word_meaning(self):
        reply = self.brain.respond('what does ሰላም mean')['reply']
        self.assertIn('ሰላም', reply)

    def test_time_and_date_answer(self):
        self.assertIn(':', self.brain.respond('what time is it')['reply'])
        self.assertIn('Ethiopian', self.brain.respond('what day is today')['reply'])


if __name__ == '__main__':
    unittest.main()
