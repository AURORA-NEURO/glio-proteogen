# M10-04 through M10-08 adapter resource boundaries

The M10-04, M10-05, M10-06, and M10-08 contracts declare a 4 MiB canonical
request ceiling and an 8 MiB canonical result ceiling. Their Typer adapters
previously called `Path.read_bytes()` directly (and M10-08 consumed stdin
without a bound), so the JSON parser's limit was applied only after the whole
file had been materialized in memory.

The adapters now use the shared bounded reader before JSON parsing. Request and
result paths select their respective contract ceiling, while M10-08 stdin
reads at most `limit + 1` bytes so an overflow is rejected without retaining an
unbounded payload. The existing strict JSON validation, service execution,
replay verification, error mapping, schemas, media types, and provisional
claim ceilings are unchanged.

Adversarial interface coverage verifies all six M10-04/05/06 request/result
reader combinations, both M10-08 path readers, the M10-08 stdin path, and a
`Path.read_bytes` firewall. Tests use 32-byte monkeypatched ceilings and
33-byte fixtures, avoiding large allocations while exercising the same
fail-before-parse behavior as the production 4/8 MiB limits.
