# M25-01 replay integrity

M25-01 now verifies semantic replay, not only self-consistent hashes. The
curator rebuilds the complete result from the bound, strictly validated request
and compares canonical result bytes before returning a verified result. This
closes a class of forged reference packages in which a caller changed evidence,
support, provenance, limitations, or status and then recomputed `result_digest`.

The replay boundary remains deterministic and fail-closed: request and result
digests, derived result identity, package lock digest, and the full canonical
result projection must all agree. API, CLI, service, and plugin verification
therefore share the same semantic closure.

This module still curates caller-declared benchmark material only. It does not
authenticate an issuer, inspect raw scientific payloads, infer proteotype
biology, or emit clinical/reference truth claims.
