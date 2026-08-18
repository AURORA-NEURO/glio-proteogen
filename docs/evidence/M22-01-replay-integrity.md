# M22-01 replay integrity

M22-01 replay now re-curates the bound protein-RNA discordance reference-truth
request and compares the complete canonical result. A caller cannot alter
reference evidence, package content, support, provenance, or limitations and
make the forged object valid by recomputing `result_digest`.

The module remains a caller-declared reference-truth curator. It does not
authenticate source authority, inspect raw cohort material, infer discordance
biology, or emit a biological conclusion. Replay mismatches remain fail-closed
across service, API, CLI, and plugin boundaries.
