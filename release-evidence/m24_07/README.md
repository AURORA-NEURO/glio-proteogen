# M24-07 release evidence

This directory freezes the provisional M24-07 evaluator matrix, benchmark,
branch-enabled coverage, independent release verifier and package records. The
M24-06 relationship is media-only and caller-declared; no unpublished upstream
runtime ABI is imported.

Run `uv run python tools/verify_m2407_release.py --root . --wheel <wheel>
--sdist <sdist>` after building candidate artifacts. The verifier checks
authority, scenario counts, benchmark budgets, coverage, hashes, wheel members
and isolated import evidence.
