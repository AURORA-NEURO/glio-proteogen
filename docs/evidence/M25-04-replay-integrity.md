# M25-04 replay integrity

An evaluated M25-04 result now binds its transport report validations,
evaluations, and configuration exactly to the request declarations before the
result digest is checked. Replacing transport evidence or calibration
configuration and recomputing `result_digest` therefore fails strict result
validation.

The request also binds its execution-context identifier and retains every
declared proteome, genome/transcriptome, PTM, and benchmark artifact by the
complete identity tuple `(artifact_id, version, digest, media_type)`. This is
an ABI-neutral provenance boundary: M25-04 remains caller-declared and does
not authenticate issuer authority or infer biological transport.
