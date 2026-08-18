# M09 CLI resource boundaries

This record covers the eight provisional M09 command-line surfaces: M09-01,
M09-02, M09-03, M09-04, M09-05, M09-06, M09-07, and M09-08. Their contracts
already declare strict JSON ceilings; this pass makes the CLI admission match
those declarations before any parser or model validation runs.

## Change

Every request/result path read now uses the shared bounded reader with the
module's request or result ceiling. M09-01 and M09-06 canonical replay files
are bounded independently as result artifacts. No operation, schema, result
claim, or provisional ABI changed.

## Evidence

- two focused tests cover all eight validate commands and AST read-path guards;
- Ruff and strict MyPy pass on all nine touched files;
- compileall and diff checks are clean;
- sparse overflow fixtures prove rejection at the first byte over 4 MiB,
  without constructing a large JSON document.
