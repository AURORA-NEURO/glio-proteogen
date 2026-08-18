# M12 adapter file-resource boundaries

The standalone M12 adapters now enforce the byte ceilings already declared by
their provisional contracts on CLI request and result files. Before this
change, M12-01 through M12-08 used `Path.read_bytes()` (or an equivalent
unbounded path read), allocating the complete file before strict JSON
validation. M12-03 also reread its result file during verification.

All eight adapters now use the shared `read_bounded` helper before parsing:

| adapters | request ceiling | result ceiling |
| --- | ---: | ---: |
| M12-01 through M12-08 | 4 MiB | 8 MiB |

The change preserves schemas, operation names, media types, replay digests,
and the provisional ABI. It only closes the path-based allocation bypass,
passes the declared result ceiling to CLI replay readers, and makes M12-03
result verification consume one bounded byte snapshot.

`tests/interfaces/test_m12_adapter_resource_limits.py` covers every M12
request reader, every result-reader path, rejection before parsing, and a
`Path.read_bytes` firewall. It uses small synthetic overflow files with
patched limits so the regression suite does not allocate multi-megabyte test
fixtures.
