.PHONY: install dev test lint fmt type check migrate seed openapi smoke

install:
	pip install -r requirements.txt

dev:
	uvicorn app.main:app --reload --port 8000

test:
	pytest -q

cov:
	pytest --cov=app --cov-report=term-missing --cov-report=html -q

lint:
	ruff check app tests alembic
	ruff format --check app tests alembic

fmt:
	ruff check --fix app tests alembic
	ruff format app tests alembic

type:
	mypy app

check: lint type test

migrate:
	alembic upgrade head

seed:
	python -m scripts.seed

openapi:
	python scripts/export_openapi.py ../../packages/api-client/openapi.json

# Smoke test end-to-end trên server đang chạy. QA chạy trước mỗi release.
smoke:
	python scripts/smoke_e2e.py
