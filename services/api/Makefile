.PHONY: install dev test lint fmt type check migrate seed openapi

install:
	pip install -r requirements.txt

dev:
	uvicorn app.main:app --reload --port 8000

test:
	pytest -q

lint:
	ruff check app tests
	ruff format --check app tests

fmt:
	ruff check --fix app tests
	ruff format app tests

type:
	mypy app

check: lint type test

migrate:
	alembic upgrade head

seed:
	python -m scripts.seed

openapi:
	python scripts/export_openapi.py ../../packages/api-client/openapi.json
