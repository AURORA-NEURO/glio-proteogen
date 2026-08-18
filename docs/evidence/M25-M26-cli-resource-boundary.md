# M25/M26-03 CLI resource boundary

The M25-01, M25-02, M25-03, M25-05, M25-07, M25-08, and M26-03 command-line
adapters now enforce their published canonical request and result byte ceilings
at the file-read boundary. Each reader uses the shared bounded reader before
strict JSON or Pydantic parsing; oversized or unreadable files remain inside
the existing sanitized Typer error envelope.

This closes a concrete transport gap: `Path.read_bytes()` previously loaded an
unbounded request or result before the contract limit was applied. The new
matrix covers both limits for all seven adapters and monkeypatches
`Path.read_bytes` to prove the adapters cannot regress to the unbounded path.
Sparse files are used by the tests so the boundary proof does not allocate a
full multi-megabyte payload.

The change is deliberately limited to resource admission. It does not alter
any M25/M26-03 contract model, digest/replay algorithm, media type, provisional
ABI, scientific claim, privacy rule, or execution behavior after validation.
