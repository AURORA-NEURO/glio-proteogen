# M24-02 transport-boundary evidence

This note records an additive, provisional transport hardening change for
M24-02. It does not freeze the module ABI, add a governed scientific claim, or
register a new central operation.

- FastAPI request routes reject bodies above the M24-02 request ceiling before
  route JSON/model parsing. The replay route has a separately declared result
  envelope ceiling.
- The replay adapter applies the result ceiling again to strict JSON parsing,
  so direct route invocation cannot bypass the transport boundary.
- The Typer `verify` command reads result files through the bounded adapter and
  maps oversized files to the same sanitized validation error as malformed
  results.
- Adversarial tests cover declared HTTP request overflow, declared replay
  envelope overflow, and the CLI oversized-result failure path.

The limits are denial-of-service and parser-safety controls only. They do not
authenticate caller-declared synthetic truth, infer biology, or change the
module's explicit provisional claim ceiling.
