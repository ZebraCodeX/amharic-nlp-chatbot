# Amharic pretraining corpus

Data layer for **continued pretraining** of an open base model (7B–14B) — the
step that actually makes a model *natively Amharic*, unlike the small QLoRA chat
adapter in `training/`.

```
python3 training/corpus/build_corpus.py \
  --out ~/amharic-corpus \
  --sources wikipedia,cc100,opus_tatoeba,bible,local \
  --max-gb-per-source 8 --tokenizer Qwen/Qwen2.5-1.5B-Instruct
```

Output is gzipped text shards (`<out>/<source>/part-*.txt.gz`, one document per
line) plus `manifest.json` recording licence, doc/token counts, size and status
for every source. Each source is capped and idempotent (re-run to resume; use
`--force` to redo one).

## Sources and licences

| Key | What | Licence |
| --- | --- | --- |
| `wikipedia` | Amharic Wikipedia dump (via `wikimedia/wikipedia`) | CC BY-SA 4.0 |
| `cc100` | CC-100 Amharic web crawl | CC-100 / Common Crawl terms |
| `fineweb2` | FineWeb-2 `amh_Ethi` (curated web) | ODC-BY 1.0 |
| `mc4` | mC4 Amharic (multilingual C4) | ODC-BY 1.0 |
| `culturax` | CulturaX Amharic (cleaned mC4 + OSCAR) | mixed (mC4 ODC-BY, OSCAR) |
| `opus_tatoeba` | Tatoeba parallel (Amharic side) | CC BY 2.0 FR |
| `opus_ted2020` | TED2020 parallel | CC BY-NC-ND 4.0 |
| `opus_gnome` / `opus_ubuntu` | Software localisation parallel | free software |
| `bible` | Wordproject Amharic Bible (in-repo) | public domain / Open Bible |
| `local` | Anything under `amharic_nlp/corpora/` (drop OCR'd text here) | user-supplied |

**Not included on purpose:** OSCAR (gated, research-only — fetch it yourself if
your use qualifies), and scraped news (BBC / VOA / DW Amharic are © the
broadcaster; use their APIs/terms or a licensed feed). **OCR'd books:** drop
`*.txt`/`*.txt.gz` into `amharic_nlp/corpora/books/` and run `--sources local`;
public-domain scans (Internet Archive, HathiTrust) are the clean source.

## Scaling to "Frontier" — what it really takes

Pretraining compute ≈ `6 × params × tokens` FLOPs. Using that:

| Goal | Data | Compute | Rough cost |
| --- | --- | --- | --- |
| This corpus pipeline (collect + clean) | ~5–15B tokens | CPU/IO only | laptop/cloud storage |
| Continued-pretrain a 7B on ~30B Amharic tokens | ~30B tokens | ~1.3×10²² FLOPs | ~$3–10k rented |
| Continued-pretrain a 14B on ~100B tokens | ~100B tokens | ~8×10²² FLOPs | ~$20–60k rented |
| Train a 0.5B from scratch on ~100B tokens | ~100B tokens | ~3×10²⁰ FLOPs | ~$300–500 (8×H100, ~2 days) |
| Frontier 70B on ~15T tokens | ~15T tokens | ~6×10²⁴ FLOPs | **$10M+ per run** |

The hard limit for Amharic is **data** — there is far less Amharic text than
English, so the realistic win is *the largest, cleanest legal Amharic corpus*
(few billion to low tens of billions of tokens), then continued-pretrain + SFT
on a strong multilingual base (Qwen2.5, Llama 3.x, Gemma, Aya). That is
competitive with giants *on Amharic* without frontier money.

## Next steps this unlocks

1. Grow the corpus (raise `--max-gb-per-source`, add FineWeb-2/CulturaX, wire in
   the `download_corpora.py` sources).
2. Near-duplicate removal (MinHash/SimHash) and quality scoring.
3. Continued pretraining with a causal-LM objective (not the chat SFT trainer),
   then instruction-tune on `training/data/amharic_sft.jsonl`.
4. Evals per stage with `training/eval_compare.py`.
