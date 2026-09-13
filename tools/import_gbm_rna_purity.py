# ruff: noqa: C901, S603, S607, T201, TRY003
"""Admit the pinned GBMPurity MLP without a runtime PyTorch dependency.

The upstream ``GBMPurity.pt`` file is a full-model PyTorch pickle.  This importer
never executes or unpickles it.  After validating the complete Git tree and every
tracked file against the pinned commit, it reads the six known float32 storage
members from the ZIP container and emits them as base64-encoded little-endian arrays
in canonical JSON.  The result contains model parameters, ordered genes, feature
lengths, preprocessing semantics, provenance, and the upstream MIT notice; it does
not contain source single-cell or pseudobulk training records.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import math
import struct
import subprocess
import zipfile
from pathlib import Path
from typing import Final

SOURCE_REPOSITORY: Final = "https://github.com/scmpht/GBMPurity.git"
SOURCE_COMMIT: Final = "af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950"
SCHEMA_VERSION: Final = "glio-proteogen.gbmpurity-mlp-artifact/1.0.0"
MODEL_ID: Final = "gbmpurity-primary-idhwt-rna/1.0.0"
EXPECTED_GENE_COUNT: Final = 5_829
ARCHIVE_PREFIX: Final = (
    "T200-MLP2h_testData_Adam_L1Loss_BS:64_LR:3e-05_WD:1e-05_DO:0.4_H1:(32, 16)_full-model/"
)

# The full tracked tree at SOURCE_COMMIT.  Checking the inventory as well as the
# bytes prevents a caller from silently substituting a partial source export.
EXPECTED_SOURCE_FILES: Final = {
    ".gitignore": (
        3_078,
        "eb8c46dc219f89675fbe859d5da7ea82d7ff20288a527c786e49bc652ba90138",
    ),
    "LICENSE": (
        1_084,
        "3f0041f0cfe77a6f4153e1465b1590b744102d9e8948203bcb56d9b244367ef7",
    ),
    "README.md": (
        4_206,
        "51c08a34e41197299e6300d06ca812e8bc3b5e51ad09cca218481f46c3844033",
    ),
    "environment.yml": (
        3_870,
        "c956fd2604c3002c12a888149c987aa6bb4cd612211daf0fb7dd87dcda13b973",
    ),
    "img/GBMPurity.png": (
        644_362,
        "de61264273dfeb18aa302b0e7fd3ed14ce1577c29fc588cee780c7a71f1a77f9",
    ),
    "model/GBMPurity.pt": (
        753_748,
        "80abd8d8f4875799f839701bec655d2e4753c750e63e60b9119b8b66342025c7",
    ),
    "model/input-genes-lengths.csv": (
        73_007,
        "de148837ab4d487b3fd86436f63e95b451fa4a305c5bf8d5eb094c117941884b",
    ),
    "src/GBMPurity.py": (
        4_850,
        "07b41deb3aa4906428782991bd29714c3977228b1a16519a60ade20480623465",
    ),
    "src/modelling/purity_dataset.py": (
        5_114,
        "69a3200387628bce0f2c89c97fe7ad17ff36e4e66de1c0833641660daa5476a4",
    ),
    "src/modelling/torch_models.py": (
        1_384,
        "b0a0b881a6ded3a45dd0e7d72175779cbbe539ce284e902fe794b4dde1801ea1",
    ),
    "src/modelling/trainGBMPurity.py": (
        4_871,
        "b6d354f0a3921a3bc7cf4aa0c77a3ae38ea581cd6b7f59f611258d438b71c40d",
    ),
    "src/utils.py": (
        2_055,
        "19507e44a78ca98c531da4387ce5cf9b4a3d7177627633f29f85a3a57d39fc5f",
    ),
}

EXPECTED_ARCHIVE_MEMBERS: Final = {
    "data.pkl": (1_938, "7f14da666424001c941eecbba5ba7e1fce1f7896d39962593778e3c63f54d8e9"),
    "byteorder": (6, "180ca01b95f0dfdd36fbb600e51cf6e46c8ef468de56b017847886fefaf7b6f9"),
    "data/0": (746_112, "75d1cd77369326ed152e5def5a2a7643da356f9092c40933a67b1dda815577b8"),
    "data/1": (128, "89fae2022379a78a5641252866c8820d5dced6bce0f6e1a82c2cd3959917fe41"),
    "data/2": (2_048, "8da207d35b8739586b0b3041ab3462e05b3c96c3f9fa268275f9f1253dfc4ad1"),
    "data/3": (64, "d00ea8fd87981bef2b1e71fe55c94c268f70c38d293669d348a75133f463be3b"),
    "data/4": (64, "f30aa3796d01f4ceda1d56b1ed1551faa063d7b2f23873e0c3fd722ace56b56c"),
    "data/5": (4, "698d5fd52b86dc47367c289654b4601e1e5be38a8f6f395f0656ab1f7790b30b"),
    "version": (2, "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2"),
    ".data/serialization_id": (
        40,
        "1f0a5c953d69bfac9863baba3fba92d88ce53ceca689d077fa7ba5cf56981ec8",
    ),
}

PARAMETER_STORAGES: Final = (
    ("fc1.weight", "data/0", (32, 5_829)),
    ("fc1.bias", "data/1", (32,)),
    ("fc2.weight", "data/2", (16, 32)),
    ("fc2.bias", "data/3", (16,)),
    ("out.weight", "data/4", (1, 16)),
    ("out.bias", "data/5", (1,)),
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_digest(value: object) -> str:
    return "sha256:" + _sha256_bytes(_canonical_bytes(value))


def _git(source_root: Path, *arguments: str) -> str:
    try:
        process = subprocess.run(
            ["git", "-C", str(source_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"unable to verify pinned source Git checkout: {error}") from error
    return process.stdout.strip()


def _verify_source_tree(source_root: Path) -> list[dict[str, object]]:
    if not source_root.is_dir():
        raise ValueError(f"source root is not a directory: {source_root}")
    head = _git(source_root, "rev-parse", "HEAD")
    if head != SOURCE_COMMIT:
        raise ValueError(f"source commit mismatch: expected {SOURCE_COMMIT}, got {head}")
    repository = _git(source_root, "config", "--get", "remote.origin.url")
    normalized_repository = repository.removesuffix("/").removesuffix(".git")
    if normalized_repository != SOURCE_REPOSITORY.removesuffix(".git"):
        raise ValueError(
            f"source repository mismatch: expected {SOURCE_REPOSITORY}, got {repository}"
        )
    tracked = tuple(
        line
        for line in _git(source_root, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
        if line
    )
    if set(tracked) != set(EXPECTED_SOURCE_FILES) or len(tracked) != len(EXPECTED_SOURCE_FILES):
        raise ValueError("tracked source inventory does not match the pinned commit")
    records: list[dict[str, object]] = []
    for relative_path in tracked:
        expected_bytes, expected_sha256 = EXPECTED_SOURCE_FILES[relative_path]
        path = source_root / Path(relative_path)
        if not path.is_file():
            raise ValueError(f"tracked source file is missing: {relative_path}")
        actual_bytes = path.stat().st_size
        actual_sha256 = _sha256_file(path)
        if actual_bytes != expected_bytes or actual_sha256 != expected_sha256:
            raise ValueError(
                f"source lock mismatch for {relative_path}: expected "
                f"{expected_bytes} bytes/{expected_sha256}, got "
                f"{actual_bytes} bytes/{actual_sha256}"
            )
        records.append(
            {
                "bytes": actual_bytes,
                "path": relative_path,
                "sha256": f"sha256:{actual_sha256}",
            }
        )
    return records


def _read_genes(path: Path) -> tuple[list[str], list[int]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["feature_name", "feature_length"]:
            raise ValueError("unexpected input-gene table header")
        rows = list(reader)
    if len(rows) != EXPECTED_GENE_COUNT:
        raise ValueError(f"expected {EXPECTED_GENE_COUNT} input genes, found {len(rows)}")
    names: list[str] = []
    lengths: list[int] = []
    for index, row in enumerate(rows):
        if set(row) != {"feature_name", "feature_length"}:
            raise ValueError(f"unexpected column in input-gene row {index + 2}")
        name = row["feature_name"]
        if not name or name != name.strip():
            raise ValueError(f"invalid feature name in input-gene row {index + 2}")
        try:
            length = int(row["feature_length"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid feature length in input-gene row {index + 2}") from error
        if length <= 0 or str(length) != row["feature_length"]:
            raise ValueError(f"non-canonical feature length in input-gene row {index + 2}")
        names.append(name)
        lengths.append(length)
    if len(names) != len(set(names)):
        raise ValueError("duplicate feature name in input-gene table")
    return names, lengths


def _validate_architecture_source(source_root: Path) -> None:
    architecture_text = (source_root / "src/modelling/torch_models.py").read_text(encoding="utf-8")
    inference_text = (source_root / "src/GBMPurity.py").read_text(encoding="utf-8")
    utility_text = (source_root / "src/utils.py").read_text(encoding="utf-8")
    required_architecture_fragments = (
        "class MLP2h(nn.Module):",
        "self.fc1 = nn.Linear(input_size, h1)",
        "self.fc2 = nn.Linear(h1, h2)",
        "self.out = nn.Linear(h2, 1)",
        "self.dropout = nn.Dropout(p_dropout)",
        "x = self.dropout(x)",
        "x = F.relu(x)",
    )
    required_inference_fragments = (
        "X = np.log2(tpm(data.values, lengths) + 1)",
        "model.eval()",
        ".flatten().clip(0, 1)",
        "if p_overlap < 0.8:",
    )
    required_utility_fragments = (
        "rpk = np.divide(X, lengths)",
        "scaling_factor = np.nansum(rpk, axis=1).reshape(-1, 1)",
        "tpm = (rpk / scaling_factor) * 1e4",
    )
    for label, text, fragments in (
        ("architecture", architecture_text, required_architecture_fragments),
        ("inference", inference_text, required_inference_fragments),
        ("preprocessing", utility_text, required_utility_fragments),
    ):
        missing = [fragment for fragment in fragments if fragment not in text]
        if missing:
            raise ValueError(f"pinned {label} source lacks expected semantics: {missing}")


def _read_parameters(model_path: Path) -> dict[str, dict[str, object]]:
    if not zipfile.is_zipfile(model_path):
        raise ValueError("pinned model is not the expected ZIP-format PyTorch archive")
    with zipfile.ZipFile(model_path) as archive:
        members = tuple(archive.namelist())
        expected_members = tuple(ARCHIVE_PREFIX + suffix for suffix in EXPECTED_ARCHIVE_MEMBERS)
        if members != expected_members:
            raise ValueError("PyTorch archive member inventory or order is unexpected")
        payloads: dict[str, bytes] = {}
        for suffix, (expected_bytes, expected_sha256) in EXPECTED_ARCHIVE_MEMBERS.items():
            member = ARCHIVE_PREFIX + suffix
            info = archive.getinfo(member)
            if info.file_size != expected_bytes:
                raise ValueError(f"unexpected uncompressed size for model member {suffix}")
            payload = archive.read(member)
            actual_sha256 = _sha256_bytes(payload)
            if actual_sha256 != expected_sha256:
                raise ValueError(f"SHA-256 mismatch for model member {suffix}")
            payloads[suffix] = payload
    if payloads["byteorder"] != b"little" or payloads["version"] != b"3\n":
        raise ValueError("unexpected PyTorch storage byte order or serialization version")
    pickle_payload = payloads["data.pkl"]
    required_pickle_markers = (
        b"torch_models\nMLP2h",
        b"torch.nn.modules.linear\nLinear",
        b"torch.nn.modules.dropout\nDropout",
        b"fc1",
        b"fc2",
        b"out",
    )
    if any(marker not in pickle_payload for marker in required_pickle_markers):
        raise ValueError("serialized model metadata does not identify the expected MLP2h graph")
    parameters: dict[str, dict[str, object]] = {}
    for parameter_name, storage_name, shape in PARAMETER_STORAGES:
        payload = payloads[storage_name]
        expected_size = math.prod(shape) * 4
        if len(payload) != expected_size:
            raise ValueError(f"unexpected storage size for {parameter_name}")
        values = struct.iter_unpack("<f", payload)
        if any(not math.isfinite(value[0]) for value in values):
            raise ValueError(f"non-finite model parameter in {parameter_name}")
        parameters[parameter_name] = {
            "data_base64": base64.b64encode(payload).decode("ascii"),
            "dtype": "<f4",
            "encoding": "base64",
            "sha256": f"sha256:{_sha256_bytes(payload)}",
            "shape": list(shape),
        }
    return parameters


def build_artifact(source_root: Path) -> dict[str, object]:
    """Validate the pinned checkout and return the canonical runtime artifact."""

    source_files = _verify_source_tree(source_root)
    _validate_architecture_source(source_root)
    feature_names, feature_lengths = _read_genes(source_root / "model/input-genes-lengths.csv")
    parameters = _read_parameters(source_root / "model/GBMPurity.pt")
    license_text = (source_root / "LICENSE").read_text(encoding="utf-8")
    if not license_text.startswith("MIT License\n"):
        raise ValueError("the pinned root license is not the expected MIT notice")
    artifact: dict[str, object] = {
        "architecture": {
            "dropout": {
                "active_during_inference": False,
                "location": "input",
                "probability": 0.4,
            },
            "layers": [
                {
                    "activation": "relu",
                    "bias": True,
                    "input_features": EXPECTED_GENE_COUNT,
                    "name": "fc1",
                    "output_features": 32,
                },
                {
                    "activation": "relu",
                    "bias": True,
                    "input_features": 32,
                    "name": "fc2",
                    "output_features": 16,
                },
                {
                    "activation": "identity_then_clip",
                    "bias": True,
                    "clip_interval": [0.0, 1.0],
                    "input_features": 16,
                    "name": "out",
                    "output_features": 1,
                },
            ],
            "source_class": "torch_models.MLP2h",
        },
        "input": {
            "feature_lengths": feature_lengths,
            "feature_names": feature_names,
            "gene_identifier": "exact case-sensitive source feature_name (HGNC-style symbol)",
            "minimum_gene_overlap_fraction": 0.8,
            "missing_gene_policy": "zero-fill only after the minimum overlap check passes",
            "required_feature_count": len(feature_names),
            "value_domain": "finite non-negative raw RNA-seq counts",
        },
        "feature_order_digest": _canonical_digest(feature_names),
        "model_id": MODEL_ID,
        "parameters": parameters,
        "preprocessing": {
            "formula": (
                "rpk=count/feature_length; scale=sum(rpk); source_scaled_tpm="
                "rpk/scale*1e4; transformed=log2(source_scaled_tpm+1)"
            ),
            "gene_order": "exact feature_names array order",
            "normalization": (
                "source scaled TPM (1e4 multiplier, intentionally 100x below conventional 1e6)"
            ),
            "output": "linear MLP output clipped to [0,1]",
        },
        "provenance": {
            "article": {
                "authors": "Thomas MPH, Ajaib S, Tanner G, Bulpitt AJ, Stead LF",
                "doi": "10.1093/neuonc/noaf026",
                "journal": "Neuro-Oncology 27(6):1458-1473 (2025)",
                "title": (
                    "GBMPurity: A machine learning tool for estimating glioblastoma "
                    "tumor purity from bulk RNA-sequencing data"
                ),
            },
            "intended_population": "primary IDH-wildtype glioblastoma bulk RNA-seq",
            "license": {
                "name": "MIT License",
                "spdx_id": "MIT",
                "text": license_text,
            },
            "repository": SOURCE_REPOSITORY,
            "source_commit": SOURCE_COMMIT,
            "training_summary": (
                "Upstream reports simulated pseudobulk tumours derived from the GBmap "
                "single-cell resource; no training records are included in this artifact."
            ),
            "transformation_notice": (
                "GLIO-PROTEOGEN converted the six exact pretrained PyTorch float32 "
                "storages and the ordered input-gene table into deterministic JSON. "
                "The converter does not execute the source pickle, retrain the model, "
                "or redistribute source single-cell/pseudobulk training records. This "
                "adaptation is not endorsed by the upstream authors."
            ),
            "upstream_disclaimer": (
                "Research use only; not for clinical decision making. The upstream "
                "authors state that the model is unsuitable outside its primary "
                "IDH-wildtype glioblastoma context."
            ),
        },
        "schema_version": SCHEMA_VERSION,
        "source": {
            "commit": SOURCE_COMMIT,
            "gene_table_path": "model/input-genes-lengths.csv",
            "gene_table_sha256": (
                "sha256:" + EXPECTED_SOURCE_FILES["model/input-genes-lengths.csv"][1]
            ),
            "license_path": "LICENSE",
            "license_sha256": "sha256:" + EXPECTED_SOURCE_FILES["LICENSE"][1],
            "license_spdx_id": "MIT",
            "model_path": "model/GBMPurity.pt",
            "model_sha256": "sha256:" + EXPECTED_SOURCE_FILES["model/GBMPurity.pt"][1],
            "repository": SOURCE_REPOSITORY,
        },
        "source_lock": {
            "archive_format": (
                "PyTorch ZIP serialization; pickle metadata was inspected but never executed"
            ),
            "files": source_files,
            "repository": SOURCE_REPOSITORY,
            "source_commit": SOURCE_COMMIT,
            "tracked_file_count": len(source_files),
        },
        "weight_tensor_digest": _canonical_digest(
            {name: tensor["sha256"] for name, tensor in parameters.items()}
        ),
    }
    artifact["content_digest_basis"] = (
        "SHA-256 of RFC-8259-compatible canonical JSON for all fields except content_digest; "
        "UTF-8, sorted keys, compact separators, no NaN"
    )
    artifact["content_digest"] = _canonical_digest(artifact)
    return artifact


def render_artifact(artifact: dict[str, object]) -> bytes:
    """Return compact deterministic JSON bytes with a trailing newline."""

    return _canonical_bytes(artifact) + b"\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert the pinned GBMPurity MLP into a NumPy-ready JSON artifact."
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help=f"Detached checkout of {SOURCE_REPOSITORY} at {SOURCE_COMMIT}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "src/glio_proteogen/research/gbm_rna_purity/data/gbm_purity_mlp.v1.json"
        ),
        help="Destination for the deterministic runtime artifact.",
    )
    arguments = parser.parse_args()
    artifact = build_artifact(arguments.source_root.resolve())
    output = arguments.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = render_artifact(artifact)
    output.write_bytes(payload)
    print(
        json.dumps(
            {
                "content_digest": artifact["content_digest"],
                "bytes": len(payload),
                "file_sha256": f"sha256:{_sha256_bytes(payload)}",
                "output": str(output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
