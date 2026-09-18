# Zer — common tasks.  (export PATH="$HOME/.fly/bin:$PATH" for `make deploy`)
SHELL := /bin/bash
VENV ?= .venv
PY := ../$(VENV)/bin/python
FLY_APP ?= hisar-amharic-ai
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

export-data: ## export real conversations as training data
	cd backend && $(PY) manage.py export_training_data

train: ## QLoRA fine-tune + merge (run on a GPU)
	bash training/run.sh

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
	dev-backend dataset export-data train eval superuser backup migrate deploy logs release
