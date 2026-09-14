from __future__ import annotations

import json
import re
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .config import DATABASE_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_db() -> None:
    with _connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                oracle_version TEXT NOT NULL DEFAULT '',
                environment TEXT NOT NULL DEFAULT '',
                architecture TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL,
                profile_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_knowledge_profile
            ON knowledge_chunks(profile_id);

            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                model TEXT NOT NULL,
                question TEXT NOT NULL,
                confidence TEXT NOT NULL DEFAULT 'unknown',
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cases_created
            ON cases(created_at DESC);
            """
        )


def list_profiles() -> list[dict[str, Any]]:
    with _connect() as db:
        rows = db.execute(
            """
            SELECT p.*,
                   COUNT(DISTINCT k.document_id) AS knowledge_documents
            FROM profiles p
            LEFT JOIN knowledge_chunks k ON k.profile_id = p.id
            GROUP BY p.id
            ORDER BY p.name COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_profile(profile_id: int) -> dict[str, Any] | None:
    with _connect() as db:
        row = db.execute(
            "SELECT * FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
    return dict(row) if row else None


def create_profile(
    name: str,
    oracle_version: str,
    environment: str,
    architecture: str,
    notes: str,
) -> dict[str, Any]:
    with _connect() as db:
        cursor = db.execute(
            """
            INSERT INTO profiles
                (name, oracle_version, environment, architecture, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name.strip(),
                oracle_version.strip(),
                environment.strip(),
                architecture.strip(),
                notes.strip(),
                _now(),
            ),
        )
        profile_id = int(cursor.lastrowid)
    profile = get_profile(profile_id)
    if profile is None:
        raise RuntimeError("The profile could not be created.")
    profile["knowledge_documents"] = 0
    return profile


def _chunks(text: str, size: int = 3500, overlap: int = 350) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    result: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start, end)
            if boundary > start + size // 2:
                end = boundary
        result.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [part for part in result if part]


def add_knowledge(profile_id: int, title: str, content: str) -> dict[str, Any]:
    document_id = uuid.uuid4().hex
    pieces = _chunks(content)
    if not pieces:
        raise ValueError("Knowledge content is empty.")
    created_at = _now()
    with _connect() as db:
        db.executemany(
            """
            INSERT INTO knowledge_chunks
                (document_id, profile_id, title, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (document_id, profile_id, title.strip(), piece, created_at)
                for piece in pieces
            ],
        )
    return {
        "document_id": document_id,
        "title": title.strip(),
        "chunks": len(pieces),
        "created_at": created_at,
    }


def list_knowledge(profile_id: int) -> list[dict[str, Any]]:
    with _connect() as db:
        rows = db.execute(
            """
            SELECT document_id, title, COUNT(*) AS chunks,
                   SUM(LENGTH(content)) AS characters,
                   MIN(created_at) AS created_at
            FROM knowledge_chunks
            WHERE profile_id = ?
            GROUP BY document_id, title
            ORDER BY created_at DESC
            """,
            (profile_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_knowledge(profile_id: int, document_id: str) -> bool:
    with _connect() as db:
        cursor = db.execute(
            """
            DELETE FROM knowledge_chunks
            WHERE profile_id = ? AND document_id = ?
            """,
            (profile_id, document_id),
        )
    return cursor.rowcount > 0


_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_$#.-]{2,}|ORA-\d{5}", re.I)
_STOP = {
    "select", "from", "where", "table", "index", "oracle", "with",
    "that", "this", "have", "into", "and", "the", "for", "are",
}


def _terms(text: str) -> Counter[str]:
    tokens = [token.lower() for token in _TOKEN.findall(text)]
    return Counter(token for token in tokens if token not in _STOP)


def retrieve_knowledge(
    profile_id: int | None, query: str, limit: int = 5
) -> list[dict[str, Any]]:
    if profile_id is None:
        return []
    with _connect() as db:
        rows = db.execute(
            """
            SELECT document_id, title, content
            FROM knowledge_chunks
            WHERE profile_id = ?
            """,
            (profile_id,),
        ).fetchall()

    query_terms = _terms(query)
    if not query_terms:
        return [dict(row) for row in rows[:limit]]

    ranked: list[tuple[float, sqlite3.Row]] = []
    for row in rows:
        content_terms = _terms(f"{row['title']} {row['content']}")
        shared = set(query_terms) & set(content_terms)
        score = sum(
            min(query_terms[token], content_terms[token]) * (1.0 + len(token) / 10)
            for token in shared
        )
        if score:
            ranked.append((score, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [dict(row) for _, row in ranked[:limit]]


def save_case(
    profile_id: int | None,
    title: str,
    category: str,
    model: str,
    question: str,
    result: dict[str, Any],
) -> int:
    with _connect() as db:
        cursor = db.execute(
            """
            INSERT INTO cases
                (profile_id, title, category, model, question,
                 confidence, result_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                title.strip(),
                category.strip(),
                model.strip(),
                question.strip(),
                str(result.get("confidence", "unknown")),
                json.dumps(result, ensure_ascii=False),
                _now(),
            ),
        )
    return int(cursor.lastrowid)


def list_cases(limit: int = 25) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 100))
    with _connect() as db:
        rows = db.execute(
            """
            SELECT c.id, c.title, c.category, c.model, c.confidence,
                   c.created_at, p.name AS profile_name
            FROM cases c
            LEFT JOIN profiles p ON p.id = c.profile_id
            ORDER BY c.id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_case(case_id: int) -> dict[str, Any] | None:
    with _connect() as db:
        row = db.execute(
            """
            SELECT c.*, p.name AS profile_name
            FROM cases c
            LEFT JOIN profiles p ON p.id = c.profile_id
            WHERE c.id = ?
            """,
            (case_id,),
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["result"] = json.loads(result.pop("result_json"))
    return result


def delete_case(case_id: int) -> bool:
    with _connect() as db:
        cursor = db.execute("DELETE FROM cases WHERE id = ?", (case_id,))
    return cursor.rowcount > 0
