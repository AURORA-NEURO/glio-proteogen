# M24-07 replay integrity

M24-07 replay now re-evaluates the bound operational request and compares the
complete canonical result. Changes to the human-factors report, evidence,
support decision, provenance, limitations, or status cannot be made valid by
recomputing `result_digest`.

The evaluator remains a caller-declared operational assessment. It does not
emit a biomarker panel, subtype, treatment recommendation, kinase activity,
identity inference, consent inference, or biological conclusion. Replay
mismatches remain fail-closed across service, API, CLI, and plugin seams.
