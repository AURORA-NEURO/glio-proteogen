# Contributing

GLIO-PROTEOGEN is built one bounded dossier module at a time. Begin by reading
`CLEAN_ROOM.md`, the module's dossier entry, and its traceability matrix.

For each behavior change:

1. add or update a synthetic fixture and a requirement-to-test traceability row;
2. change the versioned contract before its implementation when the public shape changes;
3. keep module implementations isolated behind kernel ports and public contracts;
4. run lint, strict typing, the full test/eval suite, and relevant microbenchmarks;
5. describe intentional schema-digest changes in the commit or review record.

Branches and commits use concise, human-readable scientific or module names, such as
`module/M01-02-identity-lineage`. Tool- or agent-branded branch and commit names are not used.
Generated data and fixtures must be synthetic and non-clinical. Missing, unsupported, redacted,
or unknown evidence must remain explicit and must never be recoded as a negative observation.
