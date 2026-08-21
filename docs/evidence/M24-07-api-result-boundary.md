# M24-07 replay API result boundary

M24-07 remains a provisional, standalone evaluator; this additive fix does not
freeze its ABI or add central API/CLI registration.

The FastAPI replay endpoint now uses the contract's declared
`M2407_MAX_CANONICAL_RESULT_BYTES` limit end to end. The transport middleware
selects that limit for `/verify`, the bounded stream reader applies it before
materializing the body, and strict JSON parsing receives the same limit. Other
request endpoints retain the stricter request-envelope ceiling.

This prevents a valid result envelope from being rejected at the request cap
while ensuring an oversized replay envelope is rejected before parsing. The
regression tests cover both the request-to-result limit transition and a
declared result overflow.
