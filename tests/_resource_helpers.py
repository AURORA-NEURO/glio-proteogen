"""Small helpers for resource-boundary tests."""

from __future__ import annotations

import ctypes
import os
from typing import TYPE_CHECKING, BinaryIO

if TYPE_CHECKING:
    from pathlib import Path

if os.name == "nt":
    import msvcrt
    from ctypes import wintypes


def _mark_windows_file_sparse(stream: BinaryIO) -> None:
    """Mark an open Windows file sparse before extending it past the ceiling."""

    if os.name != "nt":
        return

    returned = wintypes.DWORD()
    ok = ctypes.windll.kernel32.DeviceIoControl(  # type: ignore[attr-defined]
        wintypes.HANDLE(msvcrt.get_osfhandle(stream.fileno())),
        wintypes.DWORD(0x000900C4),
        None,
        0,
        None,
        0,
        ctypes.byref(returned),
        None,
    )
    if not ok:
        raise ctypes.WinError()


def write_sparse_oversized_json(path: Path, limit: int) -> None:
    """Create a limit-plus-one JSON-shaped file with negligible disk usage."""

    if limit < 1:
        raise ValueError
    with path.open("wb") as stream:
        stream.write(b"{")
        _mark_windows_file_sparse(stream)
        stream.seek(limit)
        stream.write(b"}")
