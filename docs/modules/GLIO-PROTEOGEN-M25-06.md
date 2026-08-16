# GLIO-PROTEOGEN-M25-06 robustness, shift and OOD challenge engine

M25-06 is a provisional, metadata-only robustness challenge engine beneath
`Uncertainty/stability/abstention`. Its dossier authority is SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `GLIO-PROTEOGEN_240_Module_Dossier.md:8833-8875`.

The implementation evaluates the eight locked challenge kinds: missing data,
low input, corruption, batch shift, platform shift, site shift, artifact, and
novel state. It emits only a robustness surface, OOD score, safe-failure
report, typed uncertainty, support status, provenance, evidence, and
limitations. It never emits a proteotype estimate, kinase activity, generic
all-omics fusion, treatment recommendation, identity inference, or negative
finding from unsupported evidence.

The sole declared upstream boundary is M25-04 caller-declared media
(`application/vnd.glio-proteogen.m25-04+json`); M25-06 does not import or
traverse an unpublished upstream service. Seven-control preflight is fail
closed. Unsupported or reviewer-required challenge declarations abstain with
an explicit safe-failure report. Request/result IDs and digests are canonical,
and FastAPI, Typer, and the strict parse-once plugin share the same contract.

Release evidence is frozen under `release-evidence/m25_06/` and independently
checked by `tools/verify_m2506_release.py`.
