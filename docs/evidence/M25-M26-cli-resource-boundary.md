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

Validation evidence:

- 15 adversarial resource-boundary tests and 51 scoped M25/M26-03 tests passed.
- Ruff/format, strict MyPy on 8 touched files, and compileall passed.
- Two `SOURCE_DATE_EPOCH=315532800` builds were byte-identical: wheel 3,868,492 bytes,
  SHA-256 `59d022fc7dc202b59a4afb5be6f0d43e05e15b035fb2815ceecc091a66c545c9`; sdist
  4,533,751 bytes, SHA-256 `e8697c2836f248fd57059ab1bf3a8ef1db9b47fcf9baddc99d7cc4dd46571cf1`.
