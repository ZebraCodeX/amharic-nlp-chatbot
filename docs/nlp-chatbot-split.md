# Splitting the NLP layer from the chatbot

Design notes for deciding whether separating the Amharic NLP from Zer's
conversation engine makes the system **faster** or **better**, and if so, where
to cut. This is an analysis + options document; no behaviour changes are made by
it.

## 1. What exists today

The code is already layered; the only place it is *physically* one thing is a
single Python process (Django/gunicorn, or `chat_app.py`).

```
amharic_nlp/            pure-stdlib NLP package (already separated)
  toolkit.py              normalizer, tokenizer, stemmer, stop-words,
                          sentence splitter, TF-IDF, DocumentIndex, BibleCorpus
  model.py                NLModel — trained 2/3-gram reader/predictor
  suggester.py            Suggester — type-ahead (words / next / sentences)
  corpus.py, training.py  corpus readers + the offline trainer
  corpora/                raw inbound corpora (gitignored)
  -> writes data/nl_model.json, data/amharic_words.json,
            data/vocabulary.txt, data/sentences.json, data/corpus_stats.json

chatbot.py              AmharicAssistant — the conversation engine
                          intent match (TF-IDF via amharic_nlp) + rules
                          (math, memory, dict, clock/date, random, code)
english_brain.py        English answers from data/knowledge_base_en.json
zer.py                  bilingual facade: language detect + routing
llm.py                  backend selection: configured > embedded > ollama
zer_model.py            embedded Qwen GGUF via llama.cpp (global gen lock)
translator.py, learning.py, creative.py, codegen.py, reasoning.py, et_calendar.py
backend/api/services.py thread-safe singletons + a global `_lock` per chat turn
```

So the NLP is **already a module boundary** with a public API
(`amharic_nlp/__init__.py`). The live question is not "module or not" but
**process boundary and request-path shape**.

## 2. What is actually coupled (and why it costs)

| Coupling | Cost today |
| --- | --- |
| `chatbot.py` imports `amharic_nlp` in-process | sub-ms stdlib calls; no network. Good. |
| `backend/api/services.py` holds one `_lock` around a whole chat turn | serializes *all* turns, including pure retrieval and LLM generation |
| `zer_model.py` holds one `_gen_lock` | all embedded generations queue; no batching |
| 4 large JSON artifacts (~26 MB: `nl_model`, `sentences`, `vocabulary`, `amharic_words`) loaded once per worker | multiplied by gunicorn worker count; slow cold start |
| Suggester + assistant singletons per process | fine for CPU, duplicated across workers |

The dominant latency term for a *hard* question is LLM generation (hundreds of ms
to seconds). Everything in `amharic_nlp` is microseconds. Splitting the fast part
away from the slow part over a network would normally make things **slower**, not
faster — unless it buys concurrency or removes a shared lock.

## 3. Split options

### A. In-process interface boundary (formalize what exists)

Introduce a `NLPBackend` protocol so the chat engine depends on an interface, not
on `amharic_nlp` directly. Ship `LocalNLP` (current behaviour) and an optional
`RemoteNLP` (HTTP) with the same shape.

```python
# nlp_backend.py  (sketch)
from typing import Protocol

class NLPBackend(Protocol):
    def normalize(self, text: str) -> str: ...
    def tokens(self, text: str) -> list[str]: ...
    def analyze(self, text: str) -> dict: ...      # intent features, language
    def suggest(self, partial: str) -> dict: ...   # words / next / sentences
```

- **Pros:** zero latency change; testable; lets you swap the tokenizer/normalizer
  or retrain the n-gram model without touching the chat engine; one place to add
  caching/metrics.
- **Cons:** another indirection; must keep the interface small to stay useful.
- **Verdict:** do this first. It is low-risk and makes options B/C/D cheap.

### B. NLP as a network microservice

Run the toolkit + artifacts as their own service (e.g. FastAPI on one CPU box),
consumed by the chat API and the keyboard/review UIs.

- **Pros:** one warm copy of the 26 MB artifacts shared by every consumer; scale
  the retrieval tier independently of generation; reuse from the standalone
  keyboard component and `/review`; survive chat deploys without reloading.
- **Cons:** adds a network hop to work that is currently microseconds; new
  operational surface (health, versioning, auth); serialization overhead.
- **Verdict:** only worth it when you have **multiple consumers** (keyboard app,
  review, mobile) or want to scale retrieval separately. For a single chat
  process it will likely *increase* p50 latency.

### C. Stage split *within* a request (understand vs generate)

Make the existing hybrid routing explicit and measurable: compute an intent
confidence from the NLP stage, and only call the LLM when it is low (or when the
request is creative/open-ended). High-confidence retrieval answers never touch
the model.

- **Pros:** the biggest **latency and cost** win, and it is free: many turns are
  greetings, math, definitions, memory, date/time — all deterministic. Also
  improves consistency (no model drift on canned answers).
- **Cons:** routing mistakes are user-visible; needs an eval to tune the
  threshold and to prove quality does not regress.
- **Verdict:** highest-value change for "faster", independent of any process
  split. Pairs naturally with A.

### D. LLM inference split (most impactful for throughput)

Move generation out of the web process into a dedicated server: either the
embedded GGUF in its own process, or a real GPU server (vLLM) behind
`LLM_BASE_URL` — which `llm.py` already prefers when configured.

- **Pros:** continuous batching and real concurrency; removes `zer_model`'s
  global `_gen_lock` and the `services._lock` from the generation path; the web
  workers stay small and fast to boot; the app can scale horizontally while one
  GPU box serves all workers.
- **Cons:** a network hop and an extra deploy; embedded/self-contained mode is
  lost for that deployment (the offline rule brain remains fallback).
- **Verdict:** this is what makes Zer **faster under load**, not per single
  request. For one user, embedded is fine and simpler.

### E. Artifact / lifecycle split

Load the trained artifacts once in a warm process and keep them mapped, instead
of per gunicorn worker. Use `mmap`/`orjson` for the big JSON files, or ship a
single packed binary (e.g. memory-mapped arrays for the n-gram tables).

- **Pros:** faster cold start, lower RSS per worker, less duplicated memory.
- **Cons:** packaging work; keep the on-disk format stable.
- **Verdict:** do it if cold start or memory is the bottleneck.

## 4. Recommendation

1. **Do C + A now** (routing confidence + interface): guaranteed latency win,
   no infra, keeps embedded mode. Everything else becomes a config choice.
2. **Keep serving embedded for single-user / self-hosted.**
3. **Adopt D when concurrency matters** (many users or slow CPU): point
   `LLM_BASE_URL` at a GPU vLLM server. No app code change — it is already the
   preferred backend.
4. **Adopt B only if a second consumer appears** (standalone keyboard, mobile,
   review service) or you need to scale retrieval independently of generation.
5. **Do E opportunistically** if cold start or memory shows up in profiling.

Net answer to "is it faster or better?": splitting the **LLM** out of the web
process is faster at scale; splitting the **NLP** out over the network is usually
slower per request and is a **better** (reuse/scaling) decision, not a speed one.
The cheap speed win is an explicit fast-path/LLM split inside the request.

## 5. Benchmark protocol (decide with numbers)

Measure before/after each option on the same hardware:

- **Latency:** p50/p95 per turn, bucketed by source (rule/retrieval vs LLM) —
  `services.chat()` already returns `elapsed_ms` and `source`.
- **Throughput:** turns/sec at concurrency 1, 4, 16 (this is where D shows up).
- **Cold start:** time to first served request; RSS per worker.
- **Quality:** `training/eval_compare.py` language-match / ROUGE-L / chrF on the
  held-out set, plus a small routing-accuracy check (does the fast path return
  the same answer a human would accept?).
- **Cache:** suggestion/type-ahead hit rate and latency under the keyboard.

Suggested harness: a script that replays a fixed list of prompts through
`backend/api/services.chat` (in-process) and through the deployed endpoint, and
writes the four metrics above to JSON for comparison.

## 6. Migration checklist

- [ ] Add `nlp_backend.py` (`LocalNLP` wrapping `amharic_nlp`; stub `RemoteNLP`).
- [ ] Route `chatbot.AmharicAssistant` and `services.get_suggester` through it.
- [ ] Expose `confidence`/`route` on the chat result and add the fast-path gate.
- [ ] Add the benchmark harness and record a baseline.
- [ ] Only then evaluate B (service) / D (GPU server) with data.
