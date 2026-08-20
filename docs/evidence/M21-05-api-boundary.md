# M21-05 API transport boundary evidence

This note records the interface hardening for the provisional M21-05 subgroup
equity evaluator. It does not freeze the provisional scientific ABI or widen
the module's claims.

The FastAPI adapter now enforces the declared transport ceilings before JSON or
Pydantic parsing:

- request and validate/evaluate routes: 4 MiB;
- result and verify routes: 8 MiB;
- streamed/chunked bodies are counted even when `Content-Length` is absent;
- `validate`, `evaluate`, and `verify` require `application/json` (parameters
  after the media type are accepted).

The Typer and plugin boundaries already use the same request/result ceilings.
The API now matches those boundaries and rejects oversized bodies with HTTP
413, while wrong media types receive HTTP 415. No submitted payload is echoed
in the errors.

Evidence is covered by:

- interface parity and wrong-media tests in
  `tests/interfaces/test_m21_05_interfaces.py`;
- direct ASGI chunked-body tests in
  `tests/integration/test_m21_05_transport.py`;
- malformed, authorization, and replay adversarial tests in
  `tests/adversarial/test_m21_05_adversarial.py`.

The implementation remains caller-declared and provisional. Transport limits
protect resource use; they do not authenticate upstream scientific evidence or
promote subgroup material into a biological claim.
