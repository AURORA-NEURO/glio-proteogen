# M03/M04 capability-boundary hardening

This isolated audit started from `6adfd9bf1c584bbfa0df3043eb25a9c098ae2f1d` on the integrated
M26 base. It does not change the M03/M04 scientific contracts or add inference. The only production
change seals the M03-08 and M04-08 release-plugin capabilities so a caller cannot forge a frozen
`Validated*Request` dataclass and pass the runtime `isinstance` check.

The token now carries a private issuance seal and is tracked in a weak registry with request identity
and canonical-request-digest checks. Valid typed and strict-JSON paths remain supported; copied,
wrong-seal, and post-issuance request-replacement tokens fail before service execution. This is an
ABI-preserving safety fix for the existing validate-then-run boundary.

Evidence:

- Curated M03/M04 safety selection: 180 passed, including all non-inference boundary tests and
  M03-08 contract/replay/coverage checks.
- Changed plugin coverage: 100% statements and 100% branches for both M03-08 and M04-08 plugins.
- Ruff and format clean; strict MyPy clean across all 3 changed Python files; compileall passed.
- Import sweep loaded 65 M03/M04 contract and module packages successfully.
- Two pinned wheel/sdist builds are byte-identical. The wheel is 3,663,728 bytes with SHA-256
  `6eba354d3ddf57a7dccdbca6e8d06eb2b867a5e20a363b341f64cbfdfde4d1d7`; the sdist is 4,201,439
  bytes with SHA-256 `071f3995c3eb47465bda9e57fa2600db08b5b61c9afa591ffa36796bf2caeb82`.
- Isolated wheel import resolved both M03-08 and M04-08 canonical digest APIs.

The Python delta against the requested authority base is +160/-6, net +154 lines across 3 files:
30/+30 production plugin lines (with 3 deletions each) and 100 regression-test lines. A broader
72-file lifecycle selection was started but stopped at 8% after approximately 20 minutes because
parameterization made it unbounded for this audit; it produced no failures before termination and
is not represented as a passing gate.
