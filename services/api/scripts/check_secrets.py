"""Chặn secret lọt vào repo (P0-11).

Chạy trong CI và trong `make check`. Ba thứ bị chặn:

  1. File .env dạng chữ thường được git theo dõi. `.env.example` là ngoại lệ có chủ đích —
     nó chứa giá trị mẫu, và giá trị mẫu phải nhìn ra ngay là mẫu.
  2. File khoá riêng (age, ssh, pem) bị commit nhầm.
  3. Giá trị trông như secret thật nằm trong file được theo dõi.

Nguyên tắc: thà báo nhầm và bắt người ta giải thích, còn hơn để một khoá thật trôi vào lịch sử
git — đã vào lịch sử thì xoá file không đủ, phải đổi khoá và viết lại lịch sử.

    python scripts/check_secrets.py            # quét file git đang theo dõi
    python scripts/check_secrets.py --staged   # chỉ quét file đang staged (dùng cho pre-commit)
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# File .env được phép có mặt trong repo.
ALLOWED_ENV = {".env.example"}

FORBIDDEN_NAMES = re.compile(
    r"(^|/)(\.env(\.[a-z]+)?|.*\.age|.*\.pem|id_rsa|id_ed25519|.*key\.txt)$"
)

# Giá trị trông như secret thật. Cố tình rộng: báo nhầm thì giải thích một câu, bỏ sót thì
# phải đổi khoá và viết lại lịch sử git.
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "Khoá riêng age/PGP/SSH",
        re.compile(r"AGE-SECRET-KEY-1|BEGIN (RSA |OPENSSH |PGP )?PRIVATE KEY"),
    ),
    ("Token AWS", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "Chuỗi kết nối có mật khẩu",
        re.compile(r"(postgres|postgresql|redis|amqp)://[^\s:@/]+:[^\s:@/]{6,}@"),
    ),
    ("Khoá riêng dịch vụ Google", re.compile(r'"type"\s*:\s*"service_account"')),
    ("Token Slack", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
]

# Giá trị mẫu được phép: phải nhìn ra ngay là mẫu.
PLACEHOLDERS = re.compile(
    r"(change-me|dev-only|example|localhost|127\.0\.0\.1|goan:goan|user:pass|<[^>]+>|xxx+)",
    re.IGNORECASE,
)

SKIP_SUFFIXES = (".enc", ".lock", ".png", ".jpg", ".pdf", ".xlsx", ".ico", ".woff", ".woff2")
SKIP_DIRS = ("node_modules/", "dist/", ".venv/", "htmlcov/")


def tracked_files(staged: bool) -> list[str]:
    cmd = (
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
        if staged
        else [
            "git",
            "ls-files",
        ]
    )
    out = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line.strip()]


def scan(paths: list[str]) -> list[str]:
    problems: list[str] = []
    for rel in paths:
        if any(rel.startswith(d) or f"/{d}" in rel for d in SKIP_DIRS):
            continue
        name = Path(rel).name
        if FORBIDDEN_NAMES.search(rel) and name not in ALLOWED_ENV:
            problems.append(f"{rel}: file bí mật không được commit (dùng bản .enc)")
            continue
        if rel.endswith(SKIP_SUFFIXES):
            continue

        full = REPO_ROOT / rel
        if not full.is_file():
            continue
        try:
            content = full.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(content):
                line_no = content[: match.start()].count("\n") + 1
                line = content.splitlines()[line_no - 1] if line_no else ""
                if PLACEHOLDERS.search(line):
                    continue
                problems.append(f"{rel}:{line_no}: {label}")
    return problems


def main() -> int:
    staged = "--staged" in sys.argv
    problems = scan(tracked_files(staged))
    if problems:
        print("Phát hiện secret trong file được git theo dõi:\n")
        for p in problems:
            print(f"  {p}")
        print(
            "\nSửa: đưa giá trị thật vào .env (đã gitignore) hoặc file .enc mã hoá bằng SOPS.\n"
            "Nếu đây là giá trị mẫu, viết nó cho ra dáng mẫu (change-me, example, <thay-tôi>)."
        )
        return 1
    print(f"Không có secret nào trong {len(tracked_files(staged))} file được theo dõi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
