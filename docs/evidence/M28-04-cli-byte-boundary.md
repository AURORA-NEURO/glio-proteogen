# M28-04 CLI byte boundary

The M28-04 Typer gateway now applies the same canonical request/result byte
ceilings before parsing files from disk. It checks file size before reading and
again after the read to cover a concurrent file-growth race. Requests remain
bounded at 4 MiB and results at 8 MiB; error output stays sanitized and the
gateway ABI, replay identity, and provisional scientific claim ceiling are
unchanged.
