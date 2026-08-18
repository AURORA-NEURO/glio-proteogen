# M13-02 and M13-07 traversal firewall

This additive hardening closes a transport/replay resource-boundary gap in the
two M13 engines. Their strict validation paths materialize caller-provided
JSON-like containers recursively; previously, deeply nested dictionaries could
reach `RecursionError` and oversized sequences were traversed without a bound.
The change preserves the existing request/result schemas, digests, status
semantics, and non-inference claim ceiling.

Both engines now fail closed with their existing typed validation errors at:

- maximum nesting depth: **64**;
- maximum mapping items per mapping: **512**;
- maximum sequence items per sequence: **4,096**; and
- maximum aggregate visited nodes: **100,000**.

The limits apply to model storage, dictionaries, lists, and tuples. Existing
rejection of non-string keys and arbitrary mapping implementations remains in
place. The adversarial contract tests cover 70-level nested dictionaries and
4,097-item sequences for both M13-02 and M13-07. This is transport safety
hardening only: no protein/proteoform/isoform, glioma, kinase, treatment, or
identity inference was added.
