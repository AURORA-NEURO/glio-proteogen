# M22-06 release evidence

This directory contains generated, hash-bound evidence for the provisional M22-06 build.
`evaluation.json`, `benchmark.json`, and `coverage.json` are produced only after the focused
suite and scoped gates pass. `package.json` records the exact wheel and sdist identity, isolated
import result, and release-verifier result. Run:

```text
python tools/verify_m2206_release.py --evidence-dir release-evidence/m22_06 --wheel <wheel> --sdist <sdist>
```

The evidence is not an owner approval or scientific qualification. It retains the M22-05 input as
the declared media boundary and does not authenticate upstream caller evidence.
