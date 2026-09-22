# Zer — common tasks.  (export PATH="$HOME/.fly/bin:$PATH" for `make deploy`)
SHELL := /bin/bash
VENV ?= .venv
PY := ../$(VENV)/bin/python
FLY_APP ?= am-ai
NPM := npm

help: ## list targets
	@grep -E '^[a-zA-Z_.-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n",$$1,$$2}'

# ---- tests ----
test: backend-test brain-test smoke ## all tests

backend-test: ## Django/DRF API tests
	cd backend && $(PY) manage.py test api

brain-test: ## pure NLP brain tests
	python3 -m unittest discover -s tests

smoke: ## keyboard component smoke test
	node tools/smoke_test.js

# ---- build / run ----
frontend-build: ## build React → backend/static/spa
	cd frontend && $(NPM) run build

frontend-app-build: ## build React → frontend/dist (native/desktop shells)
	cd frontend && $(NPM) run build:app

dev-backend: ## run Django dev server
	cd backend && $(PY) manage.py runserver

# ---- data ----
dataset: ## build the Amharic SFT seed dataset
	python3 training/build_dataset.py

conversation: ## fetch free Amharic conversational corpora (needs .venv-train)
	.venv-train/bin/python tools/fetch_conversation_corpus.py

english-kb: ## compile the English knowledge base (no model at runtime)
	python3 tools/build_english_kb.py

retrain: ## retrain the n-gram/dictionary model from all corpora
	python3 -m amharic_nlp.training --per-domain 150000 --max-trigram 60000 --max-next 10 --bible amharic_nlp/corpora/books/amharic_bible.json
	python3 -m amharic_nlp.tools.build_dictionary

export-data: ## export real conversations as training data
	cd backend && $(PY) manage.py export_training_data

train: ## QLoRA fine-tune + merge (run on a GPU)
	bash training/run.sh

train-7b: ## 7B QLoRA fine-tune + merge (24 GB GPU or Kaggle; resumable)
	bash training/run-7b.sh

train-3b: ## 3B QLoRA fine-tune + merge (T4-friendly stepping stone)
	MODEL=Qwen/Qwen2.5-3B-Instruct BATCH=2 GA=8 MAXLEN=2048 bash training/run.sh

model: ## place the embedded Zer GGUF at models/zer-qwen-q4_k_m.gguf
	@test -f models/zer-qwen-q4_k_m.gguf && echo "embedded model present ✓" || \
	  { echo "embedded model missing — fetch it, e.g.:"; \
	    echo "  scp me@192.168.1.160:/home/me/zer-qwen-q4_k_m.gguf models/"; \
	    exit 2; }

run-zer: ## run ሕሳር with the embedded Zer model (self-contained)
	bash run-with-zer.sh

serve: ## serve the merged model with vLLM + a public tunnel (GPU box)
	bash training/serve.sh $(MODEL)

connect-llm: ## point the Fly app at your GPU host (LLM_BASE_URL/LLM_API_KEY)
	bash training/connect-fly.sh

eval: ## sanity-check a model (MODEL=…)
	python3 training/eval.py --model $(MODEL)

# ---- ops ----
superuser: ## create a Django admin user
	cd backend && $(PY) manage.py createsuperuser

backup: ## back up the SQLite DB on the persistent volume
	cd backend && $(PY) manage.py backup_db

migrate: ## apply migrations
	cd backend && $(PY) manage.py migrate

deploy: frontend-build ## build + deploy the web app to Fly.io
	flyctl deploy --remote-only --ha=false --app $(FLY_APP)

logs: ## tail the live app logs
	flyctl logs --app $(FLY_APP)

release: ## tag a release:  make release V=1.7.0
	test -n "$(V)"
	git tag v$(V) && git push origin v$(V)

.PHONY: help test backend-test brain-test smoke frontend-build frontend-app-build \
	dev-backend dataset conversation english-kb retrain export-data train train-7b \
	train-3b model \
	run-zer eval serve connect-llm superuser backup migrate deploy logs release
