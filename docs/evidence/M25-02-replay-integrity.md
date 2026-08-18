# M25-02 replay integrity

M25-02 replay now regenerates the deterministic synthetic corpus from the
strictly validated request and compares the complete canonical result. A
caller cannot change a generated case, manifest, evidence record, support
decision, or limitation and make the result appear authentic by recomputing
`result_digest`.

The module remains a caller-declared synthetic fixture generator. It does not
authenticate source truth, inspect clinical/scientific payloads, infer
proteotype biology, or emit a biological conclusion. Unsupported controls and
replay mismatches remain fail-closed.
