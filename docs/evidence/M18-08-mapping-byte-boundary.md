# M18-08 mapping byte-boundary closure

M18-08 already bounded byte and string inputs through its strict JSON parser,
but direct Mapping inputs took a separate path that converted and validated
the mapping without enforcing the same declared canonical byte limits. This
could make service and plugin callers bypass the request/result resource
boundary documented by the contract.

The service now applies the existing limits uniformly to all mapping paths:

- request canonical bytes: **4 MiB**;
- result canonical bytes: **8 MiB**.

Oversized mappings fail before contract validation with a bounded service
error. Byte/string behavior, schemas, replay identity, status semantics, and
the provisional non-inference claim ceiling are unchanged. The adversarial
runtime selection covers execute, validate_request, and verify mapping paths.
