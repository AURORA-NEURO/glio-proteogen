"""Closed private input configuration; metadata-only source-lock boundaries."""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import replace

import pytest

from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock
from glio_proteogen.research.cptac_gbm_rna_purity_admission import inputs as boundary
from glio_proteogen.research.cptac_gbm_rna_purity_admission.contracts import AdmissionError


def _document():
    return {
        "schema_version": "cptac-gbm-rna-purity-inputs/1.0.0",
        "discovery": {
            "choices_path": "metadata/choices.private.json",
            "choices_sha256": "1" * 64,
            "map_bindings_path": "metadata/map.private.json",
            "map_bindings_sha256": "2" * 64,
            "files_manifest_path": "measurements/manifest.private.json",
            "files_manifest_sha256": "3" * 64,
        },
        "hgnc_path": "references/hgnc.tsv",
        "context_evidence": None,
        "context_sources": [],
    }


def _declaration(path="clinical/source.txt", payload=b"synthetic reviewed source"):
    return {
        "path": path,
        "bytes": len(payload),
        "md5": hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _save(tmp_path, document=None, *, payload=None):
    path = tmp_path / "input.private.json"
    if payload is None:
        payload = json.dumps(_document() if document is None else document).encode()
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def _load(tmp_path, document=None, *, payload=None):
    path, checksum = _save(tmp_path, document, payload=payload)
    return boundary.load_inputs(path, sha256=checksum)


def test_config_reads_only_its_metadata_not_declared_sources(tmp_path):
    result = _load(tmp_path)
    assert all(not path.exists() for path in result.input_paths)
    assert result.choices_path == tmp_path / "metadata/choices.private.json"
    assert result.hgnc_path == tmp_path / "references/hgnc.tsv"
    assert result.context_evidence is None and result.context_sources == ()
    assert "metadata" not in repr(result) and "hgnc" not in repr(result)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(result)


def test_context_locks_are_private_and_do_not_open_clinical_files(tmp_path):
    document = _document()
    document["context_evidence"] = _declaration("clinical/evidence.private.json")
    document["context_sources"] = [_declaration()]
    result = _load(tmp_path, document)
    assert result.context_evidence is not None and len(result.context_sources) == 1
    assert not result.context_sources[0].path.exists()
    assert "clinical" not in repr(result.context_sources[0])
    with pytest.raises(TypeError):
        pickle.dumps(result.context_sources[0])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(extra=True),
        lambda d: d.pop("hgnc_path"),
        lambda d: d.update(schema_version="foreign/1.0.0"),
        lambda d: d.update(discovery=[]),
        lambda d: d["discovery"].update(extra="synthetic-private-canary"),
        lambda d: d["discovery"].pop("choices_sha256"),
        lambda d: d["discovery"].update(choices_sha256="sha256:" + "1" * 64),
        lambda d: d["discovery"].update(map_bindings_sha256="A" * 64),
        lambda d: d["discovery"].update(files_manifest_sha256=True),
        lambda d: d.update(context_sources={}),
        lambda d: d.update(context_sources=[_declaration()]),
        lambda d: d.update(context_evidence={}),
        lambda d: d.update(context_evidence={**_declaration(), "extra": "private"}),
        lambda d: d.update(context_evidence={**_declaration(), "bytes": True}),
        lambda d: d.update(context_evidence={**_declaration(), "bytes": 0}),
        lambda d: d.update(context_evidence={**_declaration(), "bytes": 2**31}),
        lambda d: d.update(context_evidence={**_declaration(), "md5": "A" * 32}),
        lambda d: d.update(context_evidence={**_declaration(), "sha256": "sha256:" + "1" * 64}),
        lambda d: d.update(context_evidence=_declaration(), context_sources=[_declaration()] * 2),
        lambda d: d.update(context_evidence=_declaration(), context_sources=[_declaration()] * 257),
    ],
)
def test_closed_config_and_bounded_locks_reject_without_echo(tmp_path, mutation):
    document = _document()
    mutation(document)
    with pytest.raises(AdmissionError) as error:
        _load(tmp_path, document)
    assert "synthetic-private-canary" not in str(error.value)
    assert str(tmp_path) not in str(error.value)


@pytest.mark.parametrize(
    "path", ["", "../outside.tsv", "https://example.invalid/input", "bad\x00path", "bad\npath"]
)
def test_relative_escape_remote_and_control_paths_are_rejected(tmp_path, path):
    document = _document()
    document["hgnc_path"] = path
    with pytest.raises(AdmissionError):
        _load(tmp_path, document)


@pytest.mark.parametrize("outside", [False, True])
def test_explicit_local_absolute_paths_are_integrity_bound_not_forced_to_config_root(
    tmp_path, outside
):
    document = _document()
    expected = (tmp_path.parent if outside else tmp_path) / "hgnc.tsv"
    document["hgnc_path"] = str(expected)
    assert _load(tmp_path, document).hgnc_path == expected


@pytest.mark.parametrize(
    "payload",
    [
        b"[]",
        b"null",
        b"\xff",
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":1,"x":2}',
        b'{"x":1.5}',
        b'{"x":"escaped\\nprivate"}',
        b" " * 2_000_001,
    ],
    ids=[
        "array",
        "null",
        "invalid-utf8",
        "nan",
        "infinity",
        "duplicate",
        "float",
        "control",
        "oversize",
    ],
)
def test_config_json_is_strict_and_bounded_with_fresh_checksum(tmp_path, payload):
    with pytest.raises(AdmissionError):
        _load(tmp_path, payload=payload)


def test_duplicate_required_field_is_rejected_in_otherwise_valid_config(tmp_path):
    encoded = json.dumps(_document()).encode()
    payload = encoded[:-1] + b',"hgnc_path":"references/hgnc.tsv"}'
    with pytest.raises(AdmissionError):
        _load(tmp_path, payload=payload)


@pytest.mark.parametrize("checksum", ["0" * 64, "sha256:" + "0" * 64, "A" * 64, True])
def test_config_checksum_matches_the_exact_metadata_bytes(tmp_path, checksum):
    path, _ = _save(tmp_path)
    with pytest.raises(AdmissionError):
        boundary.load_inputs(path, sha256=checksum)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("choices_path", "not-a-Path"),
        ("context_evidence", "synthetic-private-canary"),
        ("context_evidence", object()),
        ("context_sources", [object()]),
        ("context_sources", (object(),)),
        ("choices_sha256", None),
    ],
)
def test_direct_private_inputs_reject_wrong_types_before_path_dereference(tmp_path, field, value):
    original = _load(tmp_path)
    with pytest.raises(AdmissionError) as error:
        replace(original, **{field: value})
    assert "synthetic-private-canary" not in str(error.value)


@pytest.mark.parametrize("field", ["path", "lock"])
def test_locked_input_requires_path_and_exact_lock(tmp_path, field):
    values = {"path": tmp_path / "source", "lock": SourceLock(1, "0" * 32, "0" * 64)}
    values[field] = "bad"
    with pytest.raises(AdmissionError):
        boundary.LockedInput(**values)


def test_context_sources_cannot_exist_without_evidence(tmp_path):
    original = _load(tmp_path)
    source = boundary.LockedInput(tmp_path / "source", SourceLock(1, "0" * 32, "0" * 64))
    with pytest.raises(AdmissionError):
        replace(original, context_sources=(source,))
