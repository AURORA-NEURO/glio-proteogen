# ruff: noqa: ANN401, B905, C901, PLC0415, PLR0915, PLR2004, PLW3301, SIM117, T201, TC003, TRY003
"""Rebuild the pinned Diamandis Lab GBM proteomic-axis model artifact.

This is a maintainer tool, not a runtime dependency.  The upstream models were
serialized by an old R/xgboost release.  Rebuilding therefore deliberately uses
R only to unpack the R object and xgboost 1.4.2 only to decode its legacy binary
trees.  The emitted artifact is evaluated at runtime with NumPy alone.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SOURCE_REPOSITORY = "https://github.com/diamandis-lab/paper-prot-atlas-gbm"
SOURCE_COMMIT = "8d8c5725a82ef9505562e25fe2c5ea19fe608195"
RAW_BASE = f"https://raw.githubusercontent.com/diamandis-lab/paper-prot-atlas-gbm/{SOURCE_COMMIT}"
PAPER_TITLE = (
    "Topographic mapping of the glioblastoma proteome reveals a triple-axis model "
    "of intra-tumoral heterogeneity"
)
PAPER_DOI = "10.1038/s41467-021-27667-w"
PAPER_URL = "https://www.nature.com/articles/s41467-021-27667-w"

SELECTED_SIGNATURES = (
    "SWEET_KRAS_TARGETS_UP",
    "HALLMARK_MYC_TARGETS_V1",
    "WINTER_HYPOXIA_UP",
    "VERHAAK_GLIOBLASTOMA_MESENCHYMAL",
    "VERHAAK_GLIOBLASTOMA_NEURAL",
    "VERHAAK_GLIOBLASTOMA_PRONEURAL",
    "EGFR_UP.V1_UP",
)

SOURCE_FILES = {
    "LICENSE": (
        "LICENSE",
        "150f17448621b4c79dee5b975fc08f235eb09e4de6d5dff54a1a24854d9d482c",
    ),
    "predict_script": (
        "R/predictXGB.R",
        "f41614ac5a18e237e87a0f52159711c2be8fc39434f44a7a6ae3d994b0cbee1d",
    ),
    "protein_models": (
        "data/list_xgb-gbm_64_signatures-prot-v01.RData",
        "56aee53d2b247bb5dbaec7f876c0574ac0f89eccd98eade8f9437e1f1684a76c",
    ),
    "sample_proteomics": (
        "sample/sample_prot.rds",
        "7ab1a95f3f7d9e5afd5dd2710a3dcdd02dcc3df599c6f1f7d7b277ccf1311c62",
    ),
    "sample_expected": (
        "sample/predictXGB_sample_prot.csv",
        "bac5226c212d5ded43d88b8ef4abb3ebc140793486a1e82a817a8c031401906d",
    ),
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _download_sources(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, Path] = {}
    for logical_name, (relative_path, expected_digest) in SOURCE_FILES.items():
        destination = directory / Path(relative_path).name
        if not destination.exists():
            request = urllib.request.Request(  # noqa: S310 - pinned HTTPS origin and digest
                f"{RAW_BASE}/{relative_path}",
                headers={"User-Agent": "glio-proteogen-model-importer/1.0"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                destination.write_bytes(response.read())
        actual_digest = _sha256(destination.read_bytes())
        if actual_digest != expected_digest:
            raise RuntimeError(
                f"digest mismatch for {relative_path}: {actual_digest} != {expected_digest}"
            )
        resolved[logical_name] = destination
    return resolved


def _r_string(value: str) -> str:
    return '"' + value.replace("\\", "/").replace('"', '\\"') + '"'


def _extract_r_objects(sources: Mapping[str, Path], workspace: Path, rscript: str) -> None:
    signatures = ",".join(_r_string(name) for name in SELECTED_SIGNATURES)
    script = f"""
load({_r_string(str(sources['protein_models']))})
selected <- c({signatures})
if (!all(selected %in% names(list.xgb))) stop("selected model absent from pinned RData")
for (model_name in selected) {{
  model <- list.xgb[[model_name]]
  writeBin(model$raw, file.path({_r_string(str(workspace))}, paste0(model_name, ".bin")))
  writeLines(model$feature_names,
             file.path({_r_string(str(workspace))}, paste0(model_name, ".features.txt")),
             useBytes=TRUE)
}}
sample_data <- readRDS({_r_string(str(sources['sample_proteomics']))})
write.csv(data.frame(GENE_SYMBOL=rownames(sample_data), sample_data),
          file.path({_r_string(str(workspace))}, "sample_prot.csv"),
          row.names=FALSE, quote=FALSE)
"""
    script_path = workspace / "extract_models.R"
    script_path.write_text(script, encoding="utf-8")
    subprocess.run([rscript, str(script_path)], check=True)  # noqa: S603


def _expected_rows(path: Path) -> dict[str, list[float]]:
    lines = [
        line
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if not line.lstrip('"').startswith("#")
    ]
    rows: dict[str, list[float]] = {}
    for row in csv.DictReader(lines):
        name = row["GENESET"]
        if name in SELECTED_SIGNATURES:
            rows[name] = [float(row[f"sample_{index}"]) for index in range(1, 5)]
    if set(rows) != set(SELECTED_SIGNATURES):
        raise RuntimeError(
            "the pinned expected-output CSV does not contain every selected signature"
        )
    return rows


def _load_sample(path: Path) -> tuple[list[str], list[list[float]]]:
    by_sample: list[list[float]] = [[], [], [], []]
    names: list[str] = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            names.append(row["GENE_SYMBOL"])
            for index, values in enumerate(by_sample, start=1):
                values.append(float(row[f"sample_{index}"]))
    return names, by_sample


def _scale_sample(values: Sequence[float]) -> tuple[list[float], float, float]:
    positive = [value for value in values if value != 0.0]
    geometric_mean = math.exp(math.fsum(math.log(value) for value in positive) / len(positive))
    factor = 1.0e7 / geometric_mean
    return [value * factor for value in values], geometric_mean, factor


def _leaf_for_node(node: Mapping[str, Any], node_id: int) -> float:
    for child in node["children"]:
        if int(child["nodeid"]) == node_id:
            if set(child) - {"nodeid", "leaf", "cover"}:
                raise RuntimeError("selected model contains a tree deeper than one split")
            return float(child["leaf"])
    raise RuntimeError(f"tree child {node_id} was not found")


def _decode_stumps(booster: Any, feature_index: Mapping[str, int]) -> dict[str, list[Any]]:
    arrays: dict[str, list[Any]] = {
        "split_feature": [],
        "split_condition": [],
        "yes_leaf": [],
        "no_leaf": [],
        "missing_leaf": [],
    }
    for raw_tree in booster.get_dump(dump_format="json"):
        tree = json.loads(raw_tree)
        if "leaf" in tree:
            leaf = float(tree["leaf"])
            arrays["split_feature"].append(-1)
            arrays["split_condition"].append(0.0)
            arrays["yes_leaf"].append(leaf)
            arrays["no_leaf"].append(leaf)
            arrays["missing_leaf"].append(leaf)
            continue
        if len(tree.get("children", ())) != 2:
            raise RuntimeError("selected model contains a non-stump tree")
        split_name = str(tree["split"])
        arrays["split_feature"].append(feature_index[split_name])
        arrays["split_condition"].append(float(tree["split_condition"]))
        arrays["yes_leaf"].append(_leaf_for_node(tree, int(tree["yes"])))
        arrays["no_leaf"].append(_leaf_for_node(tree, int(tree["no"])))
        arrays["missing_leaf"].append(_leaf_for_node(tree, int(tree["missing"])))
    return arrays


def _evaluate_stumps(model: Mapping[str, Any], vector: Any, np: Any) -> float:
    margin = np.float32(model["base_score"])
    for feature, threshold, yes_leaf, no_leaf in zip(
        model["split_feature"],
        model["split_condition"],
        model["yes_leaf"],
        model["no_leaf"],
    ):
        if feature == -1:
            leaf = yes_leaf
        else:
            leaf = yes_leaf if np.float32(vector[feature]) < np.float32(threshold) else no_leaf
        margin = np.float32(margin + np.float32(leaf))
    return float(margin)


def _legacy_convert(workspace: Path, output: Path, fixture_output: Path) -> None:
    import numpy as np
    import xgboost as xgb  # type: ignore[import-not-found]

    expected = _expected_rows(workspace / SOURCE_FILES["sample_expected"][0].split("/")[-1])
    sample_names, sample_columns = _load_sample(workspace / "sample_prot.csv")
    sample_index = {name: index for index, name in enumerate(sample_names)}

    common_features: list[str] | None = None
    models: dict[str, dict[str, Any]] = {}
    legacy_predictions: dict[str, list[float]] = {}
    pure_predictions: dict[str, list[float]] = {}
    maximum_legacy_error = 0.0
    maximum_published_error = 0.0

    for signature_name in SELECTED_SIGNATURES:
        raw_path = workspace / f"{signature_name}.bin"
        feature_path = workspace / f"{signature_name}.features.txt"
        wrapper = raw_path.read_bytes()
        binary = wrapper[wrapper.index(b"binf") :]
        features = feature_path.read_text(encoding="utf-8").splitlines()
        if common_features is None:
            common_features = features
        elif features != common_features:
            raise RuntimeError("selected signatures do not share an identical feature universe")
        if features != sorted(features) or len(features) != len(set(features)):
            raise RuntimeError("model feature universe is not sorted and unique")

        booster = xgb.Booster(model_file=bytearray(binary))
        booster.feature_names = features
        configuration = json.loads(booster.save_config())
        model_parameters = configuration["learner"]["learner_model_param"]
        if configuration["learner"]["objective"]["name"] != "reg:squarederror":
            raise RuntimeError("unexpected upstream XGBoost objective")
        feature_index = {name: index for index, name in enumerate(features)}
        arrays = _decode_stumps(booster, feature_index)
        if len(arrays["split_feature"]) != 600:
            raise RuntimeError("unexpected upstream tree count")

        model = {
            "base_score": float(model_parameters["base_score"]),
            "output_offset": 10.0,
            "source_r_raw_sha256": _sha256(wrapper),
            "source_xgboost_binary_sha256": _sha256(binary),
            **arrays,
        }
        matrices: list[list[float]] = []
        for column in sample_columns:
            scaled, _, _ = _scale_sample(column)
            matrices.append([scaled[sample_index[name]] for name in features])
        matrix = np.asarray(matrices, dtype=np.float64)
        legacy = [
            float(value)
            for value in booster.predict(xgb.DMatrix(matrix, feature_names=features)).tolist()
        ]
        pure = [_evaluate_stumps(model, row, np) for row in matrix]
        maximum_legacy_error = max(
            maximum_legacy_error,
            max(abs(left - right) for left, right in zip(legacy, pure)),
        )
        published = [round(value - 10.0, 4) for value in pure]
        maximum_published_error = max(
            maximum_published_error,
            max(abs(left - right) for left, right in zip(published, expected[signature_name])),
        )
        legacy_predictions[signature_name] = legacy
        pure_predictions[signature_name] = pure
        models[signature_name] = model

    if common_features is None:
        raise RuntimeError("no models were converted")
    if maximum_legacy_error > 2.0e-5:
        raise RuntimeError(f"pure stump evaluator diverged from xgboost: {maximum_legacy_error}")
    if maximum_published_error != 0.0:
        raise RuntimeError(f"published sample oracle mismatch: {maximum_published_error}")

    source = {
        logical_name: {
            "path": relative_path,
            "sha256": digest,
        }
        for logical_name, (relative_path, digest) in SOURCE_FILES.items()
    }
    artifact = {
        "schema_version": "glio-gbm-proteomic-axes-artifact/1.0.0",
        "source": {
            "paper": {"title": PAPER_TITLE, "doi": PAPER_DOI, "url": PAPER_URL},
            "repository": SOURCE_REPOSITORY,
            "commit": SOURCE_COMMIT,
            "license_spdx": "MIT",
            "selection": {
                "scope": "seven_glioma_domain_signatures",
                "names": list(SELECTED_SIGNATURES),
            },
            "files": source,
        },
        "conversion": {
            "legacy_xgboost_version": xgb.__version__,
            "numpy_version": np.__version__,
            "tree_representation": "ordered_depth_one_stumps_float32_accumulation",
        },
        "normalization": {
            "input": "positive_linear_LFQ",
            "geometric_mean_target": 1.0e7,
            "zero_policy": "exclude_from_geometric_mean",
            "missing_model_feature_policy": "fill_with_zero",
            "output_offset": 10.0,
            "published_decimal_places": 4,
        },
        "feature_names": common_features,
        "models": models,
        "oracle": {
            "sample_names": [f"sample_{index}" for index in range(1, 5)],
            "expected_published_scores": expected,
            "legacy_raw_margins": legacy_predictions,
            "pure_raw_margins": pure_predictions,
            "maximum_absolute_error_vs_xgboost_1_4_2": maximum_legacy_error,
            "maximum_published_score_error": maximum_published_error,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_canonical_json(artifact))

    fixture = {
        "schema_version": "glio-gbm-proteomic-axes-oracle-input/1.0.0",
        "source_rds_sha256": SOURCE_FILES["sample_proteomics"][1],
        "gene_symbols": sample_names,
        "samples": {
            f"sample_{index}": values for index, values in enumerate(sample_columns, start=1)
        },
    }
    fixture_output.parent.mkdir(parents=True, exist_ok=True)
    with fixture_output.open("wb") as raw_stream:
        with gzip.GzipFile(fileobj=raw_stream, mode="wb", mtime=0) as stream:
            stream.write(_canonical_json(fixture))

    report = {
        "artifact": str(output),
        "artifact_sha256": _sha256(output.read_bytes()),
        "fixture": str(fixture_output),
        "fixture_sha256": _sha256(fixture_output.read_bytes()),
        "feature_count": len(common_features),
        "signature_count": len(models),
        "trees_per_signature": sorted({len(model["split_feature"]) for model in models.values()}),
        "max_abs_error_vs_legacy": maximum_legacy_error,
        "max_published_error": maximum_published_error,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


def _build(output: Path, fixture_output: Path, source_dir: Path | None, rscript: str) -> None:
    with tempfile.TemporaryDirectory(prefix="glio-gbm-model-import-") as temporary:
        workspace = Path(temporary)
        sources = _download_sources(source_dir or workspace / "sources")
        for source in sources.values():
            if source.parent != workspace:
                shutil.copy2(source, workspace / source.name)
        workspace_sources = {name: workspace / path.name for name, path in sources.items()}
        _extract_r_objects(workspace_sources, workspace, rscript)

        uv = shutil.which("uv")
        if uv is None:
            raise RuntimeError("uv is required to instantiate the pinned legacy converter")
        command = [
            uv,
            "run",
            "--no-project",
            "--python",
            "3.9",
            "--with",
            "numpy==1.26.4",
            "--with",
            "xgboost==1.4.2",
            "python",
            str(Path(__file__).resolve()),
            "--legacy-convert",
            "--workspace",
            str(workspace),
            "--output",
            str(output.resolve()),
            "--fixture-output",
            str(fixture_output.resolve()),
        ]
        subprocess.run(command, check=True)  # noqa: S603
        shutil.copyfile(
            workspace_sources["LICENSE"],
            output.parent / "DIAMANDIS-LAB-LICENSE.txt",
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    data = root / "src" / "glio_proteogen" / "research" / "gbm_proteomic_axes" / "data"
    parser.add_argument(
        "--output",
        type=Path,
        default=data / "diamandis_gbm_proteomic_axes_v1.json",
    )
    parser.add_argument(
        "--fixture-output",
        type=Path,
        default=data / "diamandis_sample_proteomics_v1.json.gz",
    )
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--rscript", default=shutil.which("Rscript") or "Rscript")
    parser.add_argument("--legacy-convert", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--workspace", type=Path, help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.legacy_convert:
        if args.workspace is None:
            raise RuntimeError("--workspace is required in legacy conversion mode")
        _legacy_convert(args.workspace, args.output, args.fixture_output)
    else:
        _build(args.output, args.fixture_output, args.source_dir, args.rscript)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
