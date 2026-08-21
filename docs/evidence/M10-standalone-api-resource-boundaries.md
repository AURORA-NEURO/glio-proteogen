# M10 standalone API resource boundaries

The M10 standalone FastAPI applications now enforce their declared canonical
request ceilings at the ASGI transport boundary, before a request reaches
`Request.body()`, strict JSON decoding, or Pydantic validation. This closes a
resource-admission gap that existed even though the central application and
the M10 command-line readers already enforced bounded input.

The boundary applies to M10-01, M10-02, M10-03, and M10-07. Each application
uses the request limit exported by its provisional contract. M10-07's
`/v1/modules/M10-07/verify` route is selected explicitly as a result envelope
and uses its separate result ceiling; validation and execution retain the
request ceiling. An oversized declared `Content-Length` or streamed body is
rejected with HTTP 413 and is never parsed.

This is transport/resource hardening only. It does not widen any M10 ABI,
claim a scientific inference capability, or change the existing strict parser
semantics for bodies within the declared limit. The regression matrix covers
all four request surfaces and the M10-07 result-specific path, including the
before-parser 413 response and its sanitized detail.
