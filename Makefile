SHELL := /bin/bash
ENV   := set -a; [ -f .env ] && . ./.env; set +a;
PY    := .venv/bin/python
.DEFAULT_GOAL := help
.PHONY: help setup data data-long data-stress data-up check board scenarios bedrock-check explain warm extract app ui test worktrees backup scan claude

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## venv + deps + .env
	@if command -v uv >/dev/null; then uv venv -q --allow-existing .venv && uv pip install -q -p .venv -e '.[dev,agents]'; \
	 else python3 -m venv .venv && $(PY) -m pip install -q -e '.[dev,agents]'; fi
	@[ -f .env ] || { cp .env.example .env; echo "created .env, fill it in"; }
	@echo "setup done"

data: ## Starter CSVs into data/raw/ (copy, S3, or rebuild)
	@bash scripts/get-data.sh

data-long: ## Longer history into data/raw/ (official build script, from harness.toml start = 2010-01-04 unless START=; needs internet)
	@$(PY) scripts/build_long_data.py $(if $(START),--start $(START))

data-stress: ## 2020 crash history into data/raw_stress/ for the "what if March 2020 happened again?" replay (needs internet)
	@$(PY) -c "from dh import stress; raise SystemExit(stress.build())"

data-products: ## Extra products listed in Canada/U.S. into data/raw/products_cadusa/ (needs internet; then harness.toml [data] extra)
	@$(PY) scripts/build_products.py $(if $(START),--start $(START))

data-fundamentals: ## Annual statements of every stock (payout, dividend coverage) into data/raw/fundamentals/ (needs internet)
	@$(PY) scripts/build_fundamentals.py

data-up: ## Upload data/raw/*.csv to s3://$S3_BUCKET/raw/ (for the hosted app; credentials from .env)
	@$(ENV) $(PY) scripts/upload_data.py

check: ## Load the starter data, print per-asset stats
	@$(ENV) $(PY) -m dh check

board: ## Latest results per experiment/persona
	@$(PY) -m dh board

scenarios: ## Test profiles vs Profiler + Guardian (LOG=1 to log the pass rate)
	@$(PY) -m dh scenarios -v $(if $(LOG),--log)

bedrock-check: ## Smoke test of AWS: region, credentials, Bedrock text + tool use, S3 (needs .env)
	@$(ENV) $(PY) scripts/bedrock_check.py
explain: ## Pipeline + Critic + Explainer on P=amira|mateo|robert (SAVE=1 caches the Bedrock review and text for the demo)
	@$(ENV) $(PY) -m dh explain $(P) $(if $(SAVE),--save-demo)

warm: ## Fill the demo caches with Bedrock in one go: Critic, Explainer, Extractor, Analyst (DRY=1 lists the calls)
	@$(ENV) $(PY) scripts/warm.py $(if $(DRY),--dry)

log-personas: ## Log persona numbers (limits, TSLA request, strategies) to results.csv: commit code first
	@$(ENV) $(PY) -m dh log-personas

extract: ## Free text → profile: make extract T="I'm 59, ..." (SAVE=1 caches the Bedrock answer for the demo)
	@$(ENV) $(PY) -m dh extract "$(T)" $(if $(SAVE),--save-demo)

app: ## Run the demo app on :8501
	@$(ENV) $(PY) -m streamlit run app/app.py

ui: ## Run the guided interface (branch interface) on :8502
	@$(ENV) $(PY) -m streamlit run interface/app.py --server.port 8502

test: ## Run tests (offline)
	@LLM_PROVIDER=mock $(PY) -m pytest -q

worktrees: ## One worktree per lane: make worktrees [NAMES="eda models"]
	@bash scripts/worktrees.sh $(NAMES)

backup: ## Commit + push results and deliverables (before AWS teardown!)
	@bash scripts/backup.sh

scan: ## Scan git history for secrets before going public
	@bash scripts/scan-secrets.sh

claude: ## Launch Claude Code with .env loaded
	@$(ENV) claude

data-fixed-income: ## Build dated Canadian/U.S. fixed-income catalogue for raw/fixed_income/ in S3
	@$(PY) scripts/build_fixed_income.py
