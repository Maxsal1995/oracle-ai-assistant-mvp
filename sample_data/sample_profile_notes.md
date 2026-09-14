# Synthetic Oracle profile

- Oracle version: 19c
- Environment: TEST
- Architecture: two-node RAC, one CDB and one application PDB
- Storage: ASM
- Constraints:
  - Preserve exact SQL results.
  - Do not recommend a new index without access-path and DML evidence.
  - Prefer range predicates that allow partition pruning.
  - Proposed changes require a validation query and rollback plan.
