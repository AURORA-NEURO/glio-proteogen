# M24-06 replay integrity

An evaluated M24-06 result now binds its robustness scenarios and locked
challenge configuration exactly to the request before the result digest is
checked. Replacing a challenge declaration or configuration and recomputing
`result_digest` therefore fails strict result validation.

The request also binds its execution-context identifier. This is an
ABI-neutral provenance boundary: M24-06 remains caller-declared, does not
authenticate issuer authority, and does not turn unsupported challenges into
negative findings.
