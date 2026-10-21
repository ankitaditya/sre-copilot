.PHONY: install ui-install build dev test lint chaos healthy sandbox-up sandbox-down

install:
	python -m pip install -e ".[dev]"
	cd ui && npm ci

ui-install:
	cd ui && npm ci

build:
	cd ui && npm run build

dev:
	uvicorn sre_copilot.app:app --reload --port 8000

test:
	pytest

lint:
	ruff check src tests sandbox
	cd ui && npm run typecheck

chaos:
	python sandbox/chaos.py db-down

healthy:
	python sandbox/chaos.py healthy

sandbox-up:
	docker compose -f sandbox/compose.yml up --build -d

sandbox-down:
	docker compose -f sandbox/compose.yml down

