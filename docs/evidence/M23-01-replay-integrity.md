# M23-01 replay integrity

M23-01 replay now re-curates the bound variant-peptide reference-truth request
and compares the complete canonical result. Reference evidence, package
content, support, provenance, limitations, and status cannot be changed and
then made internally consistent by merely recomputing `result_digest`.

The module remains caller-declared benchmark material. It does not authenticate
source authority, inspect raw cohort data, infer variant-peptide biology, or
emit a biological conclusion. Replay mismatches remain fail-closed at the
service, API, CLI, and plugin boundaries.
