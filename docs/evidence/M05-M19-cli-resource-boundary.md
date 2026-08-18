# M05-08 and M19-07 CLI resource boundary

The M05-08 release CLI and M19-07 downstream-export CLI now use the shared
bounded streaming reader before strict JSON parsing. This closes the prior
unbounded `Path.read_bytes()` admission path while preserving the existing
request/result ceilings and typed ABI.

M19-07 result admission is bound to its declared
`M1907_MAX_CANONICAL_RESULT_BYTES` ceiling. It no longer derives the result
limit from the request ceiling, so the CLI, plugin, and FastAPI surfaces remain
aligned if those independently governed limits change.

The regression matrix uses sparse files one byte over each ceiling and patches
`Path.read_bytes` to prove the readers perform bounded streaming I/O. No
contract fields, replay semantics, claims ceiling, or scientific behavior are
changed.
