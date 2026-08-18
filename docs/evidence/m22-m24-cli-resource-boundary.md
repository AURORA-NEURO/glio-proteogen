# M22-M24 CLI resource boundary

The M22-M24 command-line adapters accept JSON paths, but the contracts already
declare separate request and result byte ceilings. Before this hardening, the
readers called `Path.read_bytes()` and only applied the request ceiling after
the entire file was resident. A hostile result file could therefore bypass its
declared transport bound before Pydantic validation.

This lane changes the 16 implemented readers to use
`glio_proteogen.adapters.limits.read_bounded` before strict JSON or model
parsing:

- M22-01 through M22-08;
- M23-01 through M23-05, M23-07, and M23-08;
- M24-07.

Request reads use `Mxxxy_MAX_CANONICAL_REQUEST_BYTES`; result reads use
`Mxxxy_MAX_CANONICAL_RESULT_BYTES`. Oversize and unreadable files are converted
to the existing sanitized Typer `BadParameter` boundary. No contract model,
media type, result digest, replay algorithm, or provisional ABI changes.

`tests/interfaces/test_m22_m24_cli_resource_limits.py` exercises every reader
for request overflow, result overflow, and a monkeypatched `Path.read_bytes`
regression. The test matrix is intentionally generated from each module's
published contract constants so a future M22-M24 adapter cannot silently omit
one side of the request/result limit pair.

This is a transport/resource safety correction only. It does not make any
M22-M24 caller-declared transport, benchmark, subgroup, robustness, human
factors, evidence-gate, or biomarker-panel value authoritative.
