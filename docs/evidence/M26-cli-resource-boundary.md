# M26 CLI resource-boundary hardening

The M26-02 and M26-04 through M26-08 Typer adapters accept local request and result paths.
Before this hardening, the adapters loaded complete files with `Path.read_bytes()` before
applying their declared canonical limits. M26-02 used a stat-then-read check that remained
vulnerable to file growth between the stat and read; M26-04 had no result ceiling; and M26-05
used its request ceiling while parsing results.

All six adapters now use the shared `read_bounded` primitive with their exact contract-owned
request and result ceilings before strict JSON or Pydantic parsing. This closes the TOCTOU and
unbounded-allocation paths while preserving every M26 schema, digest/replay rule, media type,
privacy boundary, and execution behavior after validation.

The adversarial matrix creates sparse `limit + 1` files for every request and result reader and
monkeypatches `Path.read_bytes` to prove that no adapter falls back to unbounded loading.
