# ዘር (Zer) — Amharic AI & NLP Toolkit

A pure-Python Amharic NLP toolkit plus a self-contained AI assistant. **Zer**
(ዘር, “seed”) chats in **Amharic or English**, detects the language you speak and
answers in the same language, out loud.

**Live app / PWA: <https://am-ai.fly.dev>** — chat, Amharic keyboard and
translation review UI. Open it and choose **Install app** to add it to your
device.

## Download

Native builds from [GitHub Releases](https://github.com/ZebraCodeX/amharic-nlp-chatbot/releases/latest):
Android (`Hisar.apk`), Windows (`Hisar-Setup.exe`), macOS (`Hisar.dmg`), Linux
(`Hisar.AppImage`) and iOS (signed `.ipa` needs Apple signing). One React
codebase via Capacitor (mobile) and Electron (desktop), built by GitHub Actions.

## What it does

- **Answers without any external model** — language detection, an English brain,
  Amharic code generation, dictionary lookups, math, clock and Ethiopic date.
- **Retrieval + knowledge** — 54 intents, deep `rich_answers.json` detail and a
  multi-domain corpus language model for next-word and sentence completion.
- **Live voice** — continuous, push-to-talk and “Hey Zer” wake word. Speech-to-text
  with faster-whisper; Amharic replies use Meta MMS-TTS (neural VITS) with
  sentence pacing and high-quality resampling, English prefers Piper. The
  robotic eSpeak voice is only a last-resort fallback.
- **Accounts & history** — conversations, taught facts and settings are stored
  per user (Django auth).
- **Amharic keyboard** — reusable Gboard-style Fidel keyboard with vowel-order
  keys, spelling dictionary and type-ahead.
- **Translation review** — `/review` lets you approve or correct Amharic ⇄
  English pairs, and corrections are learned immediately.
- **Bundled, hybrid brain** — Amharic answers run the fine-tuned Zer Qwen2.5-1.5B
  GGUF; English answers run a base Qwen2.5-1.5B-Instruct GGUF. Both are baked
  into the Docker image and run in-process through `llama.cpp` — self-contained,
  never an external inference endpoint.

## Stack

Django 6 + DRF backend (`backend/`), React 18 + TypeScript SPA (`frontend/`),
pure-stdlib Python NLP (`amharic_nlp/`, `chatbot.py`).

## Develop

```bash
# backend
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cd backend && ../.venv/bin/python manage.py runserver     # :8000

# frontend (separate terminal, Vite proxies /api)
cd frontend && npm install && npm run dev                 # :5173
```

## Tests

```bash
cd backend && ../.venv/bin/python manage.py test api
python3 -m unittest discover -s tests -v
cd frontend && npm run typecheck
```

## Deploy

Ships a `Dockerfile` and `fly.toml`; `make deploy` builds the SPA and runs
`flyctl deploy`. Add `FLY_API_TOKEN` for auto-deploy on every commit to `main`.

## License

Unlicense — public domain. Author: ZebraCodeX.
