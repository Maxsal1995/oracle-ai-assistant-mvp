# Oracle AI Assistant MVP

Local-first Oracle tuning and troubleshooting assistant for Windows. It analyses only the evidence that you paste or upload; it **does not connect to Oracle** and it never executes SQL.

## What the MVP does

- Analyses SQL text, execution plans, DDL, AWR/ADDM excerpts, alert logs and trace text.
- Performs deterministic Oracle-specific checks before the LLM is called.
- Uses a local Ollama model through `http://127.0.0.1:11434`.
- Stores database profiles, knowledge-base text and case history in a local SQLite file.
- Returns structured findings with severity, evidence, recommendations, validation SQL and risk notes.
- Exports each result as Markdown.
- Listens only on `127.0.0.1` by default.

## Safety boundary

This is a decision-support tool, not an autonomous DBA.

- No Oracle client or database credentials are used.
- No connection string is accepted.
- No SQL, DDL, RMAN or operating-system command is executed.
- Uploaded case evidence is processed in memory. Knowledge-base documents are stored locally only when you explicitly add them to a profile.
- Case history stores the question and generated result, not the raw evidence.
- Password-like values, e-mail addresses, IPv4 addresses and URL credentials can be redacted before the prompt is sent to Ollama.
- Always validate recommendations in a non-production environment.

## Windows quick start

### Prerequisites

1. Windows 10 22H2 or newer.
2. Python 3.11 or newer.
3. [Ollama for Windows](https://ollama.com/download/windows).

### Install

```bat
git clone https://github.com/Maxsal1995/oracle-ai-assistant-mvp.git
cd oracle-ai-assistant-mvp
setup.bat
```

Install at least one Ollama model. For example:

```bat
ollama pull qwen3:8b
```

You may use any chat-capable model already installed in Ollama. The application discovers local models automatically.

### Run

```bat
start.bat
```

The application opens at [http://127.0.0.1:8000](http://127.0.0.1:8000).

## First test

1. Select **Load synthetic example**.
2. Choose an installed Ollama model.
3. Select **SQL tuning**.
4. Run the analysis.
5. Review the deterministic signals and the structured AI findings separately.

Synthetic examples are also available under `sample_data/`.

## Knowledge base

Create one profile per environment or logical database. Useful context includes:

- Oracle version, CDB/PDB and RAC topology.
- Important table and index DDL.
- Partitioning strategy and retention policy.
- Sanitised statistics or workload notes.
- Known application constraints and change-management rules.
- Sanitised AWR/ADDM excerpts and previous incident conclusions.

Supported text formats: `.txt`, `.sql`, `.log`, `.trc`, `.out`, `.lst`, `.md`, `.json`, `.xml`, `.csv`, `.html` and `.htm`.

## Configuration

On first setup, `.env.example` is copied to `.env`.

| Setting | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama endpoint |
| `ORACLE_AI_MODEL` | empty | Preferred model; otherwise the first installed model |
| `ORACLE_AI_DATA_DIR` | `data` | Local database directory |
| `MAX_UPLOAD_MB` | `5` | Maximum size per uploaded file |
| `MAX_EVIDENCE_CHARS` | `180000` | Combined prompt evidence limit |
| `OLLAMA_TIMEOUT_SECONDS` | `300` | Local generation timeout |

## Tests

```bat
.venv\Scripts\python -m pytest
```

## Project structure

```text
app/
  main.py              FastAPI routes and application boundary
  database.py          Local SQLite profiles, knowledge and history
  oracle_analyzer.py   Deterministic Oracle signals
  ollama_client.py     Local Ollama API client
  prompts.py           Evidence-grounded DBA prompt
  security.py          Upload validation and optional redaction
  static/              Browser interface
sample_data/            Synthetic demonstration evidence
tests/                  Deterministic checks
```

## Current limitations

- Text and HTML evidence only; binary AWR PDFs are not parsed.
- Retrieval is lightweight lexical matching, not vector search.
- The quality of the final synthesis depends on the chosen local model.
- Recommendations are evidence-based hypotheses and require DBA validation.

## Suggested next phase

- Oracle-focused embedding model and vector retrieval.
- AWR HTML section parser and plan comparison.
- Team authentication and encrypted shared storage.
- Optional cloud LLM provider with an explicit redaction/approval gate.
- Read-only collector scripts that generate sanitised evidence bundles, without granting the AI direct database access.
