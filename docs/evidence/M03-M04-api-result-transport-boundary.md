# M03/M04 API result transport boundary

## Defect closed

The central FastAPI app previously installed `RequestSizeLimitMiddleware` with
the 4 MiB request ceiling for every route.  M03-05 and M04-04 already declare
an independent 8 MiB canonical result ceiling, and their `/verify` parsers use
that larger bound.  The transport middleware therefore rejected a valid
4–8 MiB replay envelope with HTTP 413 before the frozen result validator could
inspect it.  This was a transport mismatch, not a contract or scientific
behavior change.

The middleware now accepts an optional result ceiling and applies it only to
paths ending in `/verify`.  Ordinary request routes retain the 4 MiB transport
limit, while replay routes can reach their existing result-specific parser
limits.  The central app binds the result transport ceiling to the existing
M03-05 frozen 8 MiB constant; no new contract field or ABI is introduced.

## Regression evidence

- The transport unit matrix proves a verify path admits a body above the
  request ceiling and rejects the first byte above the result ceiling.
- The M03-05 black-box API test sends a synthetic 4 MiB-plus malformed replay
  document and observes strict JSON validation (422), rather than premature
  transport rejection (413).
- The ordinary request-path 4 MiB boundary tests remain unchanged and pass.

This change is limited to transport admission and does not add protein,
proteoform, isoform, abundance, glioma, mechanism, clinical, or other
scientific inference authority.
