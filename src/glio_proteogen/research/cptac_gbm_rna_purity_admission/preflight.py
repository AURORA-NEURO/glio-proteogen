"""Whole-axis native-count admission with source-first seals and no inference."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from dataclasses import asdict, dataclass, field
from importlib.metadata import version
from itertools import islice
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn, SupportsIndex, cast

from glio_proteogen.research.cptac_gbm_external_admission import plan as metadata
from glio_proteogen.research.cptac_gbm_external_admission.cohort_plan import load_discovery_plan
from glio_proteogen.research.cptac_gbm_external_admission.identity import read_locked_hgnc
from glio_proteogen.research.cptac_gbm_external_admission.source import read_verified_source

from .context import (
    ContextInventory,
    ContextState,
    ContextTarget,
    assess_context_inventory,
    parse_context_evidence,
)
from .contracts import (
    MAX_CONTEXT_BYTES,
    MAX_METADATA_BYTES,
    MAX_OUTPUT_BYTES,
    PROFILE_ID,
    AdmissionError,
    canonical_bytes,
    digest,
    require,
    validate_digest,
)

if TYPE_CHECKING:
    from glio_proteogen.research.cptac_gbm_external_admission.contracts import HgncReference
    from glio_proteogen.research.cptac_gbm_external_admission.plan import ExternalAdmissionPlan
from .identity import ModelInputAxis, admit_model_axis
from .inputs import DiscoveryInputs
from .native_counts import (
    MAX_ASSAY_BYTES,
    STATES,
    NativeCountDomainError,
    NativeCountFormatError,
    NativeCountReceipt,
    project_native_star_counts,
)
from .receipts import (
    COVERAGE_BINS,
    OUTCOMES,
    ContextReadinessCounts,
    CoverageBin,
    FeatureStateTotals,
    NativeSchemaTotals,
    OutcomeCounts,
    PreflightProtocol,
    PreflightReport,
)

_REPOSITORY = Path(__file__).resolve().parents[4]
_NAMESPACE = "src/glio_proteogen/research/cptac_gbm_rna_purity_admission/"
_SOURCE_FILES = (
    *(
        _NAMESPACE + name
        for name in (
            "__init__.py",
            "contracts.py",
            "context.py",
            "identity.py",
            "inputs.py",
            "native_counts.py",
            "preflight.py",
            "receipts.py",
        )
    ),
    "src/glio_proteogen/research/cptac_gbm_external_admission/assays.py",
    "src/glio_proteogen/research/cptac_gbm_external_admission/cohort_plan.py",
    "src/glio_proteogen/research/cptac_gbm_external_admission/contracts.py",
    "src/glio_proteogen/research/cptac_gbm_external_admission/identity.py",
    "src/glio_proteogen/research/cptac_gbm_external_admission/plan.py",
    "src/glio_proteogen/research/cptac_gbm_external_admission/source.py",
    "src/glio_proteogen/research/gbm_rna_purity/catalog.py",
    "src/glio_proteogen/research/gbm_rna_purity/contracts.py",
    "src/glio_proteogen/kernel/models.py",
    "pyproject.toml",
    "uv.lock",
    "tools/evaluate_cptac_gbm_rna_purity_preflight.py",
    "docs/research/cptac-gbm-rna-purity-admission.md",
    "docs/traceability/cptac-gbm-rna-purity-admission.csv",
)
_ARTIFACTS = frozenset(("profile.json", "protocol.json", "preflight.json"))
_SCHEMA_FIELDS = tuple(NativeSchemaTotals.model_fields)


def _read(path: Path, *, maximum: int) -> bytes:
    try:
        before = metadata._snapshot(path.lstat())
        require(1 <= before[2] <= maximum, "saved admission artifact exceeds its bound")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            require(
                metadata._snapshot(opened) == before, "saved admission artifact binding changed"
            )
            payload = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        if (
            metadata._snapshot(after) != before
            or opened.st_ctime_ns != after.st_ctime_ns
            or metadata._snapshot(path.lstat()) != before
            or len(payload) != before[2]
        ):
            raise AdmissionError("saved admission artifact binding changed")  # noqa: TRY301 -- guarded bounded read
    except AdmissionError:
        raise
    except (OSError, TypeError, ValueError):
        raise AdmissionError("saved admission artifact could not be read") from None
    return payload


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AdmissionError("admission JSON contains duplicate fields")
        result[key] = value
    return result


def _invalid_number(_value: str) -> NoReturn:
    raise AdmissionError("admission JSON contains an invalid number")


def _document(payload: bytes) -> dict[str, object]:
    try:
        value: object = json.loads(
            payload, object_pairs_hook=_pairs, parse_constant=_invalid_number
        )
        require(
            type(value) is dict and payload == canonical_bytes(value) + b"\n",
            "saved admission artifact is not canonical",
        )
        return cast("dict[str, object]", value)
    except AdmissionError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise AdmissionError("saved admission JSON was not accepted") from None


def _sealed(document: dict[str, object], field_name: str) -> dict[str, object]:
    return {**document, field_name: digest(document)}


def _check_seal(document: dict[str, object], field_name: str) -> None:
    provided = document.get(field_name)
    validate_digest(provided)
    if digest({key: value for key, value in document.items() if key != field_name}) != provided:
        raise AdmissionError("saved admission digest differs from its content")


def _write(path: Path, document: object) -> None:
    payload = canonical_bytes(document) + b"\n"
    if len(payload) > MAX_OUTPUT_BYTES:
        raise AdmissionError("admission artifact exceeds its output bound")
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except OSError:
        raise AdmissionError("admission artifact could not be written exclusively") from None


def profile() -> dict[str, object]:
    """Describe the exact policy/code without reading inputs or invoking a model."""
    bindings = {
        name: "sha256:"
        + hashlib.sha256(
            _read(_REPOSITORY / name, maximum=MAX_METADATA_BYTES).replace(b"\r\n", b"\n")
        ).hexdigest()
        for name in _SOURCE_FILES
    }
    return _sealed(
        {
            "schema_version": "cptac-gbm-native-star-purity-preflight-profile/1.0.0",
            "profile_id": PROFILE_ID,
            "software": {
                "python": sys.version.split()[0],
                "numpy": version("numpy"),
                "pydantic": version("pydantic"),
            },
            "source_bindings": bindings,
            "model_profile": "gbm-rna-tumor-purity/1.0.0",
            "model_features": 5_829,
            "native_coordinate": "STAR - Counts/unstranded/GENCODE v36",
            "minimum_recognized_features": 4_664,
            "coverage_supported_features": 5_771,
            "maximum_raw_count": 10**15,
            "maximum_rna_file_bytes": MAX_ASSAY_BYTES,
            "readiness_requires_positive_recognized_sum": True,
            "feature_states": list(STATES),
            "outcomes": list(OUTCOMES),
            "coverage_histogram_bins": list(COVERAGE_BINS),
            "context_states": [state.value for state in ContextState],
            "inference_requests_constructed": False,
            "models_executed": False,
            "new_scientific_inference_lane": False,
            "clinical_validation": False,
        },
        "profile_digest",
    )


@dataclass(frozen=True, slots=True)
class _Prepared:
    inputs: DiscoveryInputs = field(repr=False)
    plan: ExternalAdmissionPlan = field(repr=False)
    reference: HgncReference = field(repr=False)
    axis: ModelInputAxis = field(repr=False)
    context: ContextInventory = field(repr=False)
    targets: tuple[ContextTarget, ...] = field(repr=False)
    profile_document: dict[str, object] = field(repr=False)
    protocol: PreflightProtocol

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("private prepared admission cannot be serialized")


def _prepare(inputs: DiscoveryInputs) -> _Prepared:
    if type(inputs) is not DiscoveryInputs:
        raise AdmissionError("validated discovery inputs are required")
    # Revalidate caller-owned declarations, including model_construct-like or
    # object.__setattr__ corruption, before any source access.
    inputs = DiscoveryInputs(
        **{name: getattr(inputs, name) for name in inputs.__dataclass_fields__}
    )
    plan = load_discovery_plan(
        choices_path=inputs.choices_path,
        choices_sha256=inputs.choices_sha256,
        map_bindings_path=inputs.map_bindings_path,
        map_bindings_sha256=inputs.map_bindings_sha256,
        files_manifest_path=inputs.files_manifest_path,
        files_manifest_sha256=inputs.files_manifest_sha256,
    )
    if (
        plan.receipt.profile_id != "cptac-gbm-discovery-metadata-plan/1.0.0"
        or plan.receipt.eligibility_admitted is not False
        or len(plan.candidates) != 72
        or len({row.rna_file_id for row in plan.candidates}) != 72
        or any(plan.files[row.rna_file_id].workflow != "STAR - Counts" for row in plan.candidates)
    ):
        raise AdmissionError("the complete inherited discovery RNA axis is required")
    # Declarations alone must keep context metadata separate from every planned
    # assay. Digest checks also catch copies whose paths do not reveal the alias.
    assay_paths = {
        (inputs.files_manifest_path.parent / binding.relative_path).resolve()
        for binding in plan.files.values()
    }
    assay_digests = {binding.lock.sha256 for binding in plan.files.values()}
    context_inputs = (
        *inputs.context_sources,
        *((inputs.context_evidence,) if inputs.context_evidence is not None else ()),
    )
    if any(
        source.path.resolve() in assay_paths or source.lock.sha256 in assay_digests
        for source in context_inputs
    ):
        raise AdmissionError("context metadata must be distinct from planned assay inputs")
    reference = read_locked_hgnc(inputs.hgnc_path)
    axis = admit_model_axis(reference)
    targets = tuple(ContextTarget(row.rna_file_id, digest(asdict(row))) for row in plan.candidates)
    verified_sources = []
    for source in inputs.context_sources:
        read_verified_source(source.path, source.lock, max_bytes=MAX_CONTEXT_BYTES)
        verified_sources.append("sha256:" + source.lock.sha256)
    if inputs.context_evidence is None:
        context = assess_context_inventory(targets)
    else:
        evidence = inputs.context_evidence
        context = parse_context_evidence(
            read_verified_source(evidence.path, evidence.lock, max_bytes=MAX_CONTEXT_BYTES),
            targets=targets,
            verified_source_digests=tuple(verified_sources),
        )
    inventory = tuple(
        {
            "candidate": asdict(row),
            "rna_file": asdict(plan.files[row.rna_file_id]),
        }
        for row in plan.candidates
    )
    profile_document = profile()
    protocol_data: dict[str, object] = {
        "profile_digest": profile_document["profile_digest"],
        "planned_files": len(plan.candidates),
        "planned_rna_bytes": sum(plan.files[row.rna_file_id].lock.bytes for row in plan.candidates),
        "metadata_binding_digest": digest(
            (inputs.choices_sha256, inputs.map_bindings_sha256, inputs.files_manifest_sha256)
        ),
        "ordered_rna_input_inventory_digest": digest(inventory),
        "model_axis_digest": axis.digest,
        "context_axis_digest": context.receipt.ordered_axis_digest,
        "context_evidence_digest": context.receipt.evidence_digest,
        "context_source_set_digest": context.receipt.verified_source_set_digest,
        "context_input_binding_digest": digest(
            {
                "evidence": None
                if inputs.context_evidence is None
                else asdict(inputs.context_evidence.lock),
                "sources": sorted(
                    (asdict(source.lock) for source in inputs.context_sources),
                    key=lambda row: str(row["sha256"]),
                ),
            }
        ),
    }
    # Include all default policy constants before computing the self digest.
    provisional = PreflightProtocol.model_validate(
        {**protocol_data, "protocol_digest": "sha256:" + "0" * 64}
    )
    full = provisional.model_dump(mode="json")
    full.pop("protocol_digest")
    protocol = PreflightProtocol.model_validate_json(
        canonical_bytes(_sealed(full, "protocol_digest"))
    )
    return _Prepared(inputs, plan, reference, axis, context, targets, profile_document, protocol)


def frozen_protocol(inputs: DiscoveryInputs) -> dict[str, object]:
    """Admit metadata/reference/context and freeze the complete axis before RNA reads."""
    return _prepare(inputs).protocol.model_dump(mode="json")


def _output_path(path: Path, inputs: DiscoveryInputs) -> Path:
    try:
        output = path.resolve()
        if output.exists() or not output.parent.is_dir():
            raise AdmissionError("a fresh output directory with an existing parent is required")
        for source in inputs.input_paths:
            target = source.resolve()
            if output == target or output in target.parents or target in output.parents:
                raise AdmissionError("output and source directories must be disjoint")
        measurements = inputs.files_manifest_path.resolve().parent
        if output == measurements or measurements in output.parents:
            raise AdmissionError("output must be outside the RNA measurement directory")
    except (OSError, ValueError):
        raise AdmissionError("admission output directory is invalid") from None
    return output


def _outcome(receipt: NativeCountReceipt) -> str:
    if receipt.count_ready:
        return "ready"
    if receipt.recognized_model_gene_count < 4_664:
        return "below_coverage_gate"
    return "zero_recognized_sum"


def evaluate_preflight(
    inputs: DiscoveryInputs,
    *,
    output_dir: Path,
    expected_protocol_digest: str,
) -> dict[str, object]:
    """Read every planned RNA once; retain only aggregate counts and one whole-axis seal."""
    validate_digest(expected_protocol_digest)
    prepared = _prepare(inputs)
    if prepared.protocol.protocol_digest != expected_protocol_digest:
        raise AdmissionError("preflight differs from its frozen protocol; RNA was not read")
    output = _output_path(output_dir, inputs)
    try:
        output.mkdir()
    except OSError:
        raise AdmissionError("fresh admission output directory could not be created") from None
    _write(output / "profile.json", prepared.profile_document)
    _write(output / "protocol.json", prepared.protocol.model_dump(mode="json"))
    outcomes = dict.fromkeys(OUTCOMES, 0)
    table = {state: dict.fromkeys(OUTCOMES, 0) for state in ContextState}
    states = dict.fromkeys(STATES, 0)
    totals = dict.fromkeys(_SCHEMA_FIELDS, 0)
    histogram = [0] * len(COVERAGE_BINS)
    recognized_sum = coverage_supported = zero_sum_files = verified_bytes = 0
    projection_inventory = hashlib.sha256()
    for candidate, assessment in zip(
        prepared.plan.candidates, prepared.context.assessments, strict=True
    ):
        binding = prepared.plan.files[candidate.rna_file_id]
        # Integrity/I/O errors stop incomplete. Only known schema/domain errors
        # become accounted rejection categories; unexpected exceptions propagate.
        payload = read_verified_source(
            inputs.files_manifest_path.parent / binding.relative_path,
            binding.lock,
            max_bytes=MAX_ASSAY_BYTES,
        )
        verified_bytes += len(payload)
        sample = None
        try:
            sample = project_native_star_counts(
                payload, lock=binding.lock, model_axis=prepared.axis, hgnc=prepared.reference
            )
        except NativeCountDomainError:
            outcome = "domain_rejected"
        except NativeCountFormatError:
            outcome = "schema_rejected"
        else:
            receipt = sample.receipt
            outcome = _outcome(receipt)
            for name in _SCHEMA_FIELDS:
                totals[name] += getattr(receipt, name)
            for name, count in zip(STATES, receipt.state_counts, strict=True):
                states[name] += count
            recognized_sum += receipt.recognized_raw_count_sum
            coverage_supported += int(receipt.coverage_supported)
            zero_sum_files += int(receipt.recognized_raw_count_sum == 0)
            histogram[
                min(len(COVERAGE_BINS) - 1, receipt.recognized_model_gene_count * 10 // 5_829)
            ] += 1
        outcomes[outcome] += 1
        table[assessment.state][outcome] += 1
        projection_inventory.update(
            canonical_bytes(
                {
                    "rna_file_key": candidate.rna_file_id,
                    "outcome": outcome,
                    "context_state": assessment.state.value,
                    "projection_binding": None if sample is None else sample.binding_digest,
                }
            )
            + b"\n"
        )
        del payload, sample
    report_data = {
        "protocol_digest": prepared.protocol.protocol_digest,
        "report_digest": "sha256:" + "0" * 64,
        "planned_files": len(prepared.plan.candidates),
        "planned_rna_bytes": prepared.protocol.planned_rna_bytes,
        "verified_rna_bytes": verified_bytes,
        "outcomes": OutcomeCounts(**outcomes),
        "schema_totals": NativeSchemaTotals(**totals),
        "feature_state_totals": FeatureStateTotals(**states),
        "recognized_raw_count_sum": recognized_sum,
        "coverage_supported_files": coverage_supported,
        "zero_recognized_sum_files": zero_sum_files,
        "coverage_histogram": tuple(
            CoverageBin(label=label, files=count)
            for label, count in zip(COVERAGE_BINS, histogram, strict=True)
        ),
        "context_by_readiness": tuple(
            ContextReadinessCounts(context_state=state, outcomes=OutcomeCounts(**table[state]))
            for state in ContextState
        ),
        "model_axis": prepared.axis.receipt,
        "context": prepared.context.receipt,
        "ordered_projection_inventory_digest": "sha256:" + projection_inventory.hexdigest(),
    }
    provisional = PreflightReport.model_validate(report_data)
    full = provisional.model_dump(mode="json")
    full.pop("report_digest")
    report = PreflightReport.model_validate_json(canonical_bytes(_sealed(full, "report_digest")))
    report_document = report.model_dump(mode="json")
    _publish_complete(output, report_document)
    return report_document


def _publish_complete(output: Path, report_document: dict[str, object]) -> None:
    # Every fallible method/integrity/conservation check precedes completion.
    # Only the final atomic rename publishes the authoritative complete report.
    _check_directory(output, frozenset(("profile.json", "protocol.json")))
    documents = {
        name: _document(_read(output / name, maximum=MAX_OUTPUT_BYTES))
        for name in ("profile.json", "protocol.json")
    }
    documents["preflight.json"] = report_document
    _validate_documents(documents)
    pending = output / "preflight.json.pending"
    _write(pending, report_document)
    require(
        _read(pending, maximum=MAX_OUTPUT_BYTES) == canonical_bytes(report_document) + b"\n",
        "staged admission report differs from its verified content",
    )
    _check_directory(output, frozenset(("profile.json", "protocol.json", pending.name)))
    try:
        pending.rename(output / "preflight.json")
    except OSError:
        raise AdmissionError(
            "admission completion could not be published; retain staged evidence"
        ) from None


def _check_directory(directory: Path, expected: frozenset[str]) -> None:
    info = directory.lstat()
    require(
        stat.S_ISDIR(info.st_mode)
        and not (
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
        ),
        "admission output must be a regular non-link directory",
    )
    require(
        {path.name for path in islice(directory.iterdir(), len(expected) + 1)} == expected,
        "admission output has extra or missing artifacts",
    )


def _validate_documents(
    documents: dict[str, dict[str, object]],
) -> tuple[PreflightProtocol, PreflightReport]:
    stored_profile = documents["profile.json"]
    _check_seal(stored_profile, "profile_digest")
    require(
        canonical_bytes(stored_profile) == canonical_bytes(profile()),
        "saved admission profile differs from the current method",
    )
    _check_seal(documents["protocol.json"], "protocol_digest")
    _check_seal(documents["preflight.json"], "report_digest")
    protocol = PreflightProtocol.model_validate_json(canonical_bytes(documents["protocol.json"]))
    report = PreflightReport.model_validate_json(canonical_bytes(documents["preflight.json"]))
    # JSON 0/1 compare equal to Python False/True. Canonical bytes also reject
    # those aliases, coercions and omitted default fields recursively.
    require(
        canonical_bytes(protocol.model_dump(mode="json"))
        == canonical_bytes(documents["protocol.json"]),
        "saved admission protocol does not have exact typed field representations",
    )
    require(
        canonical_bytes(report.model_dump(mode="json"))
        == canonical_bytes(documents["preflight.json"]),
        "saved admission report does not have exact typed field representations",
    )
    require(
        not (
            protocol.profile_digest != stored_profile["profile_digest"]
            or report.protocol_digest != protocol.protocol_digest
            or report.planned_files != protocol.planned_files
            or report.planned_rna_bytes != protocol.planned_rna_bytes
            or digest(report.model_axis.model_dump(mode="json")) != protocol.model_axis_digest
            or report.context.ordered_axis_digest != protocol.context_axis_digest
            or report.context.evidence_digest != protocol.context_evidence_digest
            or report.context.verified_source_set_digest != protocol.context_source_set_digest
        ),
        "saved admission protocol/report bindings differ",
    )
    return protocol, report


def verify_preflight(directory: Path) -> dict[str, object]:
    """Verify saved aggregate integrity/conservation; do not reparse source assays."""
    try:
        _check_directory(directory, _ARTIFACTS)
        documents = {
            name: _document(_read(directory / name, maximum=MAX_OUTPUT_BYTES))
            for name in _ARTIFACTS
        }
        protocol, report = _validate_documents(documents)
    except AdmissionError:
        raise
    except (OSError, TypeError, ValueError, RecursionError):
        raise AdmissionError("saved admission evidence was not accepted") from None
    return {
        "verified": True,
        "profile_id": PROFILE_ID,
        "protocol_digest": protocol.protocol_digest,
        "report_digest": report.report_digest,
        "complete": True,
        "raw_sources_reparsed": False,
        "models_executed": False,
        "verification_scope": "saved_aggregate_integrity_and_conservation",
    }


__all__ = ["evaluate_preflight", "frozen_protocol", "profile", "verify_preflight"]
