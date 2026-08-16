# M07-07 release evidence

This directory records the local candidate release for
`GLIO-PROTEOGEN-M07-07`, calibration and selective prediction. It is evidence
for review and is not ABI promotion, clinical validation, or an approval.

## Authority

- Dossier SHA-256: `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`
- Exact slice: lines `2460–2503`
- Contract/ABI: `0.1.0-provisional`
- Owner/safety/gate: Quality engineering / S2 / G3

## Gate summary

| Gate | Result |
| --- | --- |
| Focused tests | 25 passed |
| Ruff | clean |
| MyPy strict | clean across 15 source files |
| Branch coverage | 96.36% (729 statements, 150 branches), fail-under 95 passed |
| Evaluator | 8 declared, 8 executed, 0 failed |
| Benchmark | mean 2,915,200 ns; median 2,938,100 ns; p95 3,276,900 ns |
| Benchmark budgets | mean 2,000,000,000 ns; p95 3,000,000,000 ns; passed |
| Compileall | passed |
| Wheel | 769,371 bytes; SHA256 `92a70bcf630f7266bc2b90e40a409c9ffc1ac4897b0682d6283977294c71d8d8` |
| Sdist | 1,441,520 bytes; SHA256 `931d1bd18a01c4f2c93febfa79686bdc37f349b2ede04dbdf480dd04f0b84d74` |
| Isolated import | passed (`M0707Service`) |

The JSON reports are machine-readable snapshots of the evaluator, benchmark,
and package gates. They are regenerated when the release candidate changes.

## Limitations

The runtime consumes caller-declared candidates and evidence. It does not fit
or execute a calibration model, authenticate evidence, dereference scientific
content, establish measurement truth, assess subgroup parity, establish
transportability, or emit clinical, kinase, treatment, or parent-proteotype
claims. Promotion requires external review and an ABI decision.
