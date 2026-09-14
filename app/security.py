from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from .config import ALLOWED_EXTENSIONS


class UploadValidationError(ValueError):
    pass


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if cleaned:
            self.parts.append(cleaned)

    def text(self) -> str:
        return "\n".join(self.parts)


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


async def read_upload_text(upload: UploadFile, max_bytes: int) -> tuple[str, str]:
    name = Path(upload.filename or "upload.txt").name
    extension = Path(name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise UploadValidationError(
            f"Unsupported file type for {name}. Allowed: {allowed}"
        )

    raw = await upload.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise UploadValidationError(f"{name} exceeds the configured upload limit.")
    if b"\x00" in raw[:4096]:
        raise UploadValidationError(f"{name} appears to be a binary file.")

    text = _decode(raw).replace("\x00", "")
    if extension in {".html", ".htm"}:
        parser = _HTMLTextExtractor()
        parser.feed(text)
        text = parser.text()
    return name, text.strip()


_REDACTION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "password",
        re.compile(
            r"(?i)\b(password|passwd|pwd)\s*([=:])\s*([^\s,;\)]+)"
        ),
        r"\1\2[REDACTED]",
    ),
    (
        "url_credentials",
        re.compile(r"(?i)(https?://)([^\s/:]+):([^\s/@]+)@"),
        r"\1[REDACTED]:[REDACTED]@",
    ),
    (
        "email",
        re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        "ipv4",
        re.compile(
            r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)"
            r"(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])"
        ),
        "[REDACTED_IP]",
    ),
]


def redact_sensitive(text: str) -> tuple[str, dict[str, int]]:
    output = text
    counts: dict[str, int] = {}
    for label, pattern, replacement in _REDACTION_PATTERNS:
        output, count = pattern.subn(replacement, output)
        if count:
            counts[label] = count
    return output, counts


def safe_snippet(text: str, maximum: int = 180) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= maximum else compact[: maximum - 1] + "…"


def trim_sections(sections: dict[str, str], maximum: int) -> tuple[dict[str, str], bool]:
    cleaned: dict[str, str] = {}
    remaining = maximum
    truncated = False
    for key, value in sections.items():
        value = (value or "").strip()
        if not value:
            continue
        if remaining <= 0:
            truncated = True
            break
        selected = value[:remaining]
        if len(selected) < len(value):
            truncated = True
        cleaned[key] = selected
        remaining -= len(selected)
    return cleaned, truncated


def public_error(detail: Any) -> str:
    text = str(detail).strip()
    return text if text else "Unexpected local application error."
