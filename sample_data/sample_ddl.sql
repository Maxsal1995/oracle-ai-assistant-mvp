-- Synthetic DDL. No production identifiers or data.
CREATE TABLE demo_variable_value (
  vv_ce_id       NUMBER NOT NULL,
  vv_timestamp   TIMESTAMP NOT NULL,
  vv_value       NUMBER
)
PARTITION BY RANGE (vv_timestamp)
INTERVAL (NUMTODSINTERVAL(1, 'DAY'))
(
  PARTITION p0 VALUES LESS THAN (TIMESTAMP '2026-01-01 00:00:00')
);

CREATE INDEX demo_vv_ix1
ON demo_variable_value (vv_ce_id, vv_timestamp)
LOCAL;

-- Synthetic workload notes:
-- Total rows: 180,000,000
-- Approximate rows per day: 500,000
