# ሕሳር — Amharic AI (ChatGPT-style, Amharic only)

A pure-Python, dependency-free Amharic conversational AI ("ጃንዲ ምሳሌ") plus a
complete Amharic NLP toolkit. Think *ChatGPT that only speaks Amharic*:

- **Ask anything** — general knowledge (science, technology, AI, Ethiopia,
  Africa, health, food, coffee, friendship, life, and more) answered in Amharic.
- **Math** — `5 ጠቅላላ 7`, `17*4`, `አምስት ሲደመር ሦስት` → answers in digits **and**
  Amharic number words.
- **Dictionary** — ask «ኢንጄራ» ምን ማለት ነው? and get Amharic definitions.
- **Remembers your name** — «ስሜ አበበ ነው» and greetings become personal.
- **Amharic only** — English input gets a polite Amharic-only reminder.
- Web chat UI with a full **Ge'ez on-screen keyboard** (30 base × 7 vowel orders).

No numpy. No sklearn. No flask. No network model. Just Python 3.8+ stdlib and
intelligent vector-based intent matching.

## Features

### NLP toolkit (`amharic_nlp.py`)
- `AmharicNormalizer` — collapses homophones (ሀ/ሐ/ኀ→ሀ, ሠ→ሰ, ኣ→አ, ፀ→ጸ).
- `AmharicTokenizer` — Ge'ez word segmentation (letters only, punctuation-safe).
- `AmharicStemmer` — prefixes/suffixes stripping (እንደ/ወደ/ስለ…, ዎች/ሮች/ኣት/ኣን…).
- `StopWordFilter` — Amharic function words (`data/stopwords.txt`).
- `SentenceSplitter` — splits on Amharic punctuation, ። ፡ ፧ ፨.
- `TfidfVectorizer` + `DocumentIndex` — TF-IDF, cosine similarity (pure stdlib).
- `BibleCorpus` — *optional* Amharic Bible retrieval tool for the toolkit
  (bring your own `data/amharic_bible.json` if you want it; **not used** by the
  chat assistant).

### Conversation engine (`chatbot.py`)
- `AmharicAssistant` — vector-based intent matching over `data/knowledge_base.json`
  (25+ intents, ~70 Amharic patterns and responses).
- Arithmetic in Arabic digits or Amharic number words.
- Built-in Amharic dictionary (~30 words).
- Conversational memory: remembers the user's name.
- Honest, helpful fallbacks — never preachy, never religious.

### Web chat (`chat_app.py` + `templates/chat.html`)
- `GET /` — chat UI with Ge'ez on-screen keyboard & Amharic font.
- `GET /api/chat?text=…` — JSON `{reply, source, confidence, elapsed_ms}`.
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

| You type (Amharic) | Source | You get |
|---|---|---|
| ሰላም | intent | Amharic greeting |
| ስሜ አበበ ነው | name | remembers your name |
| AI ምንድን ነው? | intent | plain-language definition |
| ሰማይ ለምን ሰማያዊ ነው | intent | physics explanation |
| 5 ጠቅላላ 7 | math | መልሱ፡ 12 — አስራ ሁለት |
| አምስት ሲደመር ሦስት | math | መልሱ፡ 8 — ስምንት |
| «ኢንጄራ» ምን ማለት ነው? | dictionary | Amharic definition |
| Hello! | language_gate | polite Amharic-only reply |
| ደህና ሁን | intent | farewell |

## Data

- `data/knowledge_base.json` — conversational intents, Amharic responses, dictionary.
- `data/stopwords.txt` — Amharic stop words.
- *(Optional)* `data/amharic_bible.json` — Amharic Bible, used only by the
  toolkit's optional `BibleCorpus` for researchers, never by the chatbot.

## License

Unlicense — public domain.

## Author

ZebraCodeX