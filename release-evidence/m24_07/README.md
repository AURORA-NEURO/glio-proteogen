# M24-07 release evidence

This directory freezes the provisional M24-07 evaluator matrix, benchmark,
branch-enabled coverage, independent release verifier and package records. The
M24-06 relationship is media-only and caller-declared; no unpublished upstream
runtime ABI is imported.

Run `uv run python tools/verify_m2407_release.py --root . --wheel <wheel>
--sdist <sdist>` after building candidate artifacts. The verifier checks
authority, scenario counts, benchmark budgets, coverage, hashes, wheel members
and isolated import evidence.

The current fixed-epoch build pair is byte-identical: the wheel is 3,930,670
bytes (SHA-256
`271a7362f0b6a9ac2151285424d9863edf6a2a5165c6a793b427afd35759b20d`, 1,997
members) and the sdist is 4,626,866 bytes (SHA-256
`85867769a7be42fbacfed69a252b0d7c71e29961b2cda9bfc8820293f4f3e301`, 4,687
members). These receipts are refreshed whenever the stacked source changes.
