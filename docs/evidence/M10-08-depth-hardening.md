# M10-08 depth hardening evidence

This lane is based on main `8cc38ba128b11dcf3997357b066c2619ea15eb20` and the
authoritative M10-08 slice at dossier SHA
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, lines
`3584-3627`. The `0.1.0-provisional` ABI remains owner-confirmation pending;
this lane hardens the existing contract without promoting it to a frozen
endpoint or scientific claim.

## Concrete closures

- Canonical request/result projections reject arbitrary `Mapping` objects and
  dictionary subclasses before any user accessor is invoked.
- Result replay binds the exact request digest, all source/evidence digests,
  seven control decisions, uncertainty profile, limitations, nested bundle,
  and explanation evidence. Recomputing a forged result digest does not bypass
  these bindings.
- Result verification rejects hostile result containers without traversing
  them.
- FastAPI and Typer result verification enforce the distinct 8 MiB result
  boundary; request parsing remains bounded at 4 MiB.
- Existing safety semantics remain fail-closed: no identity or consent
  inference, raw external payload traversal, upstream mutation, kinase
  activity, all-omics fusion, treatment recommendation, or unsupported-to-
  negative conversion.

## Commit chain

- `979d2ddc` contract canonicalization, provenance/uncertainty/nested replay
  closure and adversarial tests.
- `71d6a70e` hostile result verifier rejection.
- `490d94f7` API/CLI result byte-limit parity and oversize test.
- Release evidence and package verifier follow in the final release commit.

## Gates

- 31 focused M10-08 tests passed; three expected Pydantic serializer warnings
  occur only while constructing adversarial tamper payloads.
- Ruff check and format clean for changed contract/runtime/interface/evidence
  files; strict MyPy clean for the M10-08 source and release verifier files;
  compileall clean.
- Branch-enabled scoped coverage: 96.29080118694363% (546/562 statements,
  103/112 branches, 9 partial branches; fail-under 95).
- Evaluator passed all seven checks: complete publication, deterministic
  replay, duplicate JSON rejection, incomplete abstention, tampered digest
  rejection, control fail-closed behavior, and wrong upstream media rejection.
- Ten-iteration benchmark passed: mean 2,136,270 ns, median 2,057,200 ns,
  p95 2,898,400 ns against 2e9/3e9 ns budgets.
- Wheel: 3,669,339 bytes, SHA256
  `92f2e14bb2cefbf311ca8cf5ab40f70925d7412902b02d5c1cb240c09a0a379a`, 1,913
  members; generated members 0 and unsafe paths 0.
- Sdist: 4,212,041 bytes, SHA256
  `f0758ba0d0a50d9652c72df9c95b590c0ef608e4de43cd81cd4b022d46897a4e`, 4,392
  members; generated members 0 and unsafe paths 0.
- Isolated wheel installation/import passed (`glio_proteogen` and M10-08 app
  construction).

Machine-readable tuples and the release verifier are in
`release-evidence/m10_08/`.
