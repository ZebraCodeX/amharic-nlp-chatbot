# ሕሳር — Amharic AI (ChatGPT-style, Amharic only)

A pure-Python, dependency-free Amharic conversational AI plus a complete
Amharic NLP toolkit. Think *ChatGPT that only speaks Amharic*:

- **Ask anything** — 50+ topics (programming, book/story writing, science,
  physics/biology/chemistry, business & economy, geography, Ethiopia, health,
  music, sports, Amharic grammar, learning tips, and much more).
- **Code writes code** — built-in snippet generator: ask «ፓይቶን ኮድ ጻፍልኝ»
  or *"write a python function to sort a list"* and get working Python,
  JavaScript, HTML, CSS, JSON or Bash examples.
- **Deep learning engine** — the assistant *remembers facts you teach it*
  («አስታውስ የማርያም ቡና ጥቁር ነው»), answers follow-up questions
  («እና ታዲያ?»), and keeps ~10 turns of conversation context.
- **Math** — `5 ጠቅላላ 7`, `17*4`, `አምስት ሲደመር ሦስት` → digits **and**
  Amharic number words (100+ number words supported).
- **Dictionary** — «ኢንጄራ» ምን ማለት ነው? → 46 Amharic definitions.
- **Side-by-side EN translator** — flip the *EN ⇄ አማ* toggle and every
  message (yours and ሕሳር's) is translated to English using a free, keyless
  translation API (**MyMemory**, with Google Translate as fallback).
- **Gboard-style screen keyboard** — light Google-style keys, a predictive
  word strip, long-press any letter to pick the 7 vowel orders, backspace
  (long-press to clear), symbols & Amharic-numerals page, and an Enter key.
- **Remembers your name** — «ስሜ አበበ ነው» makes greetings personal.
- **Amharic only** — English input gets a polite Amharic-only reminder
  (except programming-language code requests).

No numpy. No sklearn. No flask. No network model. Just Python 3.8+ stdlib +
one free HTTP translate call when the translator is switched on.

## Features

### NLP toolkit (`amharic_nlp.py`)
- `AmharicNormalizer` — collapses homophones (ሀ/ሐ/ኀ→ሀ, ሠ→ሰ, ኣ→አ, ፀ→ጸ).
- `AmharicTokenizer` — Ge'ez word segmentation (letters only, punctuation-safe).
- `AmharicStemmer` — prefixes/suffixes stripping (እንደ/ወደ/ስለ…, ዎች/ሮች/ኣት/ኣን…).
- `StopWordFilter` — Amharic function words (`data/stopwords.txt`).
- `SentenceSplitter` — splits on Amharic punctuation ። ፡ ፧ ፨.
- `TfidfVectorizer` + `DocumentIndex` — TF-IDF, cosine similarity (pure stdlib).
- `BibleCorpus` — *optional* Amharic Bible retrieval tool for researchers
  (bring your own `data/amharic_bible.json` if you want it; **not used** by the
  chat assistant).

### Conversation engine (`chatbot.py`)
- `AmharicAssistant` — vector-based intent matching over `data/knowledge_base.json`
  (54 intents, ~120 Amharic patterns & responses).
- Teachable long-term memory persisted to `data/user_memory.json`.
- Multi-turn follow-ups and conversational context.
- Mini code-snippet generator (Python / JavaScript / HTML / CSS / JSON / Bash).
- Arithmetic in Arabic digits or Amharic number words.
- Word definitions via the built-in dictionary.

### Translation (`translator.py`)
- `translate(text, src, dst)` — free, keyless Amharic ⇄ English.
- MyMemory primary engine, Google Translate (gtx) fallback, in-memory cache.
- Works offline (`online=False`) when the network is unavailable.

### Web chat (`chat_app.py` + `templates/chat.html`)
- `GET /` — chat UI with the Gboard-style keyboard & Amharic font.
- `GET /api/chat?text=…` — JSON `{reply, source, confidence, elapsed_ms}`.
- `GET /api/translate?text=…&to=en|am` — JSON `{translated}`.
- `GET /api/health` — health check.

## Run it

```bash
python3 chat_app.py            # http://0.0.0.0:8080
# or
PORT=9000 python3 chat_app.py
```

Command-line demo:

```bash
python3 chatbot.py
```

## Try these

| You type | What happens |
|---|---|
| ሰላም | Amharic greeting |
| ስሜ አበበ ነው | remembers your name |
| AI ምንድን ነው? | plain-language definition |
| ፕሮግራም ምንድን ነው? | programming intro |
| ፓይቶን ኮድ ጻፍልኝ | Python code sample |
| መጽሐፍ መጻፍ እንዴት | book-writing structure |
| 5 ጠቅላላ 7 | math → መልሱ፡ 12 — አስራ ሁለት |
| «ኢንጄራ» ምን ማለት ነው? | Amharic definition |
| አስታውስ የማርያም ቡና ጥቁር ነው | saves a fact; later «ማርያም» recalls it |
| ስለ ኢትዮጵያ ንገረኝ · እና ታዲያ? | answer + follow-up |
| Hello! | polite Amharic-only reminder |
| *EN ⇄ አማ toggle ON* | every message also in English |

## Data

- `data/knowledge_base.json` — conversational intents, responses, dictionary.
- `data/stopwords.txt` — Amharic stop words.
- `data/user_memory.json` — facts taught to the assistant (created at runtime).
- *(Optional)* `data/amharic_bible.json` — Amharic Bible, only for the toolkit's
  optional `BibleCorpus`, never for the chatbot.

## License

Unlicense — public domain.

## Author

ZebraCodeX