# M21-07 release evidence

This directory records the frozen evaluator, locked benchmark, scoped branch
coverage, package hashes, and release-verifier result for the provisional
M21-07 lane. Authority is dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, slice
`GLIO-PROTEOGEN_240_Module_Dossier.md:7500-7540`.

The branch is stacked on current main, which contains the published M21-06
lane at `4b63f55aa14f1905283dde9c6f09e6395e0c1f17`; all generated build,
installation, and coverage working directories are removed after evidence
collection.

Replay evidence includes a self-rehashed output matrix. Verification does not
trust a result digest alone: it validates the envelope, regenerates from the
bound request, and compares the complete canonical result.

The wheel is 2,700,583 bytes with SHA-256
`29bea142bac71ddf74ec88ca9f30a6b4961c7cc3da44615318f98daeb4026210` and
1,433 members. The source distribution is 3,206,047 bytes with SHA-256
`f0ac4d24d7d61df89612f27a9458e3dfd43c5f2afb44ed8ab3a06d66b040b293`.
The wheel was installed into an isolated target and imported successfully;
the release verifier passed.
