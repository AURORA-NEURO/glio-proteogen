"""Private directory admission must precede every descendant creation."""

# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import run_gbmap_hierarchy_tasks as runner


def _fake_info(info, **changes):
    values = {
        "st_mode": info.st_mode,
        "st_dev": info.st_dev,
        "st_ino": info.st_ino,
        "st_file_attributes": getattr(info, "st_file_attributes", 0),
    }
    return SimpleNamespace(**{**values, **changes})


def test_nested_ordinary_directories_are_checked_root_to_leaf_then_created_one_at_a_time(
    tmp_path, monkeypatch
):
    output = tmp_path / "ordinary" / "nested" / "run"
    existing = tuple(reversed((tmp_path, *tmp_path.parents)))
    inspected = []
    created = []
    original_lstat, original_mkdir = os.lstat, Path.mkdir

    def inspect(path, *args, **kwargs):
        inspected.append(Path(path))
        return original_lstat(path, *args, **kwargs)

    def create(path, *args, **kwargs):
        assert inspected[: len(existing)] == list(existing)
        assert not kwargs.get("parents", False)
        assert path.parent.is_dir()
        created.append(path)
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(runner.os, "lstat", inspect)
    monkeypatch.setattr(Path, "mkdir", create)
    assert runner._inspect_private_directory(output) == output
    assert created == [tmp_path / "ordinary", tmp_path / "ordinary" / "nested", output]
    assert output.is_dir()


def test_existing_ordinary_directory_is_idempotent_without_a_mkdir_attempt(tmp_path, monkeypatch):
    output = tmp_path / "existing"
    output.mkdir()

    def forbidden(*_args, **_kwargs):
        pytest.fail("existing ordinary directories must not be recreated")

    monkeypatch.setattr(Path, "mkdir", forbidden)
    assert runner._inspect_private_directory(output) == output


@pytest.mark.parametrize("kind", ["symlink", "reparse", "non_directory"])
@pytest.mark.parametrize("at_leaf", [False, True])
def test_rejected_existing_ancestor_never_attempts_to_create_descendants(
    tmp_path, monkeypatch, kind, *, at_leaf
):
    ancestor = tmp_path / "rejected"
    ancestor.mkdir()
    output = ancestor if at_leaf else ancestor / "must-not-exist" / "run"
    observed = ancestor.lstat()
    rejected = {
        "symlink": _fake_info(observed, st_mode=stat.S_IFLNK | 0o777),
        "reparse": _fake_info(observed, st_file_attributes=runner.fit_driver._REPARSE_ATTRIBUTE),
        "non_directory": _fake_info(observed, st_mode=stat.S_IFREG | 0o600),
    }[kind]
    original_lstat = os.lstat
    attempts = []

    def inspect(path, *args, **kwargs):
        if Path(path) == ancestor:
            return rejected
        return original_lstat(path, *args, **kwargs)

    def forbidden(path, *_args, **_kwargs):
        attempts.append(path)
        pytest.fail("unsafe existing ancestors must be rejected before mkdir")

    monkeypatch.setattr(runner.os, "lstat", inspect)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError, match="ordinary non-reparse"):
        runner._inspect_private_directory(output)
    assert attempts == []
    assert not (ancestor / "must-not-exist").exists()


def test_actual_symlink_cannot_create_a_child_in_its_target(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("native symlink unavailable; mocked link/reparse cases remain mandatory")
    with pytest.raises(runner.GbmapHierarchyTaskDriverError, match="ordinary non-reparse"):
        runner._inspect_private_directory(link / "never-created" / "run")
    assert tuple(target.iterdir()) == ()


def test_actual_non_directory_ancestor_is_rejected_without_a_mkdir_attempt(tmp_path, monkeypatch):
    ancestor = tmp_path / "ordinary-file"
    original = b"existing synthetic bytes"
    ancestor.write_bytes(original)

    def forbidden(*_args, **_kwargs):
        pytest.fail("ordinary file ancestor must be identified before mkdir")

    monkeypatch.setattr(Path, "mkdir", forbidden)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError, match="ordinary non-reparse"):
        runner._inspect_private_directory(ancestor / "run")
    assert ancestor.read_bytes() == original


@pytest.mark.parametrize("relative", [Path("new"), Path("nested") / ".." / "new", Path()])
def test_repository_containment_is_rejected_before_lstat_or_mkdir(tmp_path, monkeypatch, relative):
    repository = tmp_path / "repository"
    repository.mkdir()
    monkeypatch.setattr(runner.fit_driver, "_REPOSITORY_ROOT", repository)

    def forbidden(*_args, **_kwargs):
        pytest.fail("repository containment must precede directory inspection and creation")

    monkeypatch.setattr(runner.os, "lstat", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError, match="outside the repository"):
        runner._inspect_private_directory(repository / relative)
    assert tuple(repository.iterdir()) == ()


def test_relative_paths_are_lexically_normalized_before_creation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner._inspect_private_directory(Path("uncreated") / ".." / "run" / "nested")
    assert result == tmp_path / "run" / "nested"
    assert result.is_absolute()
    assert result.is_dir()
    assert not (tmp_path / "uncreated").exists()


@pytest.mark.parametrize("value", [None, "private-run", 3])
def test_non_path_input_fails_before_normalization_or_io(monkeypatch, value):
    def forbidden(*_args, **_kwargs):
        pytest.fail("path type must be checked first")

    monkeypatch.setattr(runner.fit_driver, "_lexical_absolute", forbidden)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError, match="pathlib Path"):
        runner._inspect_private_directory(value)


@pytest.mark.parametrize("phase", ["normalization", "inspection", "creation"])
def test_operational_failures_are_sanitized_and_do_not_create_children(
    tmp_path, monkeypatch, phase
):
    output = tmp_path / "must-not-exist" / "run"
    sentinel = "SYNTHETIC_PRIVATE_PATH"

    def fail(*_args, **_kwargs):
        raise PermissionError(sentinel)

    if phase == "normalization":
        monkeypatch.setattr(runner.fit_driver, "_lexical_absolute", fail)
    elif phase == "inspection":
        monkeypatch.setattr(runner.os, "lstat", fail)
    else:
        monkeypatch.setattr(Path, "mkdir", fail)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError) as failure:
        runner._inspect_private_directory(output)
    assert sentinel not in str(failure.value)
    assert failure.value.__suppress_context__ is True
    assert not output.parent.exists()


@pytest.mark.parametrize("change", ["reparse", "identity", "non_directory"])
def test_existing_ancestor_change_is_detected_before_the_first_mkdir(tmp_path, monkeypatch, change):
    output = tmp_path / "must-not-exist" / "run"
    original_lstat = os.lstat
    observed = tmp_path.lstat()
    changed = {
        "reparse": _fake_info(observed, st_file_attributes=runner.fit_driver._REPARSE_ATTRIBUTE),
        "identity": _fake_info(observed, st_ino=observed.st_ino + 1),
        "non_directory": _fake_info(observed, st_mode=stat.S_IFREG | 0o600),
    }[change]
    visits = 0

    def inspect(path, *args, **kwargs):
        nonlocal visits
        if Path(path) == tmp_path:
            visits += 1
            if visits >= 2:
                return changed
        return original_lstat(path, *args, **kwargs)

    def forbidden(*_args, **_kwargs):
        pytest.fail("changed ancestors must fail before creation")

    monkeypatch.setattr(runner.os, "lstat", inspect)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError, match="ancestors changed"):
        runner._inspect_private_directory(output)
    assert not output.parent.exists()


def test_new_component_reparse_race_is_rejected_before_creating_its_child(tmp_path, monkeypatch):
    first = tmp_path / "first"
    output = first / "never-created"
    original_mkdir, original_lstat = Path.mkdir, os.lstat
    created = []

    def create(path, *args, **kwargs):
        created.append(path)
        return original_mkdir(path, *args, **kwargs)

    def inspect(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if Path(path) == first and first in created:
            return _fake_info(info, st_file_attributes=runner.fit_driver._REPARSE_ATTRIBUTE)
        return info

    monkeypatch.setattr(Path, "mkdir", create)
    monkeypatch.setattr(runner.os, "lstat", inspect)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError, match="ordinary non-reparse"):
        runner._inspect_private_directory(output)
    assert created == [first]
    assert not output.exists()


def test_unavailable_filesystem_root_is_not_created(tmp_path, monkeypatch):
    output = tmp_path / "new"

    def absent(*_args, **_kwargs):
        raise FileNotFoundError("synthetic unavailable root")

    def forbidden(*_args, **_kwargs):
        pytest.fail("an unverified filesystem root must never be created")

    monkeypatch.setattr(runner.os, "lstat", absent)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError, match="root is unavailable"):
        runner._inspect_private_directory(output)
