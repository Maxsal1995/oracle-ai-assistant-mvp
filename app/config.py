from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _as_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


_load_dotenv()

_data_value = Path(os.getenv("ORACLE_AI_DATA_DIR", "data"))
DATA_DIR = _data_value if _data_value.is_absolute() else BASE_DIR / _data_value
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATA_DIR / "oracle_ai_assistant.db"
STATIC_DIR = BASE_DIR / "app" / "static"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
PREFERRED_MODEL = os.getenv("ORACLE_AI_MODEL", "").strip()
MAX_UPLOAD_BYTES = _as_int("MAX_UPLOAD_MB", 5) * 1024 * 1024
MAX_EVIDENCE_CHARS = _as_int("MAX_EVIDENCE_CHARS", 180000)
OLLAMA_TIMEOUT_SECONDS = _as_int("OLLAMA_TIMEOUT_SECONDS", 300)

ALLOWED_EXTENSIONS = {
    ".txt", ".sql", ".log", ".trc", ".out", ".lst", ".md",
    ".json", ".xml", ".csv", ".html", ".htm",
}
