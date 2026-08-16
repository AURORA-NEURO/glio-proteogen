# M21-01 release evidence

This directory contains reproducibility evidence for the provisional
M21-01 reference-truth curator. The ABI is not a production release.

- Authority SHA-256: `0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`
- Authority slice: `7185–7228`
- Fixture request digest: `sha256:9305f53219d37fe0d6ffbbc563626af866812caf394183f5678e1f78b70a7b2e`
- Fixture result digest: `sha256:7a763ee9aa843a00c9ce6261efb534c335f4a9efea6f751f46b1e95dcc2892dd`
- Focused suite: 36 tests (12 contract/interface, 22 adversarial, 2 evaluator)
- Scoped coverage: 95.812% combined with branch measurement (664 statements, 124 branches)
- Evaluator: 6/6 scenarios
- Benchmark: mean 9,548,720 ns; median 8,181,050 ns; p95 19,865,200 ns; budgets 500,000,000/750,000,000 ns
- Wheel: 967,950 bytes; SHA-256 `4635e040cd43a7467ab89177a2d4c53306eb26a4f0ec4e366a7d0e5c764f5d84`
- Sdist: 1,516,895 bytes; SHA-256 `e4434781eb3b4f11d41f6313401768dff4e143f42c932fdab874ccb0d7979805`
- Release status: wheel/sdist build, isolated import, and hash capture passed
