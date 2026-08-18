# C10 file-resource boundary evidence

The C10 path-based adapters now enforce the byte ceilings already declared by
the provisional M10 contracts before JSON parsing or model validation:

- M10-01 request files: 4 MiB;
- M10-02 request files: 4 MiB;
- M10-03 request files: 4 MiB;
- M10-07 request files: 4 MiB;
- M10-07 result and canonical replay files: 8 MiB.

The adapters use the shared `read_bounded` helper, which reads at most
`max_bytes + 1` bytes and rejects an oversized file before strict JSON parsing.
This closes the allocation/parsing bypass caused by direct `Path.read_bytes()`
calls. It does not change request or result schemas, operation names, media
types, replay digests, or the provisional ABI.

The boundary regression suite checks both source-level closure for all four
adapters and runtime rejection of oversized request/result files:
`tests/test_c10_file_boundaries.py`.
