from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import (
    MAX_EVIDENCE_CHARS,
    MAX_UPLOAD_BYTES,
    OLLAMA_BASE_URL,
    PREFERRED_MODEL,
    STATIC_DIR,
)
from .database import (
    add_knowledge,
    create_profile,
    delete_case,
    delete_knowledge,
    get_case,
    get_profile,
    init_db,
    list_cases,
    list_knowledge,
    list_profiles,
    retrieve_knowledge,
    save_case,
)
from .ollama_client import OllamaClient, OllamaUnavailable
from .oracle_analyzer import analyse_oracle_evidence
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .security import (
    UploadValidationError,
    public_error,
    read_upload_text,
    redact_sensitive,
    trim_sections,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Oracle AI Assistant MVP",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")
ollama = OllamaClient()


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    oracle_version: str = Field(default="", max_length=50)
    environment: str = Field(default="", max_length=50)
    architecture: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=12000)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
async def status() -> dict:
    try:
        models = await ollama.list_models()
        return {
            "ollama": "online",
            "endpoint": OLLAMA_BASE_URL,
            "models": models,
            "preferred_model": PREFERRED_MODEL,
        }
    except OllamaUnavailable as exc:
        return {
            "ollama": "offline",
            "endpoint": OLLAMA_BASE_URL,
            "models": [],
            "preferred_model": PREFERRED_MODEL,
            "message": str(exc),
        }


@app.get("/api/profiles")
def profiles() -> list[dict]:
    return list_profiles()


@app.post("/api/profiles", status_code=201)
def profiles_create(payload: ProfileCreate) -> dict:
    try:
        return create_profile(**payload.model_dump())
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="A profile with this name already exists."
        ) from exc


@app.get("/api/profiles/{profile_id}/knowledge")
def knowledge_list(profile_id: int) -> list[dict]:
    if not get_profile(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found.")
    return list_knowledge(profile_id)


@app.post("/api/profiles/{profile_id}/knowledge", status_code=201)
async def knowledge_add(
    profile_id: int,
    title: Annotated[str, Form()] = "Manual notes",
    text: Annotated[str, Form()] = "",
    redact: Annotated[bool, Form()] = True,
    files: Annotated[list[UploadFile], File()] = [],
) -> dict:
    if not get_profile(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found.")

    documents: list[tuple[str, str]] = []
    if text.strip():
        documents.append((title.strip() or "Manual notes", text.strip()))
    try:
        for upload in files:
            filename, content = await read_upload_text(upload, MAX_UPLOAD_BYTES)
            if content:
                documents.append((filename, content))
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not documents:
        raise HTTPException(status_code=400, detail="Add text or a supported file.")

    created = []
    for document_title, content in documents:
        if redact:
            content, _ = redact_sensitive(content)
        created.append(add_knowledge(profile_id, document_title, content))
    return {"documents": created}


@app.delete("/api/profiles/{profile_id}/knowledge/{document_id}")
def knowledge_delete(profile_id: int, document_id: str) -> dict:
    if not delete_knowledge(profile_id, document_id):
        raise HTTPException(status_code=404, detail="Knowledge document not found.")
    return {"deleted": True}


@app.get("/api/history")
def history(limit: int = 25) -> list[dict]:
    return list_cases(limit)


@app.get("/api/history/{case_id}")
def history_item(case_id: int) -> dict:
    item = get_case(case_id)
    if not item:
        raise HTTPException(status_code=404, detail="Case not found.")
    return item


@app.delete("/api/history/{case_id}")
def history_delete(case_id: int) -> dict:
    if not delete_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found.")
    return {"deleted": True}


@app.post("/api/analyse")
async def analyse(
    title: Annotated[str, Form()] = "",
    category: Annotated[str, Form()] = "SQL tuning",
    question: Annotated[str, Form()] = "",
    case_context: Annotated[str, Form()] = "",
    sql_text: Annotated[str, Form()] = "",
    execution_plan: Annotated[str, Form()] = "",
    ddl_and_statistics: Annotated[str, Form()] = "",
    logs_and_errors: Annotated[str, Form()] = "",
    language: Annotated[str, Form()] = "Greek",
    model: Annotated[str, Form()] = "",
    redact: Annotated[bool, Form()] = True,
    profile_id: Annotated[int | None, Form()] = None,
    files: Annotated[list[UploadFile], File()] = [],
) -> dict:
    selected_model = model.strip() or PREFERRED_MODEL
    if not selected_model:
        raise HTTPException(
            status_code=400,
            detail="Select an installed Ollama model.",
        )

    profile = get_profile(profile_id) if profile_id is not None else None
    if profile_id is not None and not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    raw_sections = {
        "sql": sql_text,
        "execution_plan": execution_plan,
        "ddl_and_statistics": ddl_and_statistics,
        "logs_and_errors": logs_and_errors,
    }
    try:
        for upload in files:
            filename, content = await read_upload_text(upload, MAX_UPLOAD_BYTES)
            if content:
                raw_sections[f"uploaded:{filename}"] = content
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not question.strip() and not any(value.strip() for value in raw_sections.values()):
        raise HTTPException(
            status_code=400,
            detail="Add a question or Oracle evidence before running the analysis.",
        )

    heuristic_analysis = analyse_oracle_evidence(raw_sections)
    prompt_sections, truncated = trim_sections(raw_sections, MAX_EVIDENCE_CHARS)
    redaction_counts: dict[str, int] = {}
    if redact:
        for key, value in list(prompt_sections.items()):
            prompt_sections[key], counts = redact_sensitive(value)
            for label, count in counts.items():
                redaction_counts[label] = redaction_counts.get(label, 0) + count

    retrieval_query = "\n".join(
        [
            question,
            case_context,
            sql_text[:12000],
            " ".join(heuristic_analysis["inventory"]["oracle_errors"]),
        ]
    )
    knowledge = retrieve_knowledge(profile_id, retrieval_query, limit=5)
    user_prompt = build_user_prompt(
        language=language,
        category=category,
        question=question,
        case_context=case_context,
        profile=profile,
        retrieved_knowledge=knowledge,
        heuristic_analysis=heuristic_analysis,
        evidence_sections=prompt_sections,
    )

    try:
        result = await ollama.analyse(
            model=selected_model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
    except OllamaUnavailable as exc:
        raise HTTPException(status_code=503, detail=public_error(exc)) from exc

    case_title = title.strip() or question.strip()[:90] or f"{category} case"
    case_id = save_case(
        profile_id,
        case_title,
        category,
        selected_model,
        question,
        result,
    )
    return {
        "case_id": case_id,
        "title": case_title,
        "analysis": result,
        "heuristics": heuristic_analysis,
        "meta": {
            "model": selected_model,
            "profile": profile.get("name") if profile else None,
            "knowledge_chunks_used": len(knowledge),
            "redaction_counts": redaction_counts,
            "evidence_truncated": truncated,
            "database_connection": False,
        },
    }


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok", "database_connection": False}
