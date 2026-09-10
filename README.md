# የአማርኛ AI (Amharic NLP & Chat System)

A pure-Python, dependency-free deep-Amharic natural language toolkit plus a
conversational **chat-lite** assistant ("ጌና AI") that:

1. **Understands Amharic only** — everyone else gets a polite Amharic reminder.
2. **Minds the full Amharic Bible** (66 books, ~30,000 verses) using TF-IDF
   retrieval — ask topics like *«ስለ ፍቅር ምን ይላል?»* and get real verses back.
3. **Knows the fundamentals** — greetings, goodbyes, thanks, self-introduction,
   capabilities, help, and light conversation memory ("ተጨማሪ" shows more).
4. Comes with a **web chat UI** including a full Ge'ez on-screen keyboard.

No numpy. No sklearn. No flask. No GPU. Just Python 3.8+ standard library.

## Features

### NLP Toolkit (`amharic_nlp.py`)
- `AmharicNormalizer` — collapses homophone letters (ሀ/ሐ/ኀ→ሀ, ሠ→ሰ, ኣ→አ, ፀ→ጸ).
- `AmharicTokenizer` — Ge'ez-aware word segmentation (letters only, punctuation-safe).
- `AmharicStemmer` — rule-based prefix/suffix stripping (እንደ/ወደ/ስለ…, ዎች/ሮች/ኣት/ኣን…) with min-length guards.
- `StopWordFilter` — Amharic function-word removal (`data/stopwords.txt`, ~190 words).
- `SentenceSplitter` — splits on Amharic punctuation ። ፡ ፧ ፨.
- `TfidfVectorizer` + `DocumentIndex` — cosine similarity over Amharic docs.
- `BibleCorpus` — loads the Bible JSON, builds an inverted index, and searches it
  in **milliseconds**. Index is cached to `data/bible_index.json`.

### Conversational engine (`chatbot.py`)
- `AmharicAssistant.respond(text)` → `{reply, source, confidence, elapsed_ms}`.
- Intent recognition over `data/knowledge_base.json` (Amharic-only responses).
- TF-IDF Bible retrieval with confidence scoring.
- Context memory via "ተጨማሪ"/"ሌላ" (more verses from the last search).

### Web chat (`chat_app.py` + `templates/chat.html`)
- `GET /` — chat UI with Ge'ez on-screen keyboard & Amharic font.
- `GET /api/chat?text=…` — JSON reply.
- `GET /api/health` — health check.

## Run it

```bash
python3 chat_app.py            # defaults to http://0.0.0.0:8080
# or
PORT=9000 python3 chat_app.py
```

First startup builds the Bible index (a few seconds) — afterwards `data/bible_index.json`
makes it ~1s.

Try it in the browser, or via CLI:

```bash
python3 chatbot.py    # interactive Amharic chat in the terminal
```

## Try these

| You type (Amharic) | You get |
|---|---|
| ሰላም | greeting |
| ተጨማሪ | more of the last Bible verses |
| ስለ ፍቅር ምን ይላል | 1 Corinthians 13:4 ✓ |
| እምነት ምንድን ነው | faith verses |
| Hello | polite "Amharic only" reply |
| ደህና ሁን | goodbye |

## Data

- `data/amharic_bible.json` — Amharic Bible (from `magna25/amharic-bible-json`).
- `data/knowledge_base.json` — conversational intents & Amharic responses.
- `data/stopwords.txt` — Amharic stop words.
- `data/bible_index.json` — generated TF-IDF inverted index (cache).

## License

Unlicense — public domain. Do whatever you want with it.

## Author

ZebraCodeX