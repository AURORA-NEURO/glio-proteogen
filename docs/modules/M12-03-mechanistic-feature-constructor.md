# M12-03 mechanistic feature constructor

Status: `0.1.0-provisional`; ABI and endpoint names remain subject to owner confirmation.

## Authority and boundary

The authoritative dossier is `GLIO-PROTEOGEN_240_Module_Dossier.md`, SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact M12-03
slice lines 4084–4127. The module is owned by Clinical science, safety class S2,
gate G1, under the Driver-to-protein consequence map and parent target `biomarker_panel`.

M12-03 constructs interpretable pathway, topology, state, lineage, kinetics, spatial,
and regulatory feature objects from caller-declared references. It preserves complete
feature lineage, source evidence, units, configuration, relations, typed uncertainty,
support status, limitations, and human-review requirements.

The implementation never traverses external artifacts, authenticates issuer claims,
mutates upstream evidence, infers identity or consent, converts missing evidence to a
negative finding, emits the parent biomarker panel, infers kinase activity, performs
generic all-omics fusion, or recommends treatment. Kinase-state ownership remains with
KINOPHOS.

## Contract and runtime

- Strict frozen Pydantic request/result models with exact M12-02 media-type binding.
- Locked configuration, transformation IDs, topology reference, negative-control artifacts,
  source artifact references, one-value feature shape, relation endpoint closure, and complete lineage.
- Deterministic canonical request/result digests and replay verification.
- Seven-control preflight: approved configuration, identity lineage, provenance, consent,
  quality, support, and intended use.
- Constructed output requires accepted quality, passed negative-control gating, supported
  status, and no failing/non-evaluable diagnostic. Any failure abstains with no feature object.
- All seven uncertainty dimensions are explicit and non-estimable where this deterministic
  constructor has no fitted error model.

## Interfaces and evidence

The standalone `glio_proteogen.adapters.m1203` adapter exposes strict FastAPI construct,
verify, and schema routes plus Typer `export-schema`, `construct`, and `verify` commands.
Errors are sanitized and schema export refuses overwrite.

The executable evaluator fixture contains six scenarios: supported construction, failed
negative control, non-evaluable negative control, rejected quality, denied controls, and
deterministic replay. Release evidence is under `release-evidence/m12_03/`.
