# M25-06 robustness and OOD challenge

Status: provisional contract hardening; owner confirmation remains required.

M25-06 is the caller-declared robustness and out-of-domain challenge boundary
beneath proteotype. It consumes a provisional M25-05 result reference, a locked
challenge configuration, and explicit perturbation scenarios. It records
operational challenge observations and safe unsupported abstentions; it does
not infer proteotype biology or convert an unsupported perturbation into a
negative finding.

The evaluated result is closed against the exact request: its robustness
surface must retain the request's scenario declarations and locked
configuration byte-for-byte (as typed values). This prevents a self-rehashed
result from silently replacing the challenge perturbation or OOD threshold
after request validation. The surface still retains typed observations,
scenario references, OOD bands, disposition, evidence, uncertainty,
limitations, and seven-control provenance.

The ABI remains `0.1.0-provisional`; no production endpoint, owner approval,
or scientific calibration claim is made here.
