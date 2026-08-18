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

The wheel is 3,857,112 bytes with SHA-256
`864e44692be5a52692abf4df331f14bd60b0cca45ea8ceead66f518097b48ff5` and
1,990 members. The source distribution is 4,505,464 bytes with SHA-256
`a038a8e2836d3d4b9e0e5b8ed6b9201bd0909df57d87c1b3179a8697c78548db`.
The wheel was installed into an isolated target and imported successfully;
the release verifier passed.
