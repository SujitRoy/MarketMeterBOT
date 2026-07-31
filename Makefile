# MarketMeter Makefile
# Common development tasks

.PHONY: help install test lint format type-check clean run sync backfill analyze report status

# Default target
help:
	@echo "MarketMeter - Available commands:"
	@echo "  make install       - Install dependencies"
	@echo "  make test          - Run test suite"
	@echo "  make lint          - Run linter (ruff)"
	@echo "  make format        - Format code (black)"
	@echo "  make type-check    - Type check (mypy)"
	@echo "  make clean         - Clean cache files"
	@echo "  make run           - Run bot"
	@echo "  make sync          - Run incremental sync"
	@echo "  make backfill      - Run historical backfill"
	@echo "  make analyze       - Run technical analysis"
	@echo "  make report        - Generate report"
	@echo "  make status        - Show database status"

# Installation
install:
	pip install -e ".[dev]"

install-prod:
	pip install -e .

# Testing
test:
	python -m pytest tests/ -v

test-cov:
	python -m pytest tests/ --cov=src --cov-report=html

test-unit:
	python -m pytest tests/unit/ -v

test-integration:
	python -m pytest tests/integration/ -v

# Code Quality
lint:
	ruff check src/ tests/

format:
	black src/ tests/

type-check:
	mypy src/

check: lint type-check test

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

# Application Commands
run:
	python -m src.main

sync:
	python -m src.main --sync

backfill:
	python -m src.main --backfill

analyze:
	python -m src.main --analyze

report:
	python -m src.main --report

status:
	python -m src.main --status

# CLI Commands
cli:
	python -m src.cli.main

cli-help:
	python -m src.cli.main --help

# Database
db-init:
	python -c "from src.database.connection import init_database; init_database()"

db-vacuum:
	python -c "from src.database.connection import vacuum_database; vacuum_database()"

db-health:
	python -c "from src.database.connection import check_database_health; import json; print(json.dumps(check_database_health(), indent=2))"

# Docker
docker-build:
	docker build -t marketmeter-bot .

docker-run:
	docker run --rm -v $(PWD)/data:/app/data -v $(PWD)/logs:/app/logs --env-file .env marketmeter-bot

# Deploy
deploy:
	./scripts/deploy.sh

# Development
dev-setup: install
	cp .env.example .env
	@echo "Edit .env with your credentials"

dev-run: run

# All checks
ci: clean install check