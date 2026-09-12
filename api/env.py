""".env 로더.

파이썬은 Vite와 달리 `.env`를 자동으로 읽지 않는다. python-dotenv를 쓸 수도 있지만
필요한 건 `KEY=VALUE` 몇 줄이라 의존성 없이 직접 읽는다.

읽는 순서 (뒤쪽이 앞쪽을 덮지 않는다 — **이미 설정된 환경변수가 항상 이긴다**):
  1. 실제 환경변수  (`KAKAO_REST_API_KEY=... uvicorn ...`)
  2. api/.env
  3. 프로젝트 루트 .env

`api/__init__.py`에서 호출하므로 `api.*`를 임포트하는 순간 자동으로 적용된다.
"""
from __future__ import annotations
import os
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
CANDIDATES = (API_DIR / ".env", API_DIR.parent / ".env")


def _parse(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def load(paths=CANDIDATES) -> list[Path]:
    """.env 파일들을 읽어 os.environ에 채운다. 이미 있는 키는 건드리지 않는다."""
    loaded: list[Path] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            values = _parse(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        for key, value in values.items():
            os.environ.setdefault(key, value)     # 실제 환경변수가 우선
        loaded.append(path)
    return loaded
