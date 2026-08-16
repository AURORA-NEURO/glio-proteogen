# M03/M04 non-inference boundary evidence

| Field | Evidence |
| --- | --- |
| Scope | `GLIO-PROTEOGEN-M03-01` through `M03-08` and `M04-01` through `M04-04` in the merged M26-08 ancestry |
| Boundary | Results cannot assert protein, proteoform, isoform, or glioma-specific biology inference |
| Closed fields | `infers_protein`, `infers_proteoform`, `infers_isoform`, and `infers_glioma_specific_biology` are `Literal[False]` on every audited result envelope |
| Schema metadata | Every audited contract schema publishes `proteinInference`, `proteoformInference`, `isoformInference`, and `gliomaSpecificBiologyInference` as `false`; output properties use JSON Schema `const: false` |
| Runtime/replay | Service payloads bind all four flags before result digest calculation; nested M03-06 analysis and M04-03 result replay include the same fields |
| Interface boundary | FastAPI, Typer, and strict parse-once plugin paths reject true or unknown inference claims and preserve false flags in output |
| Python LOC delta | +114 production source lines (+87 M03, +27 M04); +226/−9 test lines; 47 Python files changed from `fad7ffd5` |
| Commits | `b718a733`, `7db3f552`, `cb95a619`, `030c0a2a`, `769a57be`, `a5e7318d` |

## Hard boundary

The audited modules validate quality, protocol, lineage, support, provenance, artifact, and
release metadata only. They do not issue or imply a protein identity, proteoform or isoform
identity, or glioma-specific biological interpretation. They also cannot carry such claims in
unknown fields: the strict frozen models reject extra keys, while the four closed literal flags
reject `true` values. This prohibition includes diagnoses, subtype or tumor biology, treatment,
kinase, fusion, and generic all-omics conclusions. Legitimate input-role vocabulary and lineage
references remain intact because they describe declared evidence sources, not asserted output
biology.

## Verification record

- 1,394 affected contract tests pass with coverage disabled for the deterministic gate run.
- 360 M03/M04 FastAPI/Typer/plugin integration tests pass.
- The dedicated adversarial boundary suite covers all 12 audited result models, all four true
  claims, unknown glioma fields, schema metadata/`const` closure, plugin rejection, and API/CLI
  rejection/output parity.
- Replay tests cover digest binding after the new flags are added; missing or altered flags cannot
  be silently dropped from a canonical result.
- Static checks and package/release checks are recorded below as they are run on the clean branch.

M04-05 through M04-08 are not ancestors of the merged M26-08 stack and are intentionally not
represented as audited by this record; they require the corresponding M04-08 branch to be based
and checked separately rather than silently mixing incompatible histories.
