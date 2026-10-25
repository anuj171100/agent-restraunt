from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    load_dotenv(ROOT / ".env")


def _under_root(env_name: str, default: str) -> Path:
    path = Path(os.getenv(env_name, default))
    if not path.is_absolute():
        path = ROOT / path
    return path


def cache_dir() -> Path:
    return _under_root("CACHE_DIR", "cache")


def runs_dir() -> Path:
    return _under_root("RUNS_DIR", "runs")


def openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "openai/gpt-4o-mini").strip() or "openai/gpt-4o-mini"


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing {name}. Copy .env.example to .env and fill it in.")
    return value
