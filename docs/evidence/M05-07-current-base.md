# M05-07 current-base release evidence

This lane is based on the merged M05-06 head `6a0f45f7` and targets
`module/M05-06-ptm-harmonization-current-29637`. M05-07 remains provisional
(`0.1.0-provisional`): it routes caller-declared PTM-localization support
within eight closed dimensions and abstains on missing, unknown, or
outside-domain declarations. It does not infer a protein, proteoform,
isoform, glioma-specific biological finding, or negative scientific result.

## Verified gates

- 59 focused contract, runtime, lifecycle, interface, evaluator, package, and
  adversarial tests passed.
- Ruff check/format and compileall passed on the scoped source, evaluator, and
  test files.
- MyPy strict passed on 18 targeted files.
- Branch-enabled scoped coverage is 99%: 437 statements (436 covered), 94
  branches (all covered), with fail-under 95%; the exact include scope is in
  `release-evidence/m05_07/coverage.json`.
- The locked evaluator passed 10/10 checks across seven scenarios plus tamper
  and dimension closure; fixture digest is
  `sha256:c5365f0e85b9dc16fe480263fdf60d82cbc48e05b5d08ed89122bb0cdd38658b`.
- Direct benchmark entrypoint now bootstraps repository-root imports. The two
  public paths passed with means 1.5452 ms and 1.5143 ms under the 250 ms
  budget; a pinned JSON receipt is recorded with package evidence.

The API and Typer route return the same canonical result, strict JSON rejects
duplicate keys and unknown fields, denied controls fail closed, and replay and
tamper checks remain deterministic.
