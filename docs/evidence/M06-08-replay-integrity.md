# M06-08 replay-integrity closure

M06-08 is a provisional evidence/explanation publisher beneath the
protein-abundance boundary. Its current-main replay audit found that the
public `replay=False` keyword allowed a receipt-only verification path: a
caller could mutate the abstention explanation, recompute `result_digest`, and
still pass `M0608Service.verify` without deterministic reconstruction.

The compatibility keyword is retained, but it no longer weakens verification.
Every service and plugin verification now validates the canonical envelope,
recomputes the embedded request digest, reconstructs the result from that
request, and compares the complete canonical result. The dedicated CLI now
exposes the same `verify` operation, while the FastAPI route already shares
the service seam. This closes the service/plugin/API/CLI parity gap without
changing the provisional request or result schema.

Adversarial coverage includes an outer-digest-repaired abstention mutation
through the service with `replay=False`, plugin verification with the same
flag, API tamper rejection, and CLI round-trip plus forged-result rejection.
The evaluator records the new
`self_rehashed_receipt_rejected_even_when_replay_disabled` check. No protein
abundance, proteoform, identity, consent, kinase, all-omics, or treatment
claim is emitted; abstention remains the only publication status.

Authority remains dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, slice
`GLIO-PROTEOGEN_240_Module_Dossier.md:2144-2184`; the ABI is
`0.1.0-provisional` and still requires owner confirmation.
