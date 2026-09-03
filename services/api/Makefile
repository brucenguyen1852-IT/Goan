.PHONY: install dev test lint fmt type check migrate seed openapi smoke audit \
	secrets-init secrets-new secrets-edit secrets-decrypt secrets-add-key secrets-check

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

check: lint type test secrets-check

migrate:
	alembic upgrade head

seed:
	python -m scripts.seed

openapi:
	python scripts/export_openapi.py ../../packages/api-client/openapi.json

# Smoke test end-to-end trên server đang chạy. QA chạy trước mỗi release.
smoke:
	python scripts/smoke_e2e.py

# Quét ngang toàn bộ bề mặt API: mọi endpoint, mọi vai trò, cả trường hợp phải bị từ chối.
audit:
	python scripts/api_audit.py

# --- Quản lý secret: SOPS + age (P0-11) -----------------------------------------------
# File .enc nằm trong repo và được review như mã. Khoá riêng KHÔNG bao giờ vào repo.
SOPS ?= sops
AGE_KEY_FILE ?= $(HOME)/.config/goan/age.key
ENV ?= staging

# Chặn secret lọt vào repo. Chạy trong `make check` và trong CI.
secrets-check:
	python scripts/check_secrets.py

# Lần đầu: sinh khoá cho máy này và ghi khoá công khai vào .sops.yaml.
secrets-init:
	@mkdir -p $(dir $(AGE_KEY_FILE))
	@test -f $(AGE_KEY_FILE) || age-keygen -o $(AGE_KEY_FILE)
	@chmod 600 $(AGE_KEY_FILE)
	@python scripts/sops_keys.py add "$$(age-keygen -y $(AGE_KEY_FILE))"
	@echo "Khoá riêng: $(AGE_KEY_FILE) — KHÔNG commit, KHÔNG gửi qua chat."
	@echo "Khoá công khai đã ghi vào .sops.yaml. Commit .sops.yaml rồi nhờ người trong đội mã hoá lại các file .enc."

# Thêm người vào đội: make secrets-add-key PUB=age1...
secrets-add-key:
	@test -n "$(PUB)" || (echo "Thiếu PUB=age1..." && exit 1)
	@python scripts/sops_keys.py add "$(PUB)"
	@echo "Đã thêm. Chạy lại secrets-edit cho từng môi trường để mã hoá lại bằng danh sách khoá mới."

# Tạo file secret cho một môi trường mới, bắt đầu từ .env.example.
secrets-new:
	@test ! -f .env.$(ENV).enc || (echo ".env.$(ENV).enc đã tồn tại" && exit 1)
	cp .env.example .env.$(ENV).enc
	SOPS_AGE_KEY_FILE=$(AGE_KEY_FILE) $(SOPS) --config ../../.sops.yaml \
		--input-type dotenv --output-type dotenv -e -i .env.$(ENV).enc
	@echo "Đã tạo .env.$(ENV).enc. Sửa giá trị thật bằng: make secrets-edit ENV=$(ENV)"

# Sửa secret: mở editor với nội dung đã giải mã, lưu xong tự mã hoá lại.
secrets-edit:
	SOPS_AGE_KEY_FILE=$(AGE_KEY_FILE) $(SOPS) --config ../../.sops.yaml \
		--input-type dotenv --output-type dotenv .env.$(ENV).enc

# Ghi ra .env dùng được để chạy. File này đã gitignore.
secrets-decrypt:
	SOPS_AGE_KEY_FILE=$(AGE_KEY_FILE) $(SOPS) --config ../../.sops.yaml \
		--input-type dotenv --output-type dotenv -d .env.$(ENV).enc > .env
	@echo "Đã ghi .env từ .env.$(ENV).enc"
