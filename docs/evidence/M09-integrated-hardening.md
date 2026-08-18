# M09-01..M09-08 integrated hardening evidence

This lane is based on merged M26 `77fb1ce6537161b529c53084fa8e27a9c18f021a` and keeps every M09 ABI explicitly provisional. It hardens replay and provenance without introducing a learned model, external data fetch, or owner-confirmed endpoint.

## Concrete fixes

- All eight M09 canonical projections now accept only Pydantic models or exact built-in dictionaries. Hostile `Mapping` objects and dictionary subclasses are rejected before any accessor is invoked.
- M09-04 result validation and replay now bind the request digest, baseline/source artifact digests, configuration digest, and all seven control decisions through the expected provenance projection.
- M09-07 result validation now binds the expected provisional uncertainty profile and seven-control provenance projection.
- M09-01, M09-02, M09-03, M09-05, M09-06, and M09-08 replay verifiers reject a forged provenance record even when an attacker recomputes the result digest.

## Commit chain

`42670825` canonical hostile-mapping closure; `b3f3142b` estimator provenance/uncertainty closure; `ff9316f3` all-module replay provenance closure; `c34639c5` initial release evidence; a final base/package refresh follows this commit.

## Gates

- 247 focused M09 tests passed.
- Ruff check/format, strict MyPy across 83 M09 source/evidence files, and compileall passed.
- Branch-enabled scoped coverage passed at 95.5358789891164% (4,413/4,551 statements; 766/870 branches; 88 partial branches; fail-under 95).
- All eight evaluator entry points passed, including replay/tamper scenarios and safe abstention/quarantine paths.
- Ten-iteration benchmarks passed for all eight modules; the highest recorded p95 is 3,692,700 ns for M09-08 against a 3,000,000,000 ns budget.
- Clean wheel: 3,665,149 bytes, SHA256 `a594a0c4c0672f6d18489b981857d69fe3a19fe32128601e84a9c7d578fa686b`, 1,913 members.
- Clean sdist: 4,206,466 bytes, SHA256 `53cf5d86bbb42e988faef229d5b94feb917b156e72b2019488ac371b1f566570`, 4,390 members.
- Generated-member audit is zero for both artifacts; isolated wheel installation/import passed.

Machine-readable details and a release verifier are in `release-evidence/m09_integrated_hardening/`.
