from __future__ import annotations

import re
from typing import Any

from .security import safe_snippet


ERROR_CATALOG: dict[str, tuple[str, str, str]] = {
    "ORA-00600": (
        "critical",
        "Oracle internal error",
        "Preserve the incident/trace files and validate against Oracle Support guidance.",
    ),
    "ORA-07445": (
        "critical",
        "Unhandled Oracle process exception",
        "Correlate the trace, call stack, SQL_ID and exact database RU.",
    ),
    "ORA-01578": (
        "critical",
        "Possible block corruption",
        "Identify the affected object and validate recovery options before taking action.",
    ),
    "ORA-04031": (
        "high",
        "Shared pool or memory allocation failure",
        "Review the failing allocation, pool fragmentation and workload before resizing.",
    ),
    "ORA-01555": (
        "high",
        "Snapshot too old",
        "Compare query duration, undo retention, tuned retention and concurrent DML.",
    ),
    "ORA-00257": (
        "high",
        "Archiver error",
        "Check archive destinations and FRA pressure immediately.",
    ),
    "ORA-19809": (
        "high",
        "Recovery area limit exceeded",
        "Inspect FRA consumers and the backup/deletion policy.",
    ),
    "ORA-00060": (
        "high",
        "Deadlock detected",
        "Use the deadlock graph to identify objects, SQL and lock order.",
    ),
    "ORA-03113": (
        "high",
        "Server process or instance communication terminated",
        "Correlate the timestamp with alert log, trace files and operating-system events.",
    ),
    "ORA-01031": (
        "medium",
        "Insufficient privileges",
        "Validate the exact execution user, container and direct grants.",
    ),
}

WAIT_CATALOG: list[tuple[str, str, str, str]] = [
    (
        "enq: sv - contention",
        "high",
        "Sequence value contention",
        "On RAC, review sequence CACHE and ORDER usage; validate semantics before changing them.",
    ),
    (
        "gc current request",
        "medium",
        "RAC current-block transfer wait",
        "Correlate hot objects and instance affinity using ASH/AWR evidence.",
    ),
    (
        "gc cr request",
        "medium",
        "RAC consistent-read block transfer wait",
        "Identify objects and SQL producing cross-instance block traffic.",
    ),
    (
        "log file sync",
        "medium",
        "Commit latency",
        "Review commit frequency together with redo I/O latency and log file parallel write.",
    ),
    (
        "db file sequential read",
        "info",
        "Single-block read activity",
        "Determine whether the volume and latency are abnormal for the access path.",
    ),
    (
        "db file scattered read",
        "info",
        "Multi-block read activity",
        "Correlate with full scans and storage latency.",
    ),
    (
        "direct path read temp",
        "medium",
        "Temporary read spill",
        "Review workarea sizing, join/order operations and row estimates.",
    ),
    (
        "direct path write temp",
        "medium",
        "Temporary write spill",
        "Review workarea sizing, join/order operations and row estimates.",
    ),
]


def _number(value: str) -> float | None:
    cleaned = value.strip().replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMGT]?)", cleaned, re.I)
    if not match:
        return None
    multiplier = {
        "": 1,
        "K": 1_000,
        "M": 1_000_000,
        "G": 1_000_000_000,
        "T": 1_000_000_000_000,
    }[match.group(2).upper()]
    return float(match.group(1)) * multiplier


def _cardinality_mismatches(plan: str) -> list[dict[str, Any]]:
    headers: list[str] | None = None
    mismatches: list[dict[str, Any]] = []
    for raw_line in plan.splitlines():
        if "|" not in raw_line:
            continue
        columns = [column.strip() for column in raw_line.strip().strip("|").split("|")]
        lowered = [column.lower() for column in columns]
        if "e-rows" in lowered and "a-rows" in lowered:
            headers = lowered
            continue
        if not headers or len(columns) != len(headers):
            continue
        try:
            estimated = _number(columns[headers.index("e-rows")])
            actual = _number(columns[headers.index("a-rows")])
        except (ValueError, IndexError):
            continue
        if estimated is None or actual is None or estimated <= 0 or actual <= 0:
            continue
        ratio = max(actual / estimated, estimated / actual)
        if ratio >= 10:
            mismatches.append(
                {
                    "ratio": round(ratio, 1),
                    "severity": "high" if ratio >= 100 else "medium",
                    "line": safe_snippet(raw_line, 220),
                }
            )
    return sorted(mismatches, key=lambda item: item["ratio"], reverse=True)[:5]


def analyse_oracle_evidence(sections: dict[str, str]) -> dict[str, Any]:
    sql = sections.get("sql", "")
    plan = sections.get("execution_plan", "")
    ddl = sections.get("ddl_and_statistics", "")
    logs = sections.get("logs_and_errors", "")
    uploaded = "\n".join(
        value for key, value in sections.items() if key.startswith("uploaded:")
    )
    combined = "\n".join((sql, plan, ddl, logs, uploaded))
    upper = combined.upper()
    lower = combined.lower()
    signals: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(
        code: str,
        severity: str,
        title: str,
        evidence: str,
        guidance: str,
    ) -> None:
        if code in seen:
            return
        seen.add(code)
        signals.append(
            {
                "code": code,
                "severity": severity,
                "title": title,
                "evidence": safe_snippet(evidence),
                "guidance": guidance,
            }
        )

    errors = sorted(
        set(re.findall(r"\b(?:ORA|RMAN)-\d{5}\b", upper))
    )
    for code in errors:
        if code in ERROR_CATALOG:
            severity, title, guidance = ERROR_CATALOG[code]
        elif code.startswith("RMAN-"):
            severity, title, guidance = (
                "medium",
                "RMAN diagnostic detected",
                "Use the complete RMAN error stack and channel output; avoid acting on one line alone.",
            )
        elif code.startswith("ORA-15"):
            severity, title, guidance = (
                "high",
                "ASM-related Oracle diagnostic",
                "Correlate with ASM alert logs, disk group state and the complete error stack.",
            )
        else:
            severity, title, guidance = (
                "medium",
                "Oracle diagnostic detected",
                "Interpret the code in the context of the full error stack and timestamp.",
            )
        match = re.search(re.escape(code) + r"[^\r\n]*", combined, re.I)
        add(
            f"error:{code}",
            severity,
            f"{code} — {title}",
            match.group(0) if match else code,
            guidance,
        )

    plan_upper = plan.upper()
    full_scans = plan_upper.count("TABLE ACCESS FULL")
    if full_scans:
        add(
            "plan:full-scan",
            "medium",
            f"Full table access paths detected ({full_scans})",
            "TABLE ACCESS FULL",
            "Validate selectivity, partition pruning, object size and actual buffer gets before proposing an index.",
        )
    if "PARTITION RANGE ALL" in plan_upper or "PARTITION LIST ALL" in plan_upper:
        add(
            "plan:all-partitions",
            "high",
            "The plan may scan all partitions",
            "PARTITION ... ALL",
            "Check datatype alignment and keep functions off the partition key predicates.",
        )
    if "MERGE JOIN CARTESIAN" in plan_upper:
        add(
            "plan:cartesian",
            "high",
            "Cartesian join appears in the plan",
            "MERGE JOIN CARTESIAN",
            "Confirm join predicates and cardinality estimates before changing the join method.",
        )
    if "BITMAP CONVERSION" in plan_upper or "BITMAP INDEX" in plan_upper:
        add(
            "plan:bitmap",
            "info",
            "Bitmap access path detected",
            "BITMAP",
            "Validate DML concurrency and selectivity; bitmap indexes can amplify locking in transactional workloads.",
        )
    if re.search(r"\bPX (?:COORDINATOR|SEND|RECEIVE|BLOCK)\b", plan_upper):
        add(
            "plan:parallel",
            "info",
            "Parallel execution operators detected",
            "PX",
            "Check DOP, data distribution, downgrade messages and whether parallelism is intended.",
        )
    if any(term in lower for term in ("direct path read temp", "direct path write temp", "onepass", "multipass")):
        add(
            "workarea:spill",
            "medium",
            "Possible workarea spill to TEMP",
            "direct path ... temp / onepass / multipass",
            "Correlate with SQL workarea statistics, row estimates and TEMP usage.",
        )

    mismatches = _cardinality_mismatches(plan)
    for index, mismatch in enumerate(mismatches, start=1):
        add(
            f"cardinality:{index}",
            mismatch["severity"],
            f"Estimated vs actual rows differ by about {mismatch['ratio']}×",
            mismatch["line"],
            "Investigate object/column statistics, correlations, bind values and predicate transformations.",
        )

    sql_upper = sql.upper()
    if re.search(r"\bSELECT\s+\*", sql_upper):
        add(
            "sql:select-star",
            "low",
            "SELECT * detected",
            "SELECT *",
            "Project only required columns when row width or index-only access matters.",
        )
    if re.search(r"\bUNION\b(?!\s+ALL\b)", sql_upper):
        add(
            "sql:union",
            "low",
            "UNION duplicate elimination detected",
            "UNION",
            "Use UNION ALL only when duplicate removal is not required by the business result.",
        )
    if re.search(r"\bLIKE\s+['\"]%", sql, re.I):
        add(
            "sql:leading-wildcard",
            "medium",
            "Leading-wildcard LIKE predicate detected",
            "LIKE '%…'",
            "A normal B-tree index usually cannot provide a selective leading lookup for this predicate.",
        )
    function_predicate = re.search(
        r"\b(?:TRUNC|TO_CHAR|NVL|UPPER|LOWER)\s*\(\s*[A-Z][A-Z0-9_$#]*(?:\.[A-Z][A-Z0-9_$#]*)?",
        sql_upper,
    )
    if function_predicate:
        add(
            "sql:function-predicate",
            "medium",
            "Function applied to a possible predicate column",
            function_predicate.group(0),
            "Prefer datatype-correct range predicates or validate a function-based index when semantics require the function.",
        )
    if re.search(r"/\*\+", sql):
        add(
            "sql:hints",
            "info",
            "Optimizer hints are present",
            safe_snippet(re.search(r"/\*\+.*?\*/", sql, re.S).group(0))
            if re.search(r"/\*\+.*?\*/", sql, re.S)
            else "/*+ ... */",
            "Confirm hint validity, scope and outline evidence; hints can mask stale estimates.",
        )

    for wait, severity, title, guidance in WAIT_CATALOG:
        if wait in lower:
            add(
                f"wait:{wait}",
                severity,
                title,
                wait,
                guidance,
            )

    plan_hash_match = re.search(r"PLAN HASH VALUE\s*[:=]\s*(\d+)", upper)
    sql_id_match = re.search(r"\bSQL_ID\s*[:=]\s*([A-Z0-9]{13})\b", upper)
    inventory = {
        "sql_present": bool(sql.strip()),
        "execution_plan_present": bool(plan.strip()),
        "ddl_or_statistics_present": bool(ddl.strip()),
        "logs_present": bool(logs.strip() or uploaded.strip()),
        "characters": sum(len(value) for value in sections.values()),
        "oracle_errors": errors,
        "plan_hash_value": plan_hash_match.group(1) if plan_hash_match else None,
        "sql_id": sql_id_match.group(1).lower() if sql_id_match else None,
        "full_table_scans": full_scans,
        "cardinality_mismatches": len(mismatches),
    }

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    signals.sort(key=lambda item: severity_order.get(item["severity"], 9))
    return {"inventory": inventory, "signals": signals}
