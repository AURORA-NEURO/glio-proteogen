"""Freeze and verify an aggregate clinical review before any assay access."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal, Never, SupportsIndex

from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.cptac_gbm_external_admission import plan as metadata
from glio_proteogen.research.cptac_gbm_external_admission.cohort_plan import load_discovery_plan
from glio_proteogen.research.cptac_gbm_external_admission.source import read_verified_source
from glio_proteogen.research.cptac_gbm_rna_purity_admission.inputs import (
    LockedInput,
    _locked,
    _object,
    _path,
)
from glio_proteogen.research.cptac_gbm_rna_purity_admission.preflight import (
    _check_directory,
    _document,
    _read,
    _sealed,
    _write,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.execution import (
    _output_path,
    _prepare,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.execution import (
    profile as baseline_profile,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.inputs import (
    ExecutionInputs,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.inputs import (
    load_inputs as load_baseline_inputs,
)

from .contracts import (
    PROFILE_ID,
    ResolutionError,
    canonical_bytes,
    checked_receipt_document,
    seal_document,
    validate_digest,
)
from .receipts import ClinicalResolutionReceipt, ClinicalSourceReceipt
from .source import SOURCE_LOCK, review_source

_ROOT = Path(__file__).resolve().parents[4]
_NAMESPACE = "src/glio_proteogen/research/cptac_gbm_rna_purity_resolution/"
_ARTIFACTS = frozenset(("profile.json", "protocol.json", "source.json", "resolution.json"))
_MAXIMUM = 1_048_576


@dataclass(frozen=True, slots=True, repr=False)
class ResolutionInputs:
    baseline: ExecutionInputs = field(repr=False)
    source: LockedInput = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.baseline) is not ExecutionInputs or type(self.source) is not LockedInput:
            raise ResolutionError("verified baseline and locked clinical source are required")
        ExecutionInputs(
            **{name: getattr(self.baseline, name) for name in self.baseline.__dataclass_fields__}
        )
        LockedInput(self.source.path, self.source.lock)
        if self.source.lock != SOURCE_LOCK:
            raise ResolutionError("clinical review source lock differs from its reviewed snapshot")

    def __repr__(self) -> str:
        return "<ResolutionInputs private>"

    def __reduce_ex__(self, _protocol: SupportsIndex) -> Never:
        raise TypeError("private clinical review inputs cannot be serialized")


class ReviewProtocol(FrozenModel):
    SEAL_FIELD: ClassVar[str] = "receipt_digest"
    schema_version: Literal["cptac-gbm-clinical-gap-review-protocol/1.0.0"] = (
        "cptac-gbm-clinical-gap-review-protocol/1.0.0"
    )
    profile_digest: Sha256Digest
    baseline_protocol_digest: Sha256Digest
    baseline_profile_digest: Sha256Digest
    baseline_clinical_receipt_digest: Sha256Digest
    source_receipt_digest: Sha256Digest
    resolution_receipt_digest: Sha256Digest
    receipt_digest: Sha256Digest


def load_inputs(path: Path, *, sha256: str) -> ResolutionInputs:
    """Read one closed private config and its locked baseline metadata config."""
    try:
        row = _object(
            metadata._read_json(path, sha256),
            {"schema_version", "baseline_inputs", "clinical_source"},
        )
        if row["schema_version"] != "cptac-gbm-clinical-gap-review-inputs/1.0.0":
            raise ResolutionError("clinical review input version is invalid")  # noqa: TRY301
        baseline = _object(row["baseline_inputs"], {"path", "sha256"})
        baseline_path = _path(path.resolve().parent, baseline["path"])
        inputs = load_baseline_inputs(baseline_path, sha256=baseline["sha256"])  # type: ignore[arg-type]
        return ResolutionInputs(inputs, _locked(path.resolve().parent, row["clinical_source"]))
    except ResolutionError:
        raise
    except (AttributeError, OSError, TypeError, ValueError, RecursionError):
        raise ResolutionError("clinical review configuration was not accepted") from None


def profile() -> dict[str, object]:
    names = sorted(
        [_NAMESPACE + path.name for path in (_ROOT / _NAMESPACE).glob("*.py")]
        + [
            "tools/evaluate_cptac_gbm_clinical_resolution.py",
            "docs/research/cptac-gbm-clinical-resolution.md",
        ]
    )
    return _sealed(
        {
            "profile_id": PROFILE_ID,
            "baseline_profile_digest": baseline_profile()["profile_digest"],
            "source_bindings": {
                name: "sha256:"
                + hashlib.sha256(
                    _read(_ROOT / name, maximum=_MAXIMUM).replace(b"\r\n", b"\n")
                ).hexdigest()
                for name in names
            },
            "review_kind": "source_attributed_descriptive_clinical_context",
            "qualification_basis": "none_in_reviewed_source",
            "rna_read": False,
            "model_executed": False,
            "clinical_diagnosis_inferred": False,
            "individual_results_exported": False,
        },
        "profile_digest",
    )


def _source_role(inputs: ResolutionInputs) -> None:
    """Reject path, content-role and hard-link aliases before the new source read."""
    discovery = inputs.baseline.discovery
    plan = load_discovery_plan(
        choices_path=discovery.choices_path,
        choices_sha256=discovery.choices_sha256,
        map_bindings_path=discovery.map_bindings_path,
        map_bindings_sha256=discovery.map_bindings_sha256,
        files_manifest_path=discovery.files_manifest_path,
        files_manifest_sha256=discovery.files_manifest_sha256,
    )
    path = inputs.source.path.resolve()
    assays = tuple(
        (discovery.files_manifest_path.parent / value.relative_path).resolve()
        for value in plan.files.values()
    )
    protected = (*assays, *(value.resolve() for value in inputs.baseline.input_paths))
    source_info = path.stat()
    if (
        path in protected
        or inputs.source.lock.sha256 in {value.lock.sha256 for value in plan.files.values()}
        or any(value.exists() and value.samefile(path) for value in protected)
    ):
        raise ResolutionError("clinical source role overlaps a protected input")
    if not source_info.st_size == SOURCE_LOCK.bytes:
        raise ResolutionError("clinical source size differs from its reviewed snapshot")


def _typed[ReceiptT: FrozenModel](
    values: dict[str, object], model_type: type[ReceiptT], seal: str
) -> ReceiptT:
    materialized = model_type.model_validate_json(
        canonical_bytes(
            {
                **values,
                seal: "sha256:" + "0" * 64,
            }
        )
    ).model_dump(mode="json")
    return checked_receipt_document(
        seal_document(materialized, seal), model_type, digest_field=seal
    )


def _prepare_review(inputs: ResolutionInputs) -> dict[str, dict[str, object]]:
    if type(inputs) is not ResolutionInputs:
        raise ResolutionError("verified clinical review inputs are required")
    inputs = ResolutionInputs(inputs.baseline, inputs.source)
    _source_role(inputs)
    baseline = _prepare(inputs.baseline)
    payload = read_verified_source(inputs.source.path, SOURCE_LOCK, max_bytes=_MAXIMUM)
    stats = json.loads(review_source(baseline.clinical, payload).aggregate_bytes)
    evidence_digest = stats.pop("resolution_evidence_digest")
    target_digest = stats.pop("ordered_target_bindings_digest")
    source = _typed(stats, ClinicalSourceReceipt, "source_receipt_digest")
    clinical_digest = baseline.clinical.receipt.receipt_digest
    resolution = _typed(
        {
            "baseline_clinical_receipt_digest": clinical_digest,
            "ordered_case_axis_digest": baseline.clinical.receipt.ordered_axis_digest,
            "ordered_target_bindings_digest": target_digest,
            "source_receipt_digest": source.source_receipt_digest,
            "resolution_evidence_digest": evidence_digest,
        },
        ClinicalResolutionReceipt,
        "receipt_digest",
    )
    method = profile()
    protocol = _typed(
        {
            "profile_digest": method["profile_digest"],
            "baseline_protocol_digest": baseline.protocol.protocol_digest,
            "baseline_profile_digest": baseline.profile_document["profile_digest"],
            "baseline_clinical_receipt_digest": clinical_digest,
            "source_receipt_digest": source.source_receipt_digest,
            "resolution_receipt_digest": resolution.receipt_digest,
        },
        ReviewProtocol,
        "receipt_digest",
    )
    return {
        "profile.json": method,
        "protocol.json": protocol.model_dump(mode="json"),
        "source.json": source.model_dump(mode="json"),
        "resolution.json": resolution.model_dump(mode="json"),
    }


def prepare_review(inputs: ResolutionInputs) -> dict[str, object]:
    """Freeze method, original baseline and the exact new evidence before assays."""
    return _prepare_review(inputs)["protocol.json"]


def _validate(documents: dict[str, dict[str, object]]) -> ClinicalResolutionReceipt:
    current_profile = profile()
    if canonical_bytes(documents["profile.json"]) != canonical_bytes(current_profile):
        raise ResolutionError("clinical review method differs from the current implementation")
    protocol = checked_receipt_document(
        documents["protocol.json"], ReviewProtocol, digest_field="receipt_digest"
    )
    source = checked_receipt_document(
        documents["source.json"], ClinicalSourceReceipt, digest_field="source_receipt_digest"
    )
    resolution = checked_receipt_document(
        documents["resolution.json"], ClinicalResolutionReceipt, digest_field="receipt_digest"
    )
    if (
        protocol.profile_digest != documents["profile.json"]["profile_digest"]
        or protocol.baseline_profile_digest != current_profile["baseline_profile_digest"]
        or protocol.source_receipt_digest != source.source_receipt_digest
        or resolution.source_receipt_digest != source.source_receipt_digest
        or protocol.resolution_receipt_digest != resolution.receipt_digest
        or protocol.baseline_clinical_receipt_digest != resolution.baseline_clinical_receipt_digest
        or source.source_qualified_cases != resolution.source_qualified_cases
    ):
        raise ResolutionError("clinical review cross-document bindings disagree")
    return resolution


def evaluate_review(
    inputs: ResolutionInputs, *, output_dir: Path, expected_protocol_digest: str
) -> dict[str, object]:
    """Publish only a complete, frozen, aggregate review in a fresh directory."""
    expected = validate_digest(expected_protocol_digest)
    documents = _prepare_review(inputs)
    if documents["protocol.json"]["receipt_digest"] != expected:
        raise ResolutionError("clinical review protocol changed after preparation")
    _validate(documents)
    output = _output_path(output_dir, inputs.baseline)
    source = inputs.source.path.resolve()
    if output == source or output in source.parents or source in output.parents:
        raise ResolutionError("clinical review output overlaps its source")
    output.mkdir()
    for name in ("profile.json", "protocol.json", "source.json", "resolution.json"):
        _write(output / name, documents[name])
    return verify_review(output)


def verify_review(directory: Path) -> dict[str, object]:
    """Check saved canonical receipts and method; this does not replay sources."""
    _check_directory(directory, _ARTIFACTS)
    documents = {}
    for name in sorted(_ARTIFACTS):
        payload = _read(directory / name, maximum=_MAXIMUM)
        document = _document(payload)
        if payload != canonical_bytes(document) + b"\n":
            raise ResolutionError("saved clinical review is not canonical")
        documents[name] = document
    resolution = _validate(documents)
    return {
        "complete": True,
        "verification_kind": "saved_aggregate_integrity",
        "receipt_digest": resolution.receipt_digest,
        "source_qualified_cases": resolution.source_qualified_cases,
        "rna_read": False,
        "model_executed": False,
        "individual_results_exported": False,
    }


__all__ = [
    "ResolutionInputs",
    "ReviewProtocol",
    "evaluate_review",
    "load_inputs",
    "prepare_review",
    "profile",
    "verify_review",
]
