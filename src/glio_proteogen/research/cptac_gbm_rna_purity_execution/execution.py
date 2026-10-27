"""Freeze source evidence, preserve holds, and invoke only the existing purity lane."""

from __future__ import annotations

import hashlib
import sys
from dataclasses import asdict, dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn, SupportsIndex

from glio_proteogen.research.cptac_gbm_external_admission.cohort_plan import load_discovery_plan
from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock
from glio_proteogen.research.cptac_gbm_external_admission.identity import (
    HGNC_LOCK,
    read_locked_hgnc,
)
from glio_proteogen.research.cptac_gbm_external_admission.source import read_verified_source
from glio_proteogen.research.cptac_gbm_rna_purity_admission.context import ContextState
from glio_proteogen.research.cptac_gbm_rna_purity_admission.preflight import (
    _check_directory,
    _check_seal,
    _document,
    _read,
    _sealed,
    _write,
)

from .clinical import (
    SOURCE_LOCKS,
    ClinicalAdmission,
    ClinicalAdmissionReceipt,
    ClinicalSources,
    ClinicalTarget,
    admit_clinical_context,
)
from .contracts import PROFILE_ID, ExecutionError, canonical_bytes, digest, validate_digest
from .identity import (
    AUTHOR_FEATURE_LOCK,
    GTF_LOCK,
    HGNC_METADATA_LOCK,
    ModelAxisReceipt,
    ModelInputAxis,
    admit_model_axis,
)
from .inference import qualify_execution, run_qualified_projection
from .inputs import CLINICAL_ROLES, ExecutionInputs
from .native_counts import (
    MAX_ASSAY_BYTES,
    NativeCountDomainError,
    NativeCountFormatError,
    project_native_star_counts,
)
from .receipts import OUTCOMES, ExecutionProtocol, ExecutionReport, OutcomeCounts

if TYPE_CHECKING:
    from glio_proteogen.research.cptac_gbm_external_admission.plan import ExternalAdmissionPlan

_ROOT = Path(__file__).resolve().parents[4]
_NAMESPACE = "src/glio_proteogen/research/"
_SOURCE_DIRS = (
    "cptac_gbm_rna_purity_execution",
    "cptac_gbm_rna_purity_admission",
    "cptac_gbm_external_admission",
    "gbm_rna_purity",
)
_ARTIFACTS = frozenset(
    ("profile.json", "protocol.json", "identity.json", "clinical-context.json", "execution.json")
)
_MAX_METADATA = 4_000_000
_PROCESSING_LOCK = SourceLock(
    106838,
    "e412e6d5e7c5cee6a78db10e918b9d02",
    "532278d17bde85efe87dbcd93e335a82db36e7373f0b6473c7d01a0a8b9f1f0c",
)
PROCESSING_SOURCE_URL = (
    "https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/Expression_mRNA_Pipeline/"
)


def profile() -> dict[str, object]:
    """Describe code and source policy without accessing clinical/RNA/model tensors."""
    source_names = sorted(
        [
            str(path.relative_to(_ROOT)).replace("\\", "/")
            for directory in _SOURCE_DIRS
            for path in (_ROOT / _NAMESPACE / directory).glob("*.py")
        ]
        + [
            "src/glio_proteogen/kernel/models.py",
            "pyproject.toml",
            "uv.lock",
            "tools/evaluate_cptac_gbm_rna_purity_execution.py",
            "docs/research/cptac-gbm-rna-purity-execution.md",
        ]
    )
    return _sealed(
        {
            "schema_version": "cptac-gbm-native-star-purity-execution-profile/1.0.0",
            "profile_id": PROFILE_ID,
            "software": {
                "python": sys.version.split()[0],
                "numpy": version("numpy"),
                "pydantic": version("pydantic"),
                "defusedxml": version("defusedxml"),
            },
            "source_bindings": {
                name: "sha256:"
                + hashlib.sha256(
                    _read(_ROOT / name, maximum=_MAX_METADATA).replace(b"\r\n", b"\n")
                ).hexdigest()
                for name in source_names
            },
            "model_profile_id": "gbm-rna-tumor-purity/1.0.0",
            "model_features": 5829,
            "processing_source_url": PROCESSING_SOURCE_URL,
            "processing_source_lock": asdict(_PROCESSING_LOCK),
            "source_hold_precedes_assay_read": True,
            "numerical_projection_does_not_imply_clinical_eligibility": True,
            "outcomes": list(OUTCOMES),
            "individual_results_exported": False,
            "new_scientific_inference_lane": False,
            "clinical_validation": False,
        },
        "profile_digest",
    )


@dataclass(frozen=True, slots=True, repr=False)
class _Prepared:
    inputs: ExecutionInputs
    plan: ExternalAdmissionPlan
    axis: ModelInputAxis
    clinical: ClinicalAdmission
    profile_document: dict[str, object] = field(repr=False)
    protocol: ExecutionProtocol

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("private execution preparation cannot be serialized")


def _source_roles(inputs: ExecutionInputs, plan: ExternalAdmissionPlan) -> None:
    assay_paths = {
        (inputs.discovery.files_manifest_path.parent / value.relative_path).resolve()
        for value in plan.files.values()
    }
    assay_hashes = {value.lock.sha256 for value in plan.files.values()}
    sources = (*inputs.clinical_sources, inputs.processing_source)
    paths = tuple(source.path.resolve() for source in sources)
    reference_paths = (*inputs.reference_paths, inputs.discovery.hgnc_path)
    if (
        len(set(paths)) != len(paths)
        or any(path.resolve() in assay_paths for path in (*paths, *reference_paths))
        or any(source.lock.sha256 in assay_hashes for source in sources)
        or any(
            lock.sha256 in assay_hashes
            for lock in (
                HGNC_LOCK,
                AUTHOR_FEATURE_LOCK,
                GTF_LOCK,
                HGNC_METADATA_LOCK,
            )
        )
        or any(
            (source.lock.bytes, source.lock.md5, source.lock.sha256)
            != (lock.bytes, lock.md5, lock.sha256.removeprefix("sha256:"))
            for source, lock in zip(inputs.clinical_sources, SOURCE_LOCKS, strict=True)
        )
        or inputs.processing_source.lock != _PROCESSING_LOCK
    ):
        raise ExecutionError(
            "source roles must be distinct and match their official snapshot locks"
        )


def _prepare(inputs: ExecutionInputs) -> _Prepared:
    if type(inputs) is not ExecutionInputs:
        raise ExecutionError("validated execution inputs are required")
    inputs = ExecutionInputs(
        **{name: getattr(inputs, name) for name in inputs.__dataclass_fields__}
    )
    discovery = inputs.discovery
    plan = load_discovery_plan(
        choices_path=discovery.choices_path,
        choices_sha256=discovery.choices_sha256,
        map_bindings_path=discovery.map_bindings_path,
        map_bindings_sha256=discovery.map_bindings_sha256,
        files_manifest_path=discovery.files_manifest_path,
        files_manifest_sha256=discovery.files_manifest_sha256,
    )
    if (
        plan.receipt.profile_id != "cptac-gbm-discovery-metadata-plan/1.0.0"
        or plan.receipt.eligibility_admitted is not False
        or len(plan.candidates) != 72
        or len({row.rna_file_id for row in plan.candidates}) != 72
        or any(plan.files[row.rna_file_id].workflow != "STAR - Counts" for row in plan.candidates)
    ):
        raise ExecutionError("the complete inherited discovery RNA axis is required")
    _source_roles(inputs, plan)
    axis = admit_model_axis(
        hgnc=read_locked_hgnc(discovery.hgnc_path),
        gencode_gtf_path=inputs.gencode_gtf_path,
        gencode_hgnc_path=inputs.gencode_hgnc_path,
        author_feature_path=inputs.author_feature_path,
    )
    # The official workflow defines native unstranded counts; selecting that
    # column from the exact unchanged source is the processing proof. Normalized
    # columns are validated by the projector but never fed into the model.
    read_verified_source(inputs.processing_source.path, _PROCESSING_LOCK, max_bytes=_MAX_METADATA)
    sources = ClinicalSources(
        **dict(
            zip(
                CLINICAL_ROLES,
                (
                    read_verified_source(source.path, source.lock, max_bytes=_MAX_METADATA)
                    for source in inputs.clinical_sources
                ),
                strict=True,
            )
        )
    )
    clinical = admit_clinical_context(
        tuple(
            ClinicalTarget(
                case_key=row.case_submitter_id,
                sample_key=row.sample_submitter_id,
                gdc_sample_id=row.gdc_sample_uuid,
                protein_aliquot_key=row.protein_aliquot_submitter_id,
                protein_aliquot_id=row.protein_aliquot_uuid,
                lineage_digest=digest(asdict(row)),
            )
            for row in plan.candidates
        ),
        sources,
    )
    profile_document = profile()
    protocol_data: dict[str, object] = {
        "profile_digest": profile_document["profile_digest"],
        "planned_rna_bytes": sum(plan.files[row.rna_file_id].lock.bytes for row in plan.candidates),
        "metadata_binding_digest": digest(
            (
                discovery.choices_sha256,
                discovery.map_bindings_sha256,
                discovery.files_manifest_sha256,
            )
        ),
        "ordered_rna_input_inventory_digest": digest(
            [
                {"candidate": asdict(row), "rna": asdict(plan.files[row.rna_file_id])}
                for row in plan.candidates
            ]
        ),
        "model_axis_digest": axis.digest,
        "clinical_receipt_digest": digest(clinical.receipt.model_dump(mode="json")),
        "processing_source_digest": "sha256:" + _PROCESSING_LOCK.sha256,
        "policy": inputs.policy.model_dump(mode="json"),
        "protocol_digest": "sha256:" + "0" * 64,
    }
    provisional = ExecutionProtocol.model_validate(protocol_data).model_dump(mode="json")
    provisional.pop("protocol_digest")
    protocol = ExecutionProtocol.model_validate(_sealed(provisional, "protocol_digest"))
    return _Prepared(inputs, plan, axis, clinical, profile_document, protocol)


def frozen_protocol(inputs: ExecutionInputs) -> dict[str, object]:
    """Freeze references, clinical sources, processing and complete lineage before RNA."""
    return _prepare(inputs).protocol.model_dump(mode="json")


def _output_path(path: Path, inputs: ExecutionInputs) -> Path:
    output = path.resolve()
    if output.exists() or not output.parent.is_dir():
        raise ExecutionError("a fresh execution output directory is required")
    for source in inputs.input_paths:
        target = source.resolve()
        if output == target or output in target.parents or target in output.parents:
            raise ExecutionError("execution output and sources must be disjoint")
    root = inputs.discovery.files_manifest_path.parent.resolve()
    if output == root or root in output.parents:
        raise ExecutionError("execution output must be outside the measurement directory")
    return output


def _write_initial(output: Path, prepared: _Prepared) -> None:
    try:
        output.mkdir()
    except OSError:
        raise ExecutionError("fresh execution output could not be created") from None
    _write(output / "profile.json", prepared.profile_document)
    _write(output / "protocol.json", prepared.protocol.model_dump(mode="json"))
    _write(output / "identity.json", prepared.axis.receipt.model_dump(mode="json"))
    _write(output / "clinical-context.json", prepared.clinical.receipt.model_dump(mode="json"))


def evaluate_execution(
    inputs: ExecutionInputs,
    *,
    output_dir: Path,
    expected_protocol_digest: str,
) -> dict[str, object]:
    """Project nonheld inputs and run the unchanged model only after every gate passes."""
    validate_digest(expected_protocol_digest)
    prepared = _prepare(inputs)
    if prepared.protocol.protocol_digest != expected_protocol_digest:
        raise ExecutionError("execution differs from its frozen protocol; RNA was not read")
    inputs = prepared.inputs
    output = _output_path(output_dir, inputs)
    _write_initial(output, prepared)
    outcomes = dict.fromkeys(OUTCOMES, 0)
    feature_states = [0] * 6
    read_files = projected = verified_bytes = ready = supported = model_runs = 0
    inventory = hashlib.sha256()
    for candidate, clinical in zip(prepared.plan.candidates, prepared.clinical.cases, strict=True):
        projection = None
        summary = None
        if clinical.source_hold:
            outcome = "source_hold"
        else:
            binding = prepared.plan.files[candidate.rna_file_id]
            # I/O and byte-integrity errors are fatal, never biological abstentions.
            payload = read_verified_source(
                inputs.discovery.files_manifest_path.parent / binding.relative_path,
                binding.lock,
                max_bytes=MAX_ASSAY_BYTES,
            )
            read_files += 1
            verified_bytes += len(payload)
            try:
                projection = project_native_star_counts(
                    payload,
                    lock=binding.lock,
                    model_axis=prepared.axis,
                )
            except NativeCountDomainError:
                outcome = "domain_rejected"
            except NativeCountFormatError:
                outcome = "schema_rejected"
            else:
                projected += 1
                ready += int(projection.receipt.count_ready)
                supported += int(projection.receipt.coverage_supported)
                for index, count in enumerate(projection.receipt.state_counts):
                    feature_states[index] += count
                # Clinical context and raw-coordinate processing have disjoint
                # authorities. Neither repairs absent integrated diagnosis.
                components = (
                    *clinical.component_states[:4],
                    ContextState.SOURCE_SUPPORTED,
                    ContextState.SOURCE_SUPPORTED,
                    ContextState.SOURCE_SUPPORTED,
                )
                qualification = qualify_execution(
                    projection,
                    component_states=components,
                    protocol_digest=prepared.protocol.protocol_digest,
                    model_axis_digest=prepared.axis.digest,
                    context_evidence_digest=clinical.observations_digest,
                    context_source_set_digest=digest(
                        (
                            prepared.clinical.receipt.source_set_digest,
                            prepared.protocol.processing_source_digest,
                            prepared.protocol.metadata_binding_digest,
                        )
                    ),
                    lineage_digest=digest(asdict(candidate)),
                    policy=inputs.policy,
                )
                summary = run_qualified_projection(
                    projection,
                    model_axis=prepared.axis,
                    qualification=qualification,
                    policy=inputs.policy,
                )
                outcome = summary.outcome
                model_runs += int(summary.inference_executed)
            del payload
        outcomes[outcome] += 1
        inventory.update(
            canonical_bytes(
                {
                    "rna_file_key": candidate.rna_file_id,
                    "outcome": outcome,
                    "clinical": clinical.observations_digest,
                    "projection": None if projection is None else projection.binding_digest,
                    "execution": None if summary is None else summary.binding_digest,
                }
            )
            + b"\n"
        )
        del projection, summary
    provisional = ExecutionReport(
        protocol_digest=prepared.protocol.protocol_digest,
        report_digest="sha256:" + "0" * 64,
        planned_rna_bytes=prepared.protocol.planned_rna_bytes,
        verified_rna_bytes=verified_bytes,
        read_rna_files=read_files,
        projected_files=projected,
        coverage_supported_files=supported,
        numerically_ready_files=ready,
        model_executions=model_runs,
        outcomes=OutcomeCounts(**outcomes),
        feature_state_totals=tuple(feature_states),  # type: ignore[arg-type]
        model_axis_digest=prepared.axis.digest,
        clinical_receipt_digest=prepared.protocol.clinical_receipt_digest,
        ordered_execution_inventory_digest="sha256:" + inventory.hexdigest(),
    ).model_dump(mode="json")
    provisional.pop("report_digest")
    report = ExecutionReport.model_validate_json(
        canonical_bytes(_sealed(provisional, "report_digest"))
    )
    result = report.model_dump(mode="json")
    _publish_complete(output, result)
    return result


def _validate_documents(documents: dict[str, dict[str, object]]) -> ExecutionReport:
    _check_seal(documents["profile.json"], "profile_digest")
    if canonical_bytes(documents["profile.json"]) != canonical_bytes(profile()):
        raise ExecutionError("saved execution profile differs from the current method")
    _check_seal(documents["protocol.json"], "protocol_digest")
    _check_seal(documents["execution.json"], "report_digest")
    protocol = ExecutionProtocol.model_validate_json(canonical_bytes(documents["protocol.json"]))
    report = ExecutionReport.model_validate_json(canonical_bytes(documents["execution.json"]))
    axis = ModelAxisReceipt.model_validate_json(canonical_bytes(documents["identity.json"]))
    clinical = ClinicalAdmissionReceipt.model_validate_json(
        canonical_bytes(documents["clinical-context.json"])
    )
    if (
        canonical_bytes(protocol.model_dump(mode="json"))
        != canonical_bytes(documents["protocol.json"])
        or canonical_bytes(report.model_dump(mode="json"))
        != canonical_bytes(documents["execution.json"])
        or canonical_bytes(axis.model_dump(mode="json"))
        != canonical_bytes(documents["identity.json"])
        or canonical_bytes(clinical.model_dump(mode="json"))
        != canonical_bytes(documents["clinical-context.json"])
        or protocol.profile_digest != documents["profile.json"]["profile_digest"]
        or report.protocol_digest != protocol.protocol_digest
        or report.planned_rna_bytes != protocol.planned_rna_bytes
        or report.model_axis_digest != protocol.model_axis_digest
        or digest(documents["identity.json"]) != protocol.model_axis_digest
        or report.clinical_receipt_digest != protocol.clinical_receipt_digest
        or digest(documents["clinical-context.json"]) != protocol.clinical_receipt_digest
        or protocol.processing_source_digest != "sha256:" + _PROCESSING_LOCK.sha256
        or report.outcomes.source_hold != clinical.source_hold_cases
        or report.model_executions > clinical.target_context_ready_cases
    ):
        raise ExecutionError("saved execution documents do not have exact bindings")
    return report


def _publish_complete(output: Path, report: dict[str, object]) -> None:
    initial = _ARTIFACTS - {"execution.json"}
    _check_directory(output, initial)
    documents = {name: _document(_read(output / name, maximum=_MAX_METADATA)) for name in initial}
    documents["execution.json"] = report
    _validate_documents(documents)
    pending = output / "execution.json.pending"
    _write(pending, report)
    if _read(pending, maximum=_MAX_METADATA) != canonical_bytes(report) + b"\n":
        raise ExecutionError("staged execution report differs from verified content")
    _check_directory(output, initial | {pending.name})
    try:
        pending.rename(output / "execution.json")
    except OSError:
        raise ExecutionError(
            "execution completion was not published; retain staged evidence"
        ) from None


def verify_execution(directory: Path) -> dict[str, object]:
    """Check saved aggregate integrity and conservation without replaying private sources."""
    try:
        _check_directory(directory, _ARTIFACTS)
        report = _validate_documents(
            {name: _document(_read(directory / name, maximum=_MAX_METADATA)) for name in _ARTIFACTS}
        )
    except ExecutionError:
        raise
    except (OSError, TypeError, ValueError, RecursionError):
        raise ExecutionError("saved execution evidence was not accepted") from None
    return {
        "verified": True,
        "complete": True,
        "profile_id": PROFILE_ID,
        "protocol_digest": report.protocol_digest,
        "report_digest": report.report_digest,
        "raw_sources_reparsed": False,
        "models_executed_by_verifier": False,
        "verification_scope": "saved_aggregate_integrity_and_conservation",
    }


__all__ = ["evaluate_execution", "frozen_protocol", "profile", "verify_execution"]
