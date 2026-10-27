"""Synthetic progress IO: narrow Windows retries, cancellation and exact bytes."""

from __future__ import annotations

import ctypes
import errno
import os
import threading
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.cptac_gbm_census_execution import progress

PAYLOAD = canonical_json_bytes({"phase": "source_fitting", "source_attempted": 3})
OLD = canonical_json_bytes({"phase": "source_admission", "source_attempted": 0})


def _permission(winerror, *, error_number=errno.EACCES):
    error = PermissionError(error_number, "synthetic-private-replacement", "private-test-path")
    error.winerror = winerror
    return error


def _pretend_windows(monkeypatch):
    monkeypatch.setattr(progress, "_WINDOWS", True)


def _clock(monkeypatch):
    current, waits = [0.0], []

    def sleep(delay):
        waits.append(delay)
        current[0] += delay

    monkeypatch.setattr(progress.time, "monotonic", lambda: current[0])
    monkeypatch.setattr(progress.time, "sleep", sleep)
    return current, waits


def _blocked(monkeypatch, *, error=None):
    calls = []
    failure = _permission(5) if error is None else error

    def replace(source, target):
        calls.append((source, target))
        raise failure

    monkeypatch.setattr(Path, "replace", replace)
    return calls, failure


def test_defaults_are_finite_typed_and_immutable():
    assert progress.ProgressRetryPolicy(2.0, 101, 0.02) == progress.DEFAULT_POLICY
    assert progress.MAX_PROGRESS_BYTES == 65_536
    assert {5, 32, 33} == progress.RETRYABLE_WINERRORS
    with pytest.raises(FrozenInstanceError):
        progress.DEFAULT_POLICY.max_attempts = 1


@pytest.mark.parametrize(
    "changes",
    [
        {"max_wait_seconds": True},
        {"max_wait_seconds": 1},
        {"max_wait_seconds": float("nan")},
        {"max_wait_seconds": float("inf")},
        {"max_wait_seconds": -0.01},
        {"max_wait_seconds": 2.01},
        {"max_attempts": True},
        {"max_attempts": 1.0},
        {"max_attempts": 0},
        {"max_attempts": 102},
        {"retry_interval_seconds": 0},
        {"retry_interval_seconds": False},
        {"retry_interval_seconds": 0.0},
        {"retry_interval_seconds": float("nan")},
        {"retry_interval_seconds": float("inf")},
        {"retry_interval_seconds": -0.01},
        {"retry_interval_seconds": 0.021},
    ],
)
def test_policy_rejects_nonfinite_coerced_and_wider_limits(changes):
    with pytest.raises(ValueError, match="policy"):
        progress.ProgressRetryPolicy(**changes)


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("code", [None, True, 5.0, 2, 3, 5, 17, 32, 33, 87, 112])
def test_error_classification_requires_every_windows_condition(monkeypatch, windows, code):
    monkeypatch.setattr(progress, "_WINDOWS", windows)
    expected = windows and type(code) is int and code in {5, 32, 33}
    assert progress._is_retryable_replacement(_permission(code)) is expected
    assert not progress._is_retryable_replacement(_permission(code, error_number=errno.EINVAL))
    assert not progress._is_retryable_replacement(FileNotFoundError("synthetic"))


def test_success_publishes_exact_payload_without_telemetry_or_pending_file(tmp_path):
    (tmp_path / "progress.json").write_bytes(OLD)
    assert progress.write_progress_snapshot(tmp_path, PAYLOAD) is None
    assert (tmp_path / "progress.json").read_bytes() == PAYLOAD
    assert not (tmp_path / "progress.json.tmp").exists()


@pytest.mark.parametrize("code", [5, 32, 33])
def test_retry_uses_one_exclusive_write_and_same_immutable_payload(monkeypatch, tmp_path, code):
    _pretend_windows(monkeypatch)
    _clock(monkeypatch)
    (tmp_path / "progress.json").write_bytes(OLD)
    original_open, original_replace = Path.open, Path.replace
    writes, snapshots = [], []

    def open_path(path, *args, **kwargs):
        if args and args[0] == "xb":
            writes.append(path)
        return original_open(path, *args, **kwargs)

    def replace(source, target):
        metadata = source.stat()
        snapshots.append(
            (metadata.st_ino, metadata.st_size, metadata.st_mtime_ns, source.read_bytes())
        )
        assert (tmp_path / "progress.json").read_bytes() == OLD
        if len(snapshots) <= 3:
            raise _permission(code)
        return original_replace(source, target)

    monkeypatch.setattr(Path, "open", open_path)
    monkeypatch.setattr(Path, "replace", replace)
    progress.write_progress_snapshot(tmp_path, PAYLOAD)
    assert writes == [tmp_path / "progress.json.tmp"]
    assert len(snapshots) == 4 and len(set(snapshots)) == 1
    assert snapshots[0][-1] == PAYLOAD
    assert (tmp_path / "progress.json").read_bytes() == PAYLOAD


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("synthetic"),
        FileExistsError("synthetic"),
        OSError(errno.ENOSPC, "synthetic"),
        PermissionError(errno.EACCES, "synthetic"),
        _permission(87),
        ValueError("synthetic"),
        KeyboardInterrupt(),
    ],
)
def test_unexpected_replacement_errors_propagate_unchanged_without_retry(
    monkeypatch, tmp_path, failure
):
    _pretend_windows(monkeypatch)
    calls, _ = _blocked(monkeypatch, error=failure)
    with pytest.raises(type(failure)) as caught:
        progress.write_progress_snapshot(tmp_path, PAYLOAD)
    assert caught.value is failure and len(calls) == 1
    assert (tmp_path / "progress.json.tmp").read_bytes() == PAYLOAD


def test_nonwindows_permission_error_is_never_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(progress, "_WINDOWS", False)
    calls, failure = _blocked(monkeypatch)
    with pytest.raises(PermissionError) as caught:
        progress.write_progress_snapshot(tmp_path, PAYLOAD)
    assert caught.value is failure and len(calls) == 1


def test_exclusive_write_failure_stays_outside_retry_catch(monkeypatch, tmp_path):
    _pretend_windows(monkeypatch)
    calls, _ = _blocked(monkeypatch)
    failure = _permission(5)

    def fail_open(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(Path, "open", fail_open)
    with pytest.raises(PermissionError) as caught:
        progress.write_progress_snapshot(tmp_path, PAYLOAD)
    assert caught.value is failure and calls == []


def test_existing_pending_file_is_preserved_without_implicit_resume(monkeypatch, tmp_path):
    (tmp_path / "progress.json").write_bytes(OLD)
    (tmp_path / "progress.json.tmp").write_bytes(b"prior incomplete payload")
    calls, _ = _blocked(monkeypatch)
    with pytest.raises(FileExistsError):
        progress.write_progress_snapshot(tmp_path, PAYLOAD)
    assert calls == []
    assert (tmp_path / "progress.json").read_bytes() == OLD
    assert (tmp_path / "progress.json.tmp").read_bytes() == b"prior incomplete payload"


def test_monotonic_deadline_bounds_waits_and_retains_old_and_pending_bytes(monkeypatch, tmp_path):
    _pretend_windows(monkeypatch)
    current, waits = _clock(monkeypatch)
    calls, _ = _blocked(monkeypatch)
    (tmp_path / "progress.json").write_bytes(OLD)
    policy = progress.ProgressRetryPolicy(max_wait_seconds=0.05)
    with pytest.raises(progress.ProgressReplacementExhaustedError) as caught:
        progress.write_progress_snapshot(tmp_path, PAYLOAD, policy=policy)
    assert current == [0.05] and len(calls) == 3
    assert waits == [0.02, 0.02, 0.05 - 0.04]
    assert (tmp_path / "progress.json").read_bytes() == OLD
    assert (tmp_path / "progress.json.tmp").read_bytes() == PAYLOAD
    assert "private" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_attempt_cap_is_independent_of_clock_progress(monkeypatch, tmp_path):
    _pretend_windows(monkeypatch)
    monkeypatch.setattr(progress.time, "monotonic", lambda: 0.0)
    waits = []
    monkeypatch.setattr(progress.time, "sleep", waits.append)
    calls, _ = _blocked(monkeypatch)
    with pytest.raises(progress.ProgressReplacementExhaustedError):
        progress.write_progress_snapshot(
            tmp_path, PAYLOAD, policy=progress.ProgressRetryPolicy(max_attempts=3)
        )
    assert len(calls) == 3 and waits == [0.02, 0.02]


def test_zero_wait_permits_one_initial_attempt_and_no_sleep(monkeypatch, tmp_path):
    _pretend_windows(monkeypatch)
    _, waits = _clock(monkeypatch)
    calls, _ = _blocked(monkeypatch)
    with pytest.raises(progress.ProgressReplacementExhaustedError):
        progress.write_progress_snapshot(
            tmp_path, PAYLOAD, policy=progress.ProgressRetryPolicy(max_wait_seconds=0.0)
        )
    assert len(calls) == 1 and waits == []


@pytest.mark.parametrize("cancel_at", [1, 2, 3, 4])
def test_cancellation_propagates_outside_retry_catch_at_every_boundary(
    monkeypatch, tmp_path, cancel_at
):
    _pretend_windows(monkeypatch)
    _clock(monkeypatch)
    calls, _ = _blocked(monkeypatch)
    events, interruption = [], _permission(5)
    (tmp_path / "progress.json").write_bytes(OLD)

    def cancel():
        events.append(1)
        if len(events) == cancel_at:
            raise interruption

    with pytest.raises(PermissionError) as caught:
        progress.write_progress_snapshot(tmp_path, PAYLOAD, cancel=cancel)
    assert caught.value is interruption
    assert len(calls) == (0 if cancel_at <= 2 else 1)
    assert (tmp_path / "progress.json").read_bytes() == OLD
    assert (tmp_path / "progress.json.tmp").exists() == (cancel_at > 1)


@pytest.mark.parametrize("stage", ["privacy", "canonical"])
def test_caller_validation_errors_happen_before_write_and_never_enter_retry(
    monkeypatch, tmp_path, stage
):
    calls, _ = _blocked(monkeypatch)

    def guarded_publish(state):
        if "values" in state:
            raise ValueError
        payload = canonical_json_bytes(state)
        progress.write_progress_snapshot(tmp_path, payload)

    with pytest.raises(ValueError):
        guarded_publish({"values": [1, 2]} if stage == "privacy" else {"count": float("nan")})
    assert calls == [] and not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "argument", ["output", "payload_type", "empty", "oversized", "policy", "cancel"]
)
def test_invalid_public_arguments_fail_before_filesystem_mutation(tmp_path, argument):
    output, payload, kwargs = tmp_path, PAYLOAD, {}
    if argument == "output":
        output = str(tmp_path)
    elif argument == "payload_type":
        payload = bytearray(PAYLOAD)
    elif argument == "empty":
        payload = b""
    elif argument == "oversized":
        payload = b"x" * (progress.MAX_PROGRESS_BYTES + 1)
    elif argument == "policy":
        kwargs["policy"] = object()
    else:
        kwargs["cancel"] = False
    with pytest.raises(ValueError):
        progress.write_progress_snapshot(output, payload, **kwargs)
    assert not list(tmp_path.iterdir())


def test_payload_size_bound_is_inclusive(tmp_path):
    payload = canonical_json_bytes(
        {"padding": "x" * (progress.MAX_PROGRESS_BYTES - len(b'{"padding":""}'))}
    )
    assert len(payload) == progress.MAX_PROGRESS_BYTES
    progress.write_progress_snapshot(tmp_path, payload)
    assert (tmp_path / "progress.json").read_bytes() == payload


@contextmanager
def _native_held_reader(path, *, allow_delete):
    """Own one native handle; close once even when a timer and finally both run."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = (wintypes.HANDLE,), wintypes.BOOL
    kernel.GetHandleInformation.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetHandleInformation.restype = wintypes.BOOL
    handle = kernel.CreateFileW(
        str(path), 0x80000000, 1 | 2 | (4 if allow_delete else 0), None, 3, 0x80, None
    )
    assert handle != ctypes.c_void_p(-1).value
    flags, lock, closed = wintypes.DWORD(), threading.Lock(), threading.Event()
    assert kernel.GetHandleInformation(handle, ctypes.byref(flags))

    def close():
        with lock:
            if not closed.is_set():
                assert kernel.CloseHandle(handle)
                closed.set()

    try:
        yield close, closed
    finally:
        close()
        assert closed.is_set()
        ctypes.set_last_error(0)
        assert not kernel.GetHandleInformation(handle, ctypes.byref(flags))
        assert ctypes.get_last_error() == 6


@pytest.mark.skipif(os.name != "nt", reason="native Windows reader-handle integration")
@pytest.mark.parametrize("allow_delete", [False, True])
def test_native_windows_reader_release_allows_identical_pending_payload(
    monkeypatch, tmp_path, allow_delete
):
    (tmp_path / "progress.json").write_bytes(OLD)
    replace = Path.replace
    failures = []

    def observed(source, target):
        assert source.read_bytes() == PAYLOAD
        try:
            return replace(source, target)
        except OSError as error:
            failures.append(error)
            raise

    monkeypatch.setattr(Path, "replace", observed)
    with _native_held_reader(tmp_path / "progress.json", allow_delete=allow_delete) as (
        close,
        closed,
    ):
        timer = threading.Timer(0.10, close)
        timer.start()
        try:
            progress.write_progress_snapshot(tmp_path, PAYLOAD)
        finally:
            timer.join(timeout=1)
            assert not timer.is_alive()
        assert closed.is_set()
    if not allow_delete:
        assert failures
    assert all(progress._is_retryable_replacement(error) for error in failures)
    assert (tmp_path / "progress.json").read_bytes() == PAYLOAD
    assert not (tmp_path / "progress.json.tmp").exists()


@pytest.mark.skipif(os.name != "nt", reason="native Windows reader-handle integration")
def test_native_windows_forever_held_reader_exhausts_and_keeps_evidence(tmp_path):
    (tmp_path / "progress.json").write_bytes(OLD)
    policy = progress.ProgressRetryPolicy(max_wait_seconds=0.08, retry_interval_seconds=0.01)
    with _native_held_reader(tmp_path / "progress.json", allow_delete=False):
        with pytest.raises(progress.ProgressReplacementExhaustedError):
            progress.write_progress_snapshot(tmp_path, PAYLOAD, policy=policy)
        assert (tmp_path / "progress.json").read_bytes() == OLD
        assert (tmp_path / "progress.json.tmp").read_bytes() == PAYLOAD
    with pytest.raises(FileExistsError):
        progress.write_progress_snapshot(tmp_path, PAYLOAD)
