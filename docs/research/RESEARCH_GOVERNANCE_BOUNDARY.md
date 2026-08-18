# Research/governed boundary

The executable spectrum-search and protein-group pipeline lives under
`glio_proteogen.research`. It is an additive research namespace: callers own
the mzML and FASTA bytes, the pipeline emits content-addressed evidence, and
the locked evaluator is research-use-only.

The frozen M03, M04, and M05 contracts remain separate. Their claim ceilings
intentionally exclude spectrum search, abundance estimation, peptide-to-protein
inference, proteoform/isoform inference, glioma biology, mechanism discovery,
and clinical or treatment claims. Governed source files and the shared FastAPI
and Typer adapters therefore have an executable import firewall against the
research namespace. The public app has no research execution route.

This is a safety boundary, not a claim that the research implementation is
clinically validated. Promotion into a governed module requires an owner-frozen
ABI, licensed raw/reference catalogue, search and quantification policy,
external validation cohorts, privacy/consent review, and an explicit replay and
safe-abstention contract. Until those artifacts exist, the research verifier
checks only locked computation identity, fixture/scenario inventory, package
reachability, and declared evidence—not biological truth.
