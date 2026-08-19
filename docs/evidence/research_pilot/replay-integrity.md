# Research pilot replay-integrity evidence

This additive research-only hardening closes a receipt projection gap in the
public-proteomics pilot. The previous digest projection retained only a subset
of each `Psm` and did not retain the `PilotLimits` resource policy. A caller
could therefore mutate matched intensity, fragment/precursor error, collision
state, or the search-resource ceiling while keeping the visible digest and
passing replay comparison.

The pilot now binds the complete scored-PSM projection and all four bounded
resource limits into `PilotResult.as_dict()` and its result digest. The change
does not promote the pilot into a governed ABI and does not add biological,
clinical, disease, abundance, or mechanistic claims.

Adversarial coverage verifies that replay rejects:

- a self-rehashed result whose PSM measurement/error/collision fields changed;
- a replay request with changed spectrum/PSM resource ceilings even when the
  observed PSM output is otherwise identical.

The canonical replay remains a full offline rerun over the caller-supplied
metadata, FASTA, and mzML bytes.
