# ዘር (Zer) — Amharic AI

[![Live on Fly.io](https://img.shields.io/badge/live-hisar--amharic--ai.fly.dev-e94560)](https://hisar-amharic-ai.fly.dev)

**▶ Live app / PWA: <https://hisar-amharic-ai.fly.dev>** — the chat, the Amharic
keyboard and the translation review UI at
[`/review`](https://hisar-amharic-ai.fly.dev/review), deployed on Fly.io.
Open it and choose **Install app** to add it to your device (Android, iOS,
Windows, macOS, Linux).

## Download

Get native builds from
[**GitHub Releases → latest**](https://github.com/ZebraCodeX/amharic-nlp-chatbot/releases/latest):

| Platform | Download | Stores |
| --- | --- | --- |
| **Web / PWA** | [hisar-amharic-ai.fly.dev](https://hisar-amharic-ai.fly.dev) | installable from the browser |
| **Android** | [`Hisar.apk`](https://github.com/ZebraCodeX/amharic-nlp-chatbot/releases/latest/download/Hisar.apk) · [`Hisar.aab`](https://github.com/ZebraCodeX/amharic-nlp-chatbot/releases/latest/download/Hisar.aab) | Google Play |
| **iOS** | simulator build via CI · signed `.ipa` needs Apple signing | App Store / TestFlight |
| **Windows** | [`Hisar-Setup.exe`](https://github.com/ZebraCodeX/amharic-nlp-chatbot/releases/latest/download/Hisar-Setup.exe) | Microsoft Store |
| **macOS** | [`Hisar.dmg`](https://github.com/ZebraCodeX/amharic-nlp-chatbot/releases/latest/download/Hisar.dmg) | Mac App Store |
| **Linux** | [`Hisar.AppImage`](https://github.com/ZebraCodeX/amharic-nlp-chatbot/releases/latest/download/Hisar.AppImage) · [`Hisar.deb`](https://github.com/ZebraCodeX/amharic-nlp-chatbot/releases/latest/download/Hisar.deb) | Snap / Flathub |

The Windows/macOS builds are **unsigned by default** (SmartScreen/Gatekeeper
warn) and Android ships a **debug-signed APK** — add signing secrets to produce
store-ready installers (details in [`PACKAGING.md`](PACKAGING.md)).

Apps are built by GitHub Actions (`.github/workflows/`) from one React
codebase — **Capacitor** for Android/iOS and **Electron** for desktop. See
[`PACKAGING.md`](PACKAGING.md) for signing keys and store submission.

The AI assistant is **Zer (ዘር)** — Amharic for *seed*. Say **“Hey Zer”** and
talk to it in **Amharic or English**: Zer detects the language you spoke and
answers in the same language, out loud, in a live voice conversation.

The web app is a **Django REST Framework API** (`backend/`) with a
**React + TypeScript** single-page front end (`frontend/`), styled with a custom
Ethiopian-inspired *parchment & fidel* design system. The NLP brain stays pure
Python stdlib and is reused unchanged behind the API.

## Live voice conversation (Zer)

Open **[`/voice`](https://hisar-amharic-ai.fly.dev/voice)** and press the mic (or
toggle **Hey Zer** for hands-free). One round trip is
`audio → STT → language detection → Zer → TTS → audio`, all open source:

| Stage | Library | Notes |
| --- | --- | --- |
| Speech-to-text | **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** (OpenAI Whisper on CTranslate2) | multilingual, **auto language detection** (`am` / `en`); model size via `ZER_WHISPER_MODEL` (default `base`) |
| Language routing | `zer.py` | Ge'ez script → Amharic, Latin → English; Whisper's detected language wins |
| Brain | Zer (`zer.py` + `chatbot.py`) | replies in the detected language; LLM-backed when configured, offline rules otherwise |
| Text-to-speech | **Meta MMS-TTS** (`facebook/mms-tts-amh`/`-eng`) or **[eSpeak NG](https://github.com/espeak-ng/espeak-ng)** | MMS is higher quality (optional, `torch`); eSpeak NG is always available and supports Amharic |
| Wake word | Browser `SpeechRecognition` | “hey zer” / “ሄይ ዘር”; push-to-talk always works |

If the server speech stack is unavailable (e.g. a small self-host), the page
transparently falls back to the browser's Web Speech API. Endpoints:
`GET /api/speech/status/`, `POST /api/speech/transcribe/`,
`POST /api/speech/synthesize/`, `POST /api/voice/turn/`.

> **Docker** installs `espeak-ng` + `faster-whisper`; models cache on the
> `hisar_data` volume (`HF_HOME=/app/userdata/hf`). Mic permissions for the
> packaged apps are wired in `PACKAGING.md` / the CI workflows.

```text
backend/    Django 6 + DRF  — REST API, serves the built SPA with gunicorn
frontend/   Vite + React 18 + TypeScript — chat, keyboard, translation review
chatbot.py  the assistant brain (used by backend/api/services.py)          ─┐
translator.py  Amharic ⇄ English + user-correction store                    ├─ shared
amharic_nlp/   trained n-gram / dictionaries / suggester                   ─┘
chat_app.py + templates/ + static/   legacy stdlib server (kept for reference)
```

## Develop (Django + React)

```bash
# 1) backend
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cd backend && ../.venv/bin/python manage.py runserver        # http://127.0.0.1:8000

# 2) frontend (separate terminal) — Vite proxies /api to Django
cd frontend && npm install && npm run dev                    # http://127.0.0.1:5173

# 3) production-style build (React → backend/static/spa, then gunicorn)
cd frontend && npm run build
cd ../backend && ../.venv/bin/python manage.py collectstatic --noinput
../.venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

API routes live under `/api/` (`chat`, `translate`, `translations`,
`translations/stats`, `translations/verify`, `words`, `ngram`, `suggest`,
`llm-status`, `health`). Django tests: `cd backend && python manage.py test api`.

A pure-Python, dependency-free Amharic conversational AI plus a complete
Amharic NLP toolkit. An Amharic-speaking AI assistant:

- **Real AI brain (optional)** — when any OpenAI-compatible endpoint is
  reachable (a local **Ollama**, or a keyed service) ሕሳር becomes a true
  generative LLM that *only speaks Amharic*: writes poems, novels, essays,
  websites and code, and answers open questions. The rule brain still gives
  super-fast, deterministic answers for greetings, math, definitions and
  memory; everything creative or open-ended goes to the LLM. Without a backend
  it silently keeps working on the offline rule brain.
- **Multi-domain corpus language model** — the assistant is trained (fully
  offline, pure stdlib) on **books + movies + articles + web**, not just the
  Bible: `data/nl_model.json` is a 2-gram/3-gram model over a combined corpus
  and powers *next-word hints* **and full sentence completion** in the
  keyboard (see `/api/suggest` below).
- **Ask anything** — 50+ topics (programming, book/story writing, science,
  physics/biology/chemistry, business & economy, geography, Ethiopia, health,
  music, sports, Amharic grammar, learning tips, and much more).
- **Code writes code** — built-in snippet generator: ask «ፓይቶን ኮድ ጻፍልኝ»
  or *"write a python function to sort a list"* and get working Python,
  JavaScript, HTML, CSS, JSON or Bash examples.
- **Deep learning engine** — the assistant *remembers facts you teach it*
  («አስታውስ የማርያም ቡና ጥቁር ነው»), answers follow-up questions
  («እና ታዲያ?»), and keeps ~10 turns of conversation context.
- **In-depth answers, not one-liners** — every substantive topic (40+ of them)
  answers with a *summary + ዋና ነጥቦች bullets + example + suggested follow-ups*,
  composed from the curated `data/rich_answers.json`. Ask «ስለ ኢትዮጵያ ንገረኝ» and
  get real depth; ask «በአጭሩ» and get a concise reply. «እና ታዲያ?» adds the *next*
  unseen points instead of repeating. The web UI renders the follow-ups as
  tappable chips.
- **Math** — `5 ጠቅላላ 7`, `17*4`, `አምስት ሲደመር ሦስት` → digits **and**
  Amharic number words (100+ number words supported).
- **Dictionary** — «ኢንጄራ» ምን ማለት ነው? → 46 Amharic definitions.
- **Side-by-side EN translator** — flip the *EN ⇄ አማ* toggle and every
  message (yours and ሕሳር's) is translated to English using a free, keyless
  translation API (**MyMemory**, with Google Translate as fallback).
- **Google-keyboard-style screen keyboard** — light Google-like keys; tap a
  letter to reveal *all 7 of its vowel children* (ሀ ሁ ሂ ሃ ሄ ህ ሆ …) as on-screen
  options, predictive word strip, backspace (long-press to clear), symbols &
  Amharic-numerals page, and an Enter key. With the *EN ⇄ አማ* toggle on, a live
  translation bar above the keyboard shows your typing in English as you type.
- **Spelling dictionary** — a 20,000-word correctly-spelled Amharic dictionary
  (`data/amharic_words.json`, served via `GET /api/words`) searched as you
  type: pick any seed word's child-letter order, the assistant's `fold()`
  matcher (vowel-order + homophone-insensitive, mirroring `AmharicNormalizer`)
  still finds the right word and offers up to 3 correctly-spelled options in
  the suggestion strip; tap to insert. Built from the multi-domain corpus
  vocabulary (books, articles, web), so the suggestions match modern and
  classical Amharic. Falls back to an embedded mini-list when offline.
- **Reusable Amharic keyboard component** — the screen keyboard + word search is
  a *stand-alone, plug-in web component* (`static/amharic-keyboard.js` +
  `static/amharic-keyboard.css`). Any app can use it: give it an `<input>`, a
  dictionary endpoint and it provides Gboard-style typing, the spelling
  dictionary search, n-gram next-word hints, optional **server type-ahead**
  (`suggestUrl`) with full sentence completions, and an optional live
  translation bar. The AI chat consumes it like any other app — see the
  standalone demo at `/keyboard`.
- **Werket-style phonetic typing** — the Fidel engine from the
  [Werket](https://github.com/ZebraCodeX/Werket) editor is ported in. The
  on-screen keyboard is the **Amharic Fidel layout by default** (tap a family
  key for its 7 vowel orders); flip the *ላቲን → ግዕዝ · Phonetic* switch only if
  you want to type Latin (`selam`, `buna`) and have it compose Ge'ez (`ሰላም`,
  `ቡና`) on a QWERTY page, with the GFF/Keyman uppercase-emphatic convention.
  `compose()`, `charFor()` and `ordersFor()` are exported on `AmharicKeyboard`
  for reuse, and the choice is remembered in `localStorage`.
- **Translation review UI** — open `/review` to see Amharic words beside their
  English translations and approve (✓) or correct (✎) them. Every word shows an
  **English translation to judge** (fetched with 🌐 when none is stored yet, at
  most 3 at a time and cached server-side), filterable by **letter** (ሀ ለ መ …)
  and by *ማረጋገጫ / ያልተተረጎሙ / የተረጋገጡ*. Every correction is stored server-side and
  *immediately wins* in the translator, so the crowd keeps improving the app.
- **Remembers your name** — «ስሜ አበበ ነው» makes greetings personal.
- **Amharic only** — English input gets a polite Amharic-only reminder
  (except programming-language code requests).

No numpy. No sklearn. No flask. No network model. Just Python 3.8+ stdlib +
one free HTTP translate call when the translator is switched on. The language
model is a small JSON file learned offline from free Amharic corpora — no
Python ML dependencies, and you can rebuild it yourself with
`python3 -m amharic_nlp.training`.

## Features

### NLP app (`amharic_nlp/` — a standalone package)
The NLP is *separated from the chatbot* into its own application. It owns the
raw corpora (`amharic_nlp/corpora/{books,movies,articles,other}/`), the
training pipeline and the production learner artifacts in `data/`; the chat
server only talks to its public API (`amharic_nlp/__init__.py`).

- `AmharicNormalizer` — collapses homophones (ሀ/ሐ/ኀ→ሀ, ሠ→ሰ, ኣ→አ, ፀ→ጸ).
- `AmharicTokenizer` — Ge'ez word segmentation (letters only, punctuation-safe).
- `AmharicStemmer` — prefixes/suffixes stripping (እንደ/ወደ/ስለ…, ዎች/ሮች/ኣት/ኣን…).
- `StopWordFilter` — Amharic function words (`data/stopwords.txt`).
- `SentenceSplitter` — splits on Amharic punctuation ። ፡ ፧ ፨.
- `TfidfVectorizer` + `DocumentIndex` — TF-IDF, cosine similarity (pure stdlib).
- `BibleCorpus` — Amharic Bible verse retrieval tool for researchers (the
  `amharic_bible.json` used by training also lives in `corpora/books/`).
- `corpus.py` — streaming readers for many free-text formats: plain text,
  Leipzig Corpora sentences, Amharic Wikipedia dump XML, CC-100 web crawl and
  the amharic-bible-json format.
- `NLModel` (`model.py`) — the trained 2/3-gram reader/predictor.
- `Suggester` (`suggester.py`) — type-ahead: closest words + next-word hints +
  sentence completion, homophone-folded.
- `training.py` — end-to-end trainer producing all artifacts below.
- `tools/download_corpora.py` — fetch the free sources and drop them in
  `corpora/` (books, movies, articles, web). Browser-download Leipzig bundles
  if their CDN blocks scripts — just unpack the `*_sentences.txt` into
  `corpora/articles/`; the trainer picks them up.

### Conversation engine (`chatbot.py`)
- `AmharicAssistant` — vector-based intent matching over `data/knowledge_base.json`
  (54 intents, ~120 Amharic patterns & responses).
- **Hybrid routing** — deterministic rules win for math, memory, definitions,
  names, greetings and Amharic-only enforcement; creative and open-ended
  requests (`ግጥም ጻፍልኝ`, «ስለ ኮስሞስ ንገረኝ») go to the LLM when reachable.
- **Offline generative skills** (`creative.py`) — when no LLM is running, the
  verbs *write / create / develop / plan* still produce **real artifacts** in
  Amharic: poems, song lyrics, story openings, full HTML websites, essays and
  6-step action plans — never canned "I can't" lines.
- Teachable long-term memory persisted to `data/user_memory.json`.
- Multi-turn follow-ups and conversational context.
- Mini code-snippet generator (Python / JavaScript / HTML / CSS / JSON / Bash).
- Arithmetic in Arabic digits or Amharic number words.
- **Real clock & Amharic date** — «ስንት ሰዓት ነው?», «ዛሬ ምን ቀን ነው?» and «ሳምንቱ
  ስንት ነው?» answer with the live Ethiopic calendar date (`et_calendar.py`):
  Ge'ez month names (መስከረም … ጳጉሜ), Amharic week-day and the ዓ.ም era — plus
  the first 12-hour Amharic clock answer (ስምንት ሰዓት ተኩል, ከሰዓት).
- **Fun randomness** — «ሳንቲም ጣልልኝ» (ጭንቅላት/ጅራት), «ዳይስ ጣል» (1–6), «ዕጣ ቅዳልኝ»
  and «የዘፈቀደ ቁጥር ምረጥ» (1–100).
- Time-of-day-aware greetings: መልካም ጥዋት / እንደቀኑ ውብ ቀን / መልካም ምሽት / መልካም ሌሊት.
- Word definitions via the built-in dictionary.

### Language model (`data/nl_model.json`)
- Trained by `python3 -m amharic_nlp.training` over a *balanced multi-domain
  corpus*: **books** (Amharic Wikipedia dump + the full Amharic Bible),
  **articles** (BBC Amharic + Leipzig news), **movies** (drop subtitles/scripts
  into `corpora/movies/`) and **other** web text (CC-100 Amharic). The bundled
  trained model: ~337,000 sentences, ~323,000 unique words, 30,000-word
  unigram, bigram + trigram continuations, and a 15,000-sentence bank.
- `NLModel.next_words((ቃል1, ቃል2))` → top continuation words (trigram
  preferred, bigram backup). Powers the keyboard's *next-word hints*.
- `Suggester.suggest(partial)` → `{words, next, sentences}` for the training
  UI's smart type-ahead (served at `GET /api/suggest`).

### Retrieving & retraining on more Amharic text
```bash
# 1) fetch the free sources (Wikipedia, Bible, BBC articles, CC-100 web)
python3 -m amharic_nlp.tools.download_corpora

# 2) drop your own corpus text files into the matching folders:
#      amharic_nlp/corpora/books/     (books, encyclopedias, መጻሕፍት)
#      amharic_nlp/corpora/movies/    (movie/series subtitles, scripts)
#      amharic_nlp/corpora/articles/  (news, magazines, blog posts)
#      amharic_nlp/corpora/other/     (anything else)
#    — plain UTF-8 .txt works; Leipzig *_sentences.txt and Wikipedia dumps too.

# 3) retrain (flags keep one giant dump from crowding out the others)
python3 -m amharic_nlp.training --per-domain 150000 --bible amharic_nlp/corpora/books/amharic_bible.json
```
The trainer writes `nl_model.json`, `amharic_words.json` (20,000-word spelling
dictionary), `vocabulary.txt` (every word + frequency), `sentences.json`
(frequent-sentence completion bank) and `corpus_stats.json` into `data/`.

### LLM client (`llm.py`)
- Zero-config auto-detection: local **Ollama** at `localhost:11434`, or any
  OpenAI-compatible endpoint via `$LLM_BASE_URL`, `$LLM_API_KEY`, `$LLM_MODEL`
  (works with OpenAI, Groq, Together, OpenRouter, vLLM…).
- Small built-in reply cache; thread-safe; falls back to `None` (→ rule brain)
  when no backend responds.

### Translation (`translator.py`)
- `translate(text, src, dst)` — free, keyless Amharic ⇄ English.
- MyMemory primary engine, Google Translate (gtx) fallback, in-memory cache.
- Works offline (`online=False`) when the network is unavailable.
- `list_translations(query, status, limit, offset)` — the review catalogue
  (glossary + user corrections + frequent words awaiting translation).
- `translation_stats()` — counts by status (`suggested`, `verified`,
  `corrected`, `untranslated`, `glossary`).

### Web chat (`chat_app.py` + `templates/chat.html`)
- `GET /` — chat UI with the reusable Gboard-style + phonetic keyboard.
- `GET /keyboard` — **standalone keyboard demo** (a plain form using the same
  reusable component, no AI involved).
- `GET /review` — **translation review UI** (`templates/translations.html`):
  approve or correct Amharic ⇄ English pairs; each saved correction immediately
  improves the translator.
- `GET /static/*` — the reusable keyboard assets (`amharic-keyboard.js/css`),
  the review assets, and any other static files.
- `POST /api/chat` — JSON body `{text, history?}` → `{reply, source, confidence,
  followups?, elapsed_ms}` (GET `?text=` also works). `history` carries recent
  turns so the LLM keeps the conversation context after a page reload.
- `GET /api/translate?text=…&to=en|am` — JSON `{translated, score, reasons,
  word_evidence}`; candidates are scored for glossary fidelity, length sanity,
  and back-translation agreement when online engines are available.
- `GET /api/translations?status=&q=&limit=&offset=` — paginated review
  catalogue; `status ∈ {all, review, verified, corrected, untranslated}`.
- `GET /api/translations/stats` — live counts for the review dashboard.
- `POST /api/translations/verify` (alias `/api/translate/verify`) — body
  `{text, src, dst, translation, correct?}`; saves an approval or correction.
- `GET /api/words` — the 20,000-word spelling dictionary.
- `GET /api/ngram` — the multi-domain n-gram model (next-word hints in UI).
- `GET /api/suggest?text=…` — **smart type-ahead**: `{words, next, sentences}`
  — closest dictionary words to the typed prefix, n-gram next-word hints, and
  full sentence completions from the trained sentence bank (homophone-folded).
- `GET /api/llm-status` — `{available, model, backend}` (shown as a badge in
  the header: ✦ real Ai አእምሮ vs. offline AI).
- `GET /api/health` — health check.

## Run it

```bash
python3 chat_app.py            # http://localhost:8080
# or
PORT=9000 python3 chat_app.py
```

The server binds dual-stack (IPv6 + IPv4), so `http://localhost:8080` works on
any machine. Standalone keyboard demo (no AI): `http://localhost:8080/keyboard`.

On Android or iPhone, open the site in a modern browser and choose **Add to
Home screen** or **Install app**. The PWA caches the keyboard, dictionary, and
n-gram assets for fast startup; chat and online translation use the server when
it is reachable.

Command-line demo:

```bash
python3 chatbot.py
```

### Deploy to Fly.io

The live app runs on [Fly.io](https://fly.io): <https://hisar-amharic-ai.fly.dev>.
The repo ships a `Dockerfile`, `.dockerignore` and `fly.toml`, so redeploying is:

```bash
flyctl apps create hisar-amharic-ai          # once
flyctl volumes create hisar_data --region sjc --size 1   # once
flyctl deploy --remote-only --ha=false       # build + release
```

The multi-stage `Dockerfile` builds the React SPA with Node, then runs
**gunicorn** on port `8000` with Django serving both the API and the SPA (and
WhiteNoise serving hashed assets). The `hisar_data` volume is mounted at
`/app/userdata` and persists crowd corrections (`user_translations.json`) and
taught facts (`user_memory.json`) across restarts (see `HISAR_USERDATA_DIR`).

```bash
flyctl secrets set DJANGO_SECRET_KEY="$(openssl rand -hex 32)"
flyctl secrets set LLM_BASE_URL=… LLM_API_KEY=… LLM_MODEL=…   # optional: real LLM
```

### Turn ሕሳር into a full LLM (optional)

Zero setup for the offline rule brain — but to unlock real generative AI, just
make any OpenAI-compatible endpoint reachable:

```bash
# Option A — local Ollama (free, offline, no API key)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:1.7b        # small; gemma2:2b / llama3.2:1b also fine
# restart the server — it auto-detects Ollama and shows “✦ real Ai አእምሮ”

# Option B — any OpenAI-compatible API
LLM_BASE_URL=https://api.groq.com/openai/v1 \
LLM_API_KEY=your-key LLM_MODEL=llama-3.3-70b-versatile python3 chat_app.py
```

While it is running, creative & open-ended requests (poems, stories, websites,
essays, “ስለ X ንገረኝ”) are answered by the LLM in Amharic; math, memory,
dictionary and greetings stay on the instant deterministic rules.

## Tests

```bash
cd backend && ../.venv/bin/python manage.py test api   # Django/DRF API tests
python3 -m unittest discover -s tests -v               # NLP brain unit + integration tests
node tools/smoke_test.js                               # headless keyboard (type-ahead + phonetic)
cd frontend && npm run typecheck                       # TypeScript
```

`backend/api/tests.py` covers the REST end points; `tests/` covers the pure
NLP brain (assistant, translator scoring, keyboard component wiring).

## Try these

| You type | What happens |
|---|---|
| ሰላም | Amharic greeting (time-of-day aware) |
| ስሜ አበበ ነው | remembers your name |
| ስንት ሰዓት ነው? | real 12-hour Amharic clock time |
| ዛሬ ምን ቀን ነው? | Ethiopic calendar date + ዓ.ም era + Amharic week-day |
| ሳንቲም ጣልልኝ | coin flip (ጭንቅላት / ጅራት) |
| ዳይስ ጣል | dice roll (1–6) |
| ዕጣ ቅዳልኝ | random lot (1–100) |
| AI ምንድን ነው? | plain-language definition |
| ፕሮግራም ምንድን ነው? | programming intro |
| ፓይቶን ኮድ ጻፍልኝ | Python code sample |
| ስለ ፍቅር ግጥም ጻፍልኝ | original poem (offline template or LLM) |
| ለትምህርቴ እቅድ አዘጋጅልኝ | 6-step action plan (offline) |
| ስለ ቡና የድረገጽ ኮድ ጻፍልኝ | full HTML website (offline or LLM) |
| ስለ ኮስሞስ ንገረኝ | open answer (LLM) |
| መጽሐፍ መጻፍ እንዴት | book-writing structure |
| 5 ጠቅላላ 7 | math → መልሱ፡ 12 — አስራ ሁለት |
| «ኢንጄራ» ምን ማለት ነው? | Amharic definition |
| አስታውስ የማርያም ቡና ጥቁር ነው | saves a fact; later «ማርያም» recalls it |
| ስለ ኢትዮጵያ ንገረኝ · እና ታዲያ? | answer + follow-up |
| Hello! | polite Amharic-only reminder |
| *EN ⇄ አማ toggle ON* | every message also in English |

## Data

- `data/knowledge_base.json` — conversational intents, responses, dictionary.
- `data/rich_answers.json` — curated in-depth detail (summary / points / example
  / follow-ups) for every substantive intent; powers the detailed replies.
- `data/stopwords.txt` — Amharic stop words.
- `data/user_memory.json` — facts taught to the assistant (created at runtime).
- `data/user_translations.json` — user-approved/corrected Amharic ⇄ English pairs
  from `/review` (created at runtime; corrected pairs always win in translation).
- `data/nl_model.json` — 2/3-gram model across books + articles + movies + web
  (from `amharic_nlp/corpora/`; rebuild with `python3 -m amharic_nlp.training`).
- `data/amharic_words.json` — 20,000-word Amharic dictionary, **indexed by
  letter** (the first fidel family: ሀ ለ ሐ መ ሠ … ፀ ፈ ፐ, 39 groups). Shape:
  `{count, letters:[{letter,count}], by_letter:{ሀ:[{w,f},…],…}, words:[…]}`.
  Rebuild with `python3 -m amharic_nlp.tools.build_dictionary`.
  `GET /api/words` returns the flat list (keyboard/`/api/suggest`);
  `GET /api/dictionary/letters/` and `GET /api/dictionary/?letter=ሀ` expose the
  per-letter index.
- `data/vocabulary.txt` — every observed word + frequency (323k+ words).
- `data/sentences.json` — frequent sentence bank for type-ahead completion.
- `data/corpus_stats.json` — per-domain training report.

## Ethiopic calendar (`et_calendar.py`)

Pure-stdlib Gregorian ⇄ Ethiopic conversion so «ዛሬ ምን ቀን ነው?» works offline:
the Ethiopic year (ዓ.ም) starts on Gregorian 11 September, has 12 × 30-day months
plus ጳጉሜ (5 days, 6 in a leap year). Verified against known boundaries
(NY 2000 ዓ.ም = 2007-09-11, ጳጉሜ 5 = 2026-09-10) and full round-trips in
`tests/test_features.py`.

## License

Unlicense — public domain.

## Author

ZebraCodeX
