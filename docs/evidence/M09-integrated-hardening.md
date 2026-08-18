# M09-01..M09-08 integrated hardening evidence

This lane is based on M26 `e4ae745888879fdc9895df49a9d0dcf3d8307187` and keeps every M09 ABI explicitly provisional. It hardens replay and provenance without introducing a learned model, external data fetch, or owner-confirmed endpoint.

## Concrete fixes

- All eight M09 canonical projections now accept only Pydantic models or exact built-in dictionaries. Hostile `Mapping` objects and dictionary subclasses are rejected before any accessor is invoked.
- M09-04 result validation and replay now bind the request digest, baseline/source artifact digests, configuration digest, and all seven control decisions through the expected provenance projection.
- M09-07 result validation now binds the expected provisional uncertainty profile and seven-control provenance projection.
- M09-01, M09-02, M09-03, M09-05, M09-06, and M09-08 replay verifiers reject a forged provenance record even when an attacker recomputes the result digest.

## Commit chain

`a319a522` canonical hostile-mapping closure; `2a4c2e24` estimator provenance/uncertainty closure; `c547f99e` all-module replay provenance closure; release evidence follows in this commit.

## Gates

- 247 focused M09 tests passed.
- Ruff check/format, strict MyPy across 81 M09 source files, and compileall passed.
- Branch-enabled scoped coverage passed at 95.5358789891164% (4,413/4,551 statements; 766/870 branches; 88 partial branches; fail-under 95).
- All eight evaluator entry points passed, including replay/tamper scenarios and safe abstention/quarantine paths.
- Ten-iteration benchmarks passed for all eight modules; the highest recorded p95 is 3,692,700 ns for M09-08 against a 3,000,000,000 ns budget.
- Clean wheel: 3,665,153 bytes, SHA256 `8a1f544a7bf60626954f59c6c3f66701c772f6d84e47c086b74cd44eaebc44fd`, 1,913 members.
- Clean sdist: 4,205,519 bytes, SHA256 `827b10e14348cb283044ab38f74c165d477e086d8dbee642b2b00de586b52997`, 4,389 members.
- Generated-member audit is zero for both artifacts; isolated wheel installation/import passed.

Machine-readable details and a release verifier are in `release-evidence/m09_integrated_hardening/`.
