"""Source-lock and safe-conversion tests for the GBMPurity importer."""

from __future__ import annotations

import hashlib
import inspect
import json
import struct
import subprocess
import zipfile
from pathlib import Path

import pytest

from tools import import_gbm_rna_purity as importer

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
ARTIFACT_PATH = (
    REPOSITORY_ROOT
    / "src/glio_proteogen/research/gbm_rna_purity/data/gbm_purity_mlp.v1.json"
)
OPTIONAL_SOURCE_ROOT = WORKSPACE_ROOT / ".tmp-gbmpurity-source"
EXPECTED_FILE_SHA256 = "2999d845c602c7b8b44d45c37a7f43bea57ad6a930af12f9c7b56cc221ffccc2"
EXPECTED_CONTENT_DIGEST = (
    "sha256:651fa1ea9100650d8b34cec3c980624e42bada1ec3ff9cfe23fdf13049585722"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_archive(path: Path, payloads: dict[str, bytes], prefix: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for suffix, payload in payloads.items():
            archive.writestr(prefix + suffix, payload)


def _archive_payloads(*, parameter: bytes | None = None) -> dict[str, bytes]:
    metadata = b"|".join(
        (
            b"torch_models\nMLP2h",
            b"torch.nn.modules.linear\nLinear",
            b"torch.nn.modules.dropout\nDropout",
            b"fc1",
            b"fc2",
            b"out",
        )
    )
    return {
        "data.pkl": metadata,
        "byteorder": b"little",
        "data/0": parameter if parameter is not None else struct.pack("<f", 0.25),
        "version": b"3\n",
    }


def _bind_archive_contract(
    monkeypatch: pytest.MonkeyPatch,
    payloads: dict[str, bytes],
    *,
    prefix: str = "fixture/",
) -> None:
    monkeypatch.setattr(importer, "ARCHIVE_PREFIX", prefix)
    monkeypatch.setattr(
        importer,
        "EXPECTED_ARCHIVE_MEMBERS",
        {suffix: (len(payload), _sha256(payload)) for suffix, payload in payloads.items()},
    )
    monkeypatch.setattr(
        importer,
        "PARAMETER_STORAGES",
        (("out.bias", "data/0", (1,)),),
    )


def test_checked_in_artifact_is_canonical_and_fully_source_locked() -> None:
    payload = ARTIFACT_PATH.read_bytes()
    document = json.loads(payload)
    content = dict(document)
    declared = content.pop("content_digest")

    assert _sha256(payload) == EXPECTED_FILE_SHA256
    assert declared == EXPECTED_CONTENT_DIGEST
    assert importer._canonical_digest(content) == declared
    assert importer.render_artifact(document) == payload
    assert document["source"] == {
        "commit": importer.SOURCE_COMMIT,
        "gene_table_path": "model/input-genes-lengths.csv",
        "gene_table_sha256": (
            "sha256:" + importer.EXPECTED_SOURCE_FILES["model/input-genes-lengths.csv"][1]
        ),
        "license_path": "LICENSE",
        "license_sha256": "sha256:" + importer.EXPECTED_SOURCE_FILES["LICENSE"][1],
        "license_spdx_id": "MIT",
        "model_path": "model/GBMPurity.pt",
        "model_sha256": "sha256:" + importer.EXPECTED_SOURCE_FILES["model/GBMPurity.pt"][1],
        "repository": importer.SOURCE_REPOSITORY,
    }
    source_lock = document["source_lock"]
    assert source_lock["tracked_file_count"] == len(importer.EXPECTED_SOURCE_FILES) == 12
    assert {record["path"] for record in source_lock["files"]} == set(
        importer.EXPECTED_SOURCE_FILES
    )
    assert document["input"]["required_feature_count"] == importer.EXPECTED_GENE_COUNT
    assert document["provenance"]["license"]["spdx_id"] == "MIT"


def test_importer_never_executes_the_pytorch_pickle() -> None:
    source = inspect.getsource(importer._read_parameters)
    assert "pickle.loads" not in source
    assert "torch.load" not in source
    assert "eval(" not in source
    assert "exec(" not in source
    assert "zipfile.ZipFile" in source


@pytest.mark.skipif(
    not OPTIONAL_SOURCE_ROOT.is_dir(),
    reason="the pinned upstream checkout is not distributed with package tests",
)
def test_optional_pinned_checkout_reproduces_the_exact_runtime_artifact() -> None:
    rebuilt = importer.build_artifact(OPTIONAL_SOURCE_ROOT)
    assert importer.render_artifact(rebuilt) == ARTIFACT_PATH.read_bytes()


def test_gene_table_parser_accepts_only_exact_unique_canonical_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(importer, "EXPECTED_GENE_COUNT", 2)
    valid = tmp_path / "valid.csv"
    valid.write_text("feature_name,feature_length\nEGFR,1000\nPTEN,2000\n", encoding="utf-8")
    assert importer._read_genes(valid) == (["EGFR", "PTEN"], [1000, 2000])

    cases = (
        ("wrong,length\nEGFR,1\nPTEN,2\n", "header"),
        ("feature_name,feature_length\nEGFR,1\n", "expected 2"),
        ("feature_name,feature_length\n EGFR,1\nPTEN,2\n", "feature name"),
        ("feature_name,feature_length\nEGFR,1.0\nPTEN,2\n", "feature length"),
        ("feature_name,feature_length\nEGFR,0\nPTEN,2\n", "non-canonical"),
        ("feature_name,feature_length\nEGFR,1\nEGFR,2\n", "duplicate"),
        ("feature_name,feature_length,extra\nEGFR,1,x\nPTEN,2,y\n", "header"),
    )
    for index, (contents, message) in enumerate(cases):
        path = tmp_path / f"invalid-{index}.csv"
        path.write_text(contents, encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            importer._read_genes(path)


def test_source_tree_rejects_missing_checkout_git_failure_commit_and_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="not a directory"):
        importer._verify_source_tree(tmp_path / "absent")

    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired("git", 30)

    monkeypatch.setattr(subprocess, "run", fail_run)
    with pytest.raises(ValueError, match="unable to verify"):
        importer._git(tmp_path, "rev-parse", "HEAD")

    with monkeypatch.context() as context:
        context.setattr(importer, "_git", lambda *_args: "wrong-commit")
        with pytest.raises(ValueError, match="source commit mismatch"):
            importer._verify_source_tree(tmp_path)

    def wrong_repository(_root: Path, *arguments: str) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return importer.SOURCE_COMMIT
        return "https://example.invalid/substitute"

    with monkeypatch.context() as context:
        context.setattr(importer, "_git", wrong_repository)
        with pytest.raises(ValueError, match="source repository mismatch"):
            importer._verify_source_tree(tmp_path)


def test_source_tree_checks_inventory_and_every_file_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locked = {"LICENSE": (3, _sha256(b"MIT"))}
    monkeypatch.setattr(importer, "EXPECTED_SOURCE_FILES", locked)

    def git_response(_root: Path, *arguments: str) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return importer.SOURCE_COMMIT
        if arguments == ("config", "--get", "remote.origin.url"):
            return importer.SOURCE_REPOSITORY
        return "EXTRA"

    monkeypatch.setattr(importer, "_git", git_response)
    with pytest.raises(ValueError, match="inventory"):
        importer._verify_source_tree(tmp_path)

    (tmp_path / "LICENSE").write_bytes(b"bad")

    def locked_inventory(_root: Path, *arguments: str) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return importer.SOURCE_COMMIT
        if arguments == ("config", "--get", "remote.origin.url"):
            return importer.SOURCE_REPOSITORY
        return "LICENSE"

    monkeypatch.setattr(importer, "_git", locked_inventory)
    with pytest.raises(ValueError, match="source lock mismatch"):
        importer._verify_source_tree(tmp_path)

    (tmp_path / "LICENSE").write_bytes(b"MIT")
    assert importer._verify_source_tree(tmp_path) == [
        {"bytes": 3, "path": "LICENSE", "sha256": "sha256:" + _sha256(b"MIT")}
    ]


def test_architecture_source_requires_exact_preprocessing_and_eval_semantics(
    tmp_path: Path,
) -> None:
    modelling = tmp_path / "src/modelling"
    modelling.mkdir(parents=True)
    architecture = (
        "class MLP2h(nn.Module):\n"
        "self.fc1 = nn.Linear(input_size, h1)\n"
        "self.fc2 = nn.Linear(h1, h2)\n"
        "self.out = nn.Linear(h2, 1)\n"
        "self.dropout = nn.Dropout(p_dropout)\n"
        "x = self.dropout(x)\n"
        "x = F.relu(x)\n"
    )
    inference = (
        "X = np.log2(tpm(data.values, lengths) + 1)\n"
        "model.eval()\n"
        ".flatten().clip(0, 1)\n"
        "if p_overlap < 0.8:\n"
    )
    utility = (
        "rpk = np.divide(X, lengths)\n"
        "scaling_factor = np.nansum(rpk, axis=1).reshape(-1, 1)\n"
        "tpm = (rpk / scaling_factor) * 1e4\n"
    )
    (modelling / "torch_models.py").write_text(architecture, encoding="utf-8")
    (tmp_path / "src/GBMPurity.py").write_text(inference, encoding="utf-8")
    (tmp_path / "src/utils.py").write_text(utility, encoding="utf-8")
    importer._validate_architecture_source(tmp_path)

    (tmp_path / "src/utils.py").write_text("substituted", encoding="utf-8")
    with pytest.raises(ValueError, match="preprocessing source lacks expected semantics"):
        importer._validate_architecture_source(tmp_path)


def test_parameter_reader_extracts_locked_float32_without_pickle_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = _archive_payloads()
    _bind_archive_contract(monkeypatch, payloads)
    archive_path = tmp_path / "model.pt"
    _write_archive(archive_path, payloads, "fixture/")

    parameters = importer._read_parameters(archive_path)
    assert parameters["out.bias"]["shape"] == [1]
    assert parameters["out.bias"]["dtype"] == "<f4"
    assert parameters["out.bias"]["sha256"] == "sha256:" + _sha256(payloads["data/0"])


def test_parameter_reader_rejects_nonarchive_inventory_hash_metadata_and_nonfinite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nonarchive = tmp_path / "not-model.pt"
    nonarchive.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="ZIP-format"):
        importer._read_parameters(nonarchive)

    payloads = _archive_payloads()
    _bind_archive_contract(monkeypatch, payloads)
    missing = tmp_path / "missing.pt"
    _write_archive(
        missing,
        {key: value for key, value in payloads.items() if key != "version"},
        "fixture/",
    )
    with pytest.raises(ValueError, match="inventory or order"):
        importer._read_parameters(missing)

    corrupt = dict(payloads)
    corrupt["data/0"] = struct.pack("<f", 0.5)
    corrupt_path = tmp_path / "corrupt.pt"
    _write_archive(corrupt_path, corrupt, "fixture/")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        importer._read_parameters(corrupt_path)

    bad_metadata = dict(payloads)
    bad_metadata["data.pkl"] = b"substituted"
    _bind_archive_contract(monkeypatch, bad_metadata)
    bad_metadata_path = tmp_path / "bad-metadata.pt"
    _write_archive(bad_metadata_path, bad_metadata, "fixture/")
    with pytest.raises(ValueError, match="expected MLP2h graph"):
        importer._read_parameters(bad_metadata_path)

    nonfinite = _archive_payloads(parameter=struct.pack("<f", float("nan")))
    _bind_archive_contract(monkeypatch, nonfinite)
    nonfinite_path = tmp_path / "nonfinite.pt"
    _write_archive(nonfinite_path, nonfinite, "fixture/")
    with pytest.raises(ValueError, match="non-finite model parameter"):
        importer._read_parameters(nonfinite_path)


def test_canonical_importer_encoding_rejects_nonfinite_extensions() -> None:
    assert importer._canonical_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    with pytest.raises(ValueError, match="Out of range float values"):
        importer._canonical_bytes({"bad": float("inf")})
