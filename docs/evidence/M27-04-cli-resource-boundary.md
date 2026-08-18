# M27-04 CLI resource-boundary hardening

The M27-04 Typer gateway accepted request and result paths through unbounded
`Path.read_bytes()` calls. Request JSON was checked only after full allocation, and result
JSON had no byte ceiling at all, despite the frozen contract defining request and result
canonical limits.

Both readers now use the shared `read_bounded` primitive with the contract-owned limits before
strict JSON or Pydantic parsing. This aligns the CLI with the already-bounded M27-04 HTTP,
service, and plugin paths without changing the request/result schema, replay behavior, media
type, or claim boundary.

The adversarial tests create sparse `limit + 1` files to prove both request and result
rejection without allocating large payloads. A monkeypatched `Path.read_bytes` firewall proves
the readers cannot regress to unbounded loading.
