.PHONY: dev dev-build dev-mobile test-backend test-frontend test-e2e eval-multilingual eval-multilingual-report eval-seed-and-lint lint format seed seed-cluster seed-entities seed-graph clean logs perf-locust perf-k6 perf-all deploy-production pre-deploy-check smoke-test create-release install-offline

# ── Local Development ─────────────────────────────────────────────────────────
dev:
	docker compose up --watch

dev-build:
	docker compose up --build --watch

dev-mobile:
	cd apps/mobile && npx expo start --web

# ── Testing ───────────────────────────────────────────────────────────────────
test-backend:
	docker compose exec backend pytest tests/ -v

test-frontend:
	cd frontend && bun run test

test-e2e:
	cd frontend && npx playwright test

# ── Lint & Format ─────────────────────────────────────────────────────────────
lint:
	cd backend && uv run ruff check app/ tests/
	cd backend && uv run ruff format --check app/ tests/
	cd frontend && bun run lint

format:
	cd backend && uv run ruff format app/ tests/
	cd frontend && bun run format

# ── Data ──────────────────────────────────────────────────────────────────────
seed:
	HINDSIGHT_API_URL=http://localhost:8600 python3 scripts/seed_documents.py

seed-multilingual:
	HINDSIGHT_API_URL=http://localhost:8600 python3 scripts/seed_documents.py --multilingual

seed-cluster:
	python3 scripts/cluster_corpus.py

seed-entities:
	python3 scripts/extract_entities.py

seed-graph:
	python3 scripts/build_graph_view.py

seed-all: seed seed-cluster seed-entities seed-graph

install-offline:
	pip install -r requirements-offline.txt

# ── Performance Tests ──────────────────────────────────────────────────────────
PERF_USERS ?= 10
PERF_DURATION ?= 60
PERF_TARGET_HOST ?= http://localhost:8000

perf-locust:
	locust -f backend/tests/benchmark/locustfile.py --headless \
		-u $(PERF_USERS) -r 5 --run-time $(PERF_DURATION)s \
		--host $(PERF_TARGET_HOST)

perf-k6:
	K6_TARGET_HOST=$(PERF_TARGET_HOST) k6 run backend/tests/benchmark/k6_search.js

perf-all: perf-locust perf-k6

# ── RAG Evaluation ──────────────────────────────────────────────────────────
EVAL_BASE_URL ?= http://localhost:8000
EVAL_TIMEOUT ?= 15
EVAL_TOP_K ?= 10

eval-multilingual:
	EVAL_BASE_URL=$(EVAL_BASE_URL) EVAL_TIMEOUT=$(EVAL_TIMEOUT) EVAL_TOP_K=$(EVAL_TOP_K) \
		python3 docs/testing/eval/run_eval.py

eval-multilingual-report:
	@cat docs/testing/multilingual-eval-report.md

eval-seed-and-lint:
	EVAL_BASE_URL=$(EVAL_BASE_URL) EVAL_TIMEOUT=$(EVAL_TIMEOUT) EVAL_TOP_K=$(EVAL_TOP_K) \
		python3 docs/testing/eval/run_eval.py --seed-multilingual

# ── Deployment ───────────────────────────────────────────────────────────────
deploy-production:
	sh scripts/deploy-production.sh

pre-deploy-check:
	sh scripts/pre-deploy-check.sh

smoke-test:
	sh scripts/smoke-test.sh

create-release:
	sh scripts/create-release.sh

# ── Utilities ─────────────────────────────────────────────────────────────────
logs:
	docker compose logs -f

clean:
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -name "*.pyc" -delete
