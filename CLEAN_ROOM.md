# Clean-room construction record

This repository began with an empty Git history and an empty source tree. Its implementation
is derived from the GLIO-PROTEOGEN 240-module dossier and independently written contracts,
algorithms, tests, and documentation. No source code, tests, branches, patches, or generated
artifacts from an earlier GLIO-PROTEOGEN repository may be inspected or reused.

## Permitted inputs

- the GLIO-PROTEOGEN 240-module dossier supplied as the functional specification;
- public standards and primary technical documentation referenced for a module;
- synthetic, non-clinical fixtures created specifically for this repository;
- independently derived algorithms and interfaces whose provenance is recorded here.

## Prohibited inputs

- code or repository history from any previous GLIO-PROTEOGEN implementation;
- copied tests, fixtures, schemas, prompts, generated artifacts, or implementation notes from
  such a repository;
- patient data, production credentials, or unapproved clinical artifacts.

If a contributor is exposed to a prohibited implementation source, they must stop work on the
affected module and ask the maintainers to reassign or independently re-derive it. Similarity to
an earlier implementation is not used as an acceptance criterion; conformance to the dossier and
the locked evidence gate is.

## Module evidence rule

A module is complete only when its versioned contract, implementation, synthetic fixtures,
negative and property cases, policy checks, integration tests, microbenchmarks, traceability,
recovery behavior, and reproducibility evidence all pass. Later modules consume only published
contracts and content-addressed outputs, never another module's private implementation.
