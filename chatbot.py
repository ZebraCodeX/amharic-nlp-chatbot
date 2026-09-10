# -*- coding: utf-8 -*-
"""
chatbot.py — Amharic conversational AI assistant.

The assistant combines:
  1. Intent recognition over a hand-written Amharic knowledge base
  2. TF-IDF retrieval over the full Amharic Bible for topic questions
  3. Light conversation memory (e.g. user can ask for "more" results)

All processing happens in Amharic only, fully offline, pure standard library.
"""

import json
import os
import random
import re

from amharic_nlp import (
    AmharicNormalizer,
    AmharicTokenizer,
    StopWordFilter,
    AmharicStemmer,
    BibleCorpus,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
KB_FILE = os.path.join(DATA_DIR, 'knowledge_base.json')
BIBLE_FILE = os.path.join(DATA_DIR, 'amharic_bible.json')
BIBLE_INDEX_FILE = os.path.join(DATA_DIR, 'bible_index.json')


class AmharicAssistant:
    """Main conversational system. Talk to it in Amharic."""

    def __init__(self, bible_path=BIBLE_FILE, knowledge_base_path=KB_FILE,
                 load_bible=True, auto_cache=True):
        self.normalizer = AmharicNormalizer()
        self.tokenizer = AmharicTokenizer()
        self.stemmer = AmharicStemmer()
        self.stop_filter = StopWordFilter()

        self.intents = self._load_intents(knowledge_base_path)
        self._more_memory = []      # last Bible search results, doc indices per type

        # Replace the raw tokenizer with a Unicode-aware one for ASCII detection
        self._latin_re = re.compile(r'[a-zA-Z0-9\u0041-\u024f]+')

        self.bible = None
        if load_bible and os.path.exists(bible_path):
            self.bible = BibleCorpus(bible_path)
            self.bible.load()
            if auto_cache and os.path.exists(BIBLE_INDEX_FILE):
                self.bible.load_index(BIBLE_INDEX_FILE)
                self._index_loaded = True
            else:
                self.bible.build_index()
                self._index_loaded = False
                try:
                    self.bible.save_index(BIBLE_INDEX_FILE)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _load_intents(self, path):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        intents = {}
        for item in data['intents']:
            intents[item['tag']] = item
        return intents

    def _primary_latin(self, text):
        """Return True if the text is mostly Latin/ASCII (English, numerals)."""
        letters = [ch for ch in text if ch.isalpha()]
        if not letters:
            return False
        latin = sum(1 for ch in letters if '\u0041' <= ch <= '\u024f')
        return latin / len(letters) > 0.6

    def _normalize(self, text):
        return self.normalizer.normalize(text)

    def _match_keywords(self, text, keyword_list):
        t = self._normalize(text)
        for kw in keyword_list:
            if kw in t:
                return True
        return False

    # ------------------------------------------------------------------
    # intent dispatch
    # ------------------------------------------------------------------
    def _respond_intent(self, tag):
        item = self.intents.get(tag)
        if not item:
            return None
        return random.choice(item['responses'])

    def try_intent(self, text):
        """Return (response, tag) if a knowledge-base intent matched, else None."""
        t = self._normalize(text)
        truth = self.stop_filter.filter(self.tokenizer.tokenize(t))

        # -- greetings (short messages, highest priority) ----------------
        if self._match_keywords(text, ['ሰላም', 'ታዲያስ', 'ሃሎ', 'እሄንዳይ']) and len(text) <= 12:
            if any(x in text for x in ['ሰላም', 'ታዲያስ', 'ሃሎ']):
                return self._respond_intent('greeting'), 'greeting'
        if self._match_keywords(text, ['እንደምን']) if not text.startswith('እንዴት') else False:
            return self._respond_intent('greeting'), 'greeting'

        # -- farewell ----------------------------------------------------
        if self._match_keywords(text, ['ደህና ሁን', 'በስንብት', 'እንደነገርን', 'ሰላም ቀሪ', 'ባይ ']):
            return self._respond_intent('goodbye'), 'goodbye'

        # -- thanks ------------------------------------------------------
        if self._match_keywords(text, ['አመሰግናለሁ', 'አመሰግናሃለሁ', 'በጣም ቀና']):
            return self._respond_intent('thanks'), 'thanks'

        # -- how are you -------------------------------------------------
        if self._match_keywords(text, ['እንዴት ነህ', 'እንዴት ነሽ', 'እንዴት ናችሁ', 'እንዴት ዋልክ']):
            return self._respond_intent('how_are_you'), 'how_are_you'

        # -- who are you -------------------------------------------------
        if self._match_keywords(text, ['ማን ነህ', 'ማን ነሽ', 'ማንነትህ', 'ስምህ']):
            return self._respond_intent('who_are_you'), 'who_are_you'

        # -- capabilities ------------------------------------------------
        if self._match_keywords(text, ['ምን ትሰራለህ', 'ችሎታ', 'ምን ማድረግ ትችላለህ']):
            return self._respond_intent('capabilities'), 'capabilities'

        # -- help --------------------------------------------------------
        if self._match_keywords(text, ['እርዳኝ', 'እገዛ', 'መመሪያ', 'ምን ላድርግ']):
            return self._respond_intent('help'), 'help'

        # -- praise ------------------------------------------------------
        if self._match_keywords(text, ['ብልህ', 'አሪፍ', 'ኃይለኛ', 'ጥሩ ነህ']):
            return self._respond_intent('praise'), 'praise'

        # -- "more" continuation ----------------------------------------
        if self._match_keywords(text, ['ሌላ', 'ተጨማሪ', 'ይቀጥል', 'ምን ሌላ']) and self._more_memory:
            return self._more_response(), 'more'

        return None, None

    def _more_response(self):
        """Serve the next batch of the current Bible search."""
        if not self._more_memory:
            return "ከእነዚህ በላይ ሌላ አልተገኘም። ሌላ ጥያቄ ጠይቀኝ።"
        responses = []
        for item in self._more_memory:
            if item.get('used'):
                continue
            item['used'] = True
            responses.append(self._format_verse(item))
            if len(responses) >= 2:
                break
        if not responses:
            self._more_memory = []
            return "ከእነዚህ በላይ ሌላ አልተገኘም። አዲስ ጥያቄ ጠይቀኝ።"
        return '\n\n'.join(responses)

    def _format_verse(self, item):
        ref = item['ref']
        text = item['text']
        return f"{ref}\n\n{text}"

    # ------------------------------------------------------------------
    # main entry point
    # ------------------------------------------------------------------
    def respond(self, text):
        """Return a dict with the assistant's reply, source and confidence."""
        text = text.strip()
        if not text:
            return {'reply': 'ምን ትፈልጋለህ? በአማርኛ ጻፍልኝ።', 'source': 'empty', 'confidence': 1.0}

        if self._primary_latin(text):
            return {
                'reply': 'እባክህ በአማርኛ ጻፍልኝ! እኔ የተፈጠርኩት የአማርኛ ቋንቋን ለመረዳት ነው። እንግሊዝኛን አልገባኝም።',
                'source': 'language_gate', 'confidence': 1.0,
            }

        # Knowledge base intents first
        response, tag = self.try_intent(text)
        if response:
            return {'reply': response, 'source': f'intent:{tag}', 'confidence': 0.95}

        # Bible topical retrieval
        if self.bible is not None:
            results = self.bible.search(text, k=6)
            if results:
                self._more_memory = []
                # record for "more" requests
                for score, verse in results:
                    ref, content = verse
                    self._more_memory.append({
                        'ref': ref,
                        'text': content,
                        'score': score,
                        'used': False,
                    })
                top = self._more_memory[:2]
                for m in top:
                    m['used'] = True
                reply = '\n\n'.join(self._format_verse(m) for m in top)
                conf = min(0.95, 0.4 + results[0][0])
                return {'reply': reply, 'source': 'bible', 'confidence': round(conf, 3)}

        # Fallback
        fallback = (
            "ስለ ርዕስህ በመጽሐፍ ቅዱስ ውስጥ በቂ መረጃ አላገኘሁም። "
            "ተጨማሪ ዝርዝር ስጠኝ፣ ወይም እንዲህ ጠይቀኝ፡- «ስለ ፍቅር ምን ይላል?» «ስለ እምነት ጥቅስ ንገረኝ»"
        )
        return {'reply': fallback, 'source': 'fallback', 'confidence': 0.15}


def demo_chat():
    """Interactive command-line chat session in Amharic."""
    print("የአማርኛ አጋር AI — አማርኛን ጻፍ ወይም «ደህና ሁን» በል።")
    print("Loading assistant (this may take a moment the first time)...")
    assistant = AmharicAssistant()
    print("\nReady! Start chatting (type 'quit' or say ደህና ሁን to exit).\n")
    while True:
        try:
            user = input('አንተ  > ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nደህና ሁን!')
            break
        if not user:
            continue
        if user.lower() in ('quit', 'exit', 'q'):
            print('AI    > ደህና ሁን! እንደገና ይገናኘን።')
            break
        result = assistant.respond(user)
        print(f'AI    > {result["reply"]}')


if __name__ == '__main__':
    demo_chat()