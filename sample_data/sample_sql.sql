-- Synthetic example. No production identifiers or data.
SELECT vv_ce_id,
       vv_timestamp,
       vv_value
FROM   demo_variable_value
WHERE  TRUNC(vv_timestamp) = DATE '2026-09-01'
AND    vv_ce_id = :ce_id
ORDER BY vv_timestamp;
