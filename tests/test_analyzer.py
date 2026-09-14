from app.oracle_analyzer import analyse_oracle_evidence
from app.security import redact_sensitive, trim_sections


def test_detects_partition_and_cardinality_signals() -> None:
    sections = {
        "sql": "select * from demo where trunc(event_time) = date '2026-09-01'",
        "execution_plan": """
| Id | Operation             | Name | Starts | E-Rows | A-Rows |
|  1 | PARTITION RANGE ALL   |      |      1 |    100 |  86400 |
|  2 |  TABLE ACCESS FULL    | DEMO |    365 |    100 |  86400 |
""",
        "ddl_and_statistics": "",
        "logs_and_errors": "",
    }
    result = analyse_oracle_evidence(sections)
    codes = {item["code"] for item in result["signals"]}

    assert "plan:all-partitions" in codes
    assert "plan:full-scan" in codes
    assert "sql:function-predicate" in codes
    assert result["inventory"]["cardinality_mismatches"] >= 1


def test_detects_rac_sequence_wait() -> None:
    result = analyse_oracle_evidence(
        {
            "sql": "",
            "execution_plan": "",
            "ddl_and_statistics": "",
            "logs_and_errors": "Top event: enq: SV - contention",
        }
    )
    titles = {item["title"] for item in result["signals"]}
    assert "Sequence value contention" in titles


def test_detects_critical_oracle_error() -> None:
    result = analyse_oracle_evidence(
        {
            "sql": "",
            "execution_plan": "",
            "ddl_and_statistics": "",
            "logs_and_errors": "ORA-01578: ORACLE data block corrupted",
        }
    )
    signal = next(item for item in result["signals"] if "ORA-01578" in item["title"])
    assert signal["severity"] == "critical"


def test_redaction_and_section_limit() -> None:
    cleaned, counts = redact_sensitive(
        "password=Secret1 user@example.com 10.20.30.40"
    )
    assert "Secret1" not in cleaned
    assert "user@example.com" not in cleaned
    assert "10.20.30.40" not in cleaned
    assert sum(counts.values()) == 3

    trimmed, truncated = trim_sections({"a": "12345", "b": "67890"}, 7)
    assert "".join(trimmed.values()) == "1234567"
    assert truncated is True
