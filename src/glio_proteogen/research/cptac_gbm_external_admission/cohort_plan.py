"""Replay the frozen discovery specimen hierarchy and exact TMT channel joins.

Source metadata and its caller-supplied digests remain trust inputs. This local
loader rechecks internal exact associations, not the remote issuer or biology.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping, cast

from . import plan as boundary
from .contracts import MAX_SOURCE_BYTES, SourceLock
from .plan import (
    AdmissionPlanError,
    AssayInputBinding,
    CandidateBinding,
    ExternalAdmissionPlan,
    ExternalAdmissionReceipt,
    Workflow,
)

PROFILE_ID: Final = "cptac-gbm-discovery-metadata-plan/1.0.0"
MAP_SHA256: Final = "faea4574cd423c54b064c201391a9591160dc98ac3b6a443adaf8975914d74d1"
MAP_MD5: Final = "b1a598ad26a66015f339366e44799d6a"
_CANDIDATES: Final = 72
_PLEXES: Final = 11
_CHANNELS: Final = (
    "126C",
    "127N",
    "127C",
    "128N",
    "128C",
    "129N",
    "129C",
    "130N",
    "130C",
    "131N",
    "131C",
)
_RATIOS: Final = ",".join(channel + "/126C" for channel in _CHANNELS[1:])
_NORMALS: Final = frozenset(("Blood Derived Normal", "Solid Tissue Normal"))
_MD5: Final = re.compile(r"[0-9a-f]{32}")


def _list(value: object, *, maximum: int = 2_000) -> list[object]:
    if type(value) is not list or len(value) > maximum:
        boundary._fail()
    return value


def _object(value: object, required: set[str]) -> dict[str, object]:
    if type(value) is not dict or not required.issubset(value):
        boundary._fail()
    return cast("dict[str, object]", value)


def _official_file(value: object) -> dict[str, object]:
    row = _object(
        value,
        {
            "file_id",
            "id",
            "file_name",
            "file_size",
            "md5sum",
            "access",
            "state",
            "data_format",
            "data_type",
            "analysis",
            "associated_entities",
            "cases",
        },
    )
    file_id = boundary._uuid(row["file_id"])
    analysis = _object(row["analysis"], {"workflow_type"})
    workflow = analysis["workflow_type"]
    expected = {
        "STAR - Counts": "Gene Expression Quantification",
        "AscatNGS": "Gene Level Copy Number",
    }
    if (
        row["id"] != file_id
        or row["access"] != "open"
        or row["state"] != "released"
        or row["data_format"] != "TSV"
        or not isinstance(workflow, str)
        or workflow not in expected
        or row["data_type"] != expected[workflow]
    ):
        boundary._fail()
    boundary._text(row["file_name"], maximum=512)
    boundary._integer(row["file_size"], minimum=1, maximum=10_000_000)
    if type(row["md5sum"]) is not str or _MD5.fullmatch(row["md5sum"]) is None:
        boundary._fail()
    return row


def _associated_primary_sample(
    file: Mapping[str, object], *, case_label: str, sample_label: str, sample_uuid: str
) -> str:
    """Trace exact associated aliquot UUIDs through all captured nested parents."""

    ancestry: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    for case_value in _list(file["cases"]):
        case = _object(case_value, {"case_id", "submitter_id", "samples"})
        case_id = boundary._uuid(case["case_id"])
        case_submitter = boundary._text(case["submitter_id"])
        for sample_value in _list(case["samples"]):
            sample = _object(sample_value, {"sample_id", "submitter_id", "sample_type"})
            parent: tuple[str, ...] = (
                case_id,
                case_submitter,
                boundary._uuid(sample["sample_id"]),
                boundary._text(sample["submitter_id"]),
                boundary._text(sample["sample_type"]),
                boundary._text(sample["tissue_type"]) if sample.get("tissue_type") else "",
            )
            for portion_value in _list(sample.get("portions", [])):
                portion = _object(portion_value, {"portion_id"})
                portion_id = boundary._uuid(portion["portion_id"])
                for analyte_value in _list(portion.get("analytes", [])):
                    analyte = _object(analyte_value, {"analyte_id"})
                    analyte_id = boundary._uuid(analyte["analyte_id"])
                    for aliquot_value in _list(analyte.get("aliquots", [])):
                        aliquot = _object(aliquot_value, {"aliquot_id", "submitter_id"})
                        ancestry[boundary._uuid(aliquot["aliquot_id"])].add(
                            (
                                *parent,
                                portion_id,
                                analyte_id,
                                boundary._text(aliquot["submitter_id"]),
                            )
                        )
    parents: list[tuple[str, ...]] = []
    entities = _list(file["associated_entities"], maximum=2)
    if not entities:
        boundary._fail()
    seen: set[str] = set()
    for entity_value in entities:
        entity = _object(
            entity_value, {"case_id", "entity_id", "entity_type", "entity_submitter_id"}
        )
        entity_id = boundary._uuid(entity["entity_id"])
        candidates = ancestry.get(entity_id, set())
        if entity["entity_type"] != "aliquot" or entity_id in seen or len(candidates) != 1:
            boundary._fail()
        seen.add(entity_id)
        parent = next(iter(candidates))
        if (
            entity["case_id"] != parent[0]
            or entity["entity_submitter_id"] != parent[8]
            or parent[1] != case_label
        ):
            boundary._fail()
        parents.append(parent)
    tumors = [parent for parent in parents if parent[4] == "Primary Tumor"]
    if (
        len(tumors) != 1
        or tumors[0][2] != sample_uuid
        or tumors[0][3] != sample_label
        or tumors[0][5] not in ("", "Tumor")
    ):
        boundary._fail()
    for parent in parents:
        if parent[4] == "Primary Tumor":
            continue
        if (
            parent[4] not in _NORMALS
            or parent[5] not in ("", "Normal")
            or parent[0] != tumors[0][0]
        ):
            boundary._fail()
    workflow = _object(file["analysis"], {"workflow_type"})["workflow_type"]
    if workflow == "STAR - Counts" and len(parents) != 1:
        boundary._fail()
    return tumors[0][0]


def _pdc_candidate(
    value: object, files: Mapping[str, dict[str, object]]
) -> tuple[CandidateBinding, str]:
    row = boundary._record(
        value, {"pdc", "gdc_sample_uuid", "rna_file", "cnv_file", "metadata_candidate_not_admitted"}
    )
    pdc = _object(
        row["pdc"],
        {
            "case_id",
            "case_submitter_id",
            "case_status",
            "sample_id",
            "sample_submitter_id",
            "sample_status",
            "sample_type",
            "pool",
            "aliquot_id",
            "aliquot_submitter_id",
            "aliquot_status",
        },
    )
    if (
        row["metadata_candidate_not_admitted"] is not True
        or pdc["pool"] != "No"
        or pdc["sample_type"] != "Primary Tumor"
        or any(
            pdc[field] != "Qualified"
            for field in ("case_status", "sample_status", "aliquot_status")
        )
    ):
        boundary._fail()
    boundary._uuid(pdc["case_id"])
    boundary._uuid(pdc["sample_id"])
    case_label = boundary._text(pdc["case_submitter_id"])
    sample_label = boundary._text(pdc["sample_submitter_id"])
    sample_uuid = boundary._uuid(row["gdc_sample_uuid"])
    selected: list[str] = []
    gdc_cases: set[str] = set()
    for field, expected_workflow in (("rna_file", "STAR - Counts"), ("cnv_file", "AscatNGS")):
        file = _official_file(row[field])
        file_id = cast("str", file["file_id"])
        if (
            file_id not in files
            or file != files[file_id]
            or _object(file["analysis"], {"workflow_type"})["workflow_type"] != expected_workflow
        ):
            boundary._fail()
        gdc_cases.add(
            _associated_primary_sample(
                file, case_label=case_label, sample_label=sample_label, sample_uuid=sample_uuid
            )
        )
        selected.append(file_id)
    if len(gdc_cases) != 1:
        boundary._fail()
    binding = CandidateBinding(
        case_label,
        sample_label,
        sample_uuid,
        boundary._text(pdc["aliquot_submitter_id"]),
        boundary._uuid(pdc["aliquot_id"]),
        selected[0],
        selected[1],
    )
    return binding, next(iter(gdc_cases))


def _map_bindings(
    value: object, source_rows: list[object], *, choices_sha256: str, count: int
) -> None:
    mapped = boundary._record(
        value,
        {
            "schema",
            "source_candidate_bindings_sha256",
            "source_map_sha256",
            "source_map_md5",
            "qualified_metadata_candidates_before_map",
            "candidate_bindings",
            "withheld",
            "parsed_map_rows",
            "reference_assignments_excluded",
            "measurement_admitted",
        },
    )
    if (
        mapped["schema"] != "discovery-exact-tmt-channel-map-bindings/1.0.0"
        or mapped["source_candidate_bindings_sha256"] != choices_sha256
        or mapped["source_map_sha256"] != MAP_SHA256
        or mapped["source_map_md5"] != MAP_MD5
        or mapped["measurement_admitted"] is not False
        or mapped["withheld"] != []
        or boundary._integer(mapped["qualified_metadata_candidates_before_map"]) != count
    ):
        boundary._fail()
    positions: dict[str, tuple[int, str]] = {}
    plex_ids: set[int] = set()
    analytical: set[str] = set()
    for row_value in boundary._records(mapped["parsed_map_rows"], _PLEXES):
        row = boundary._record(row_value, {"plex_index", "source_row"})
        plex = boundary._integer(row["plex_index"], maximum=_PLEXES - 1)
        cells = boundary._records(row["source_row"], 15)
        if plex in plex_ids or cells[2] != "POOL" or cells[-1] != _RATIOS:
            boundary._fail()
        plex_ids.add(plex)
        boundary._text(cells[0], maximum=512)
        name = boundary._text(cells[1])
        boundary._text(cells[-2])
        if name in analytical:
            boundary._fail()
        analytical.add(name)
        for channel, cell in zip(_CHANNELS[1:], cells[3:13], strict=True):
            label = boundary._text(cell)
            if label == "POOL" or label in positions:
                boundary._fail()
            positions[label] = (plex, channel)
    references: set[int] = set()
    for reference_value in boundary._records(mapped["reference_assignments_excluded"], _PLEXES):
        reference = boundary._record(reference_value, {"plex_index", "channel", "label"})
        plex = boundary._integer(reference["plex_index"], maximum=_PLEXES - 1)
        if reference["channel"] != "126C" or reference["label"] != "POOL" or plex in references:
            boundary._fail()
        references.add(plex)
    if references != plex_ids:
        boundary._fail()
    originals = {}
    for source_row in source_rows:
        pdc = _object(_object(source_row, {"pdc"})["pdc"], {"aliquot_id"})
        originals[boundary._uuid(pdc["aliquot_id"])] = source_row
    seen: set[str] = set()
    for candidate_value in boundary._records(mapped["candidate_bindings"], count):
        candidate = boundary._record(
            candidate_value,
            {
                "candidate",
                "exact_once_in_nonreference_sample_map",
                "sample_map_occurrences",
                "metadata_candidate_not_admitted",
            },
        )
        source = _object(candidate["candidate"], {"pdc"})
        pdc = _object(source["pdc"], {"aliquot_id", "aliquot_submitter_id"})
        identifier = boundary._uuid(pdc["aliquot_id"])
        occurrence = boundary._record(
            boundary._records(candidate["sample_map_occurrences"], 1)[0], {"plex_index", "channel"}
        )
        observed = (
            boundary._integer(occurrence["plex_index"], maximum=_PLEXES - 1),
            boundary._text(occurrence["channel"]),
        )
        if (
            identifier in seen
            or source != originals.get(identifier)
            or candidate["exact_once_in_nonreference_sample_map"] is not True
            or candidate["metadata_candidate_not_admitted"] is not True
            or positions.get(boundary._text(pdc["aliquot_submitter_id"])) != observed
            or observed[1] == "126C"
        ):
            boundary._fail()
        seen.add(identifier)


def _files_manifest(
    value: object,
    files: Mapping[str, dict[str, object]],
    *,
    choices_sha256: str,
    map_bindings_sha256: str,
    count: int,
) -> dict[str, AssayInputBinding]:
    manifest = boundary._record(
        value,
        {
            "schema",
            "source_plan_sha256",
            "source_channel_bindings_sha256",
            "selected_specimens",
            "requested_files",
            "official_size_and_md5_verified_files",
            "verified_bytes",
            "files",
            "failures",
            "model_fits",
            "redistribution_status",
        },
    )
    if (
        manifest["schema"] != "frozen-discovery-GDC-downloads/1.0.0"
        or manifest["source_plan_sha256"] != choices_sha256
        or manifest["source_channel_bindings_sha256"] != map_bindings_sha256
        or manifest["failures"] != []
        or manifest["model_fits"] is not False
        or manifest["redistribution_status"] != "local_only_terms_unverified"
    ):
        boundary._fail()
    for field, expected in (
        ("selected_specimens", count),
        ("requested_files", 2 * count),
        ("official_size_and_md5_verified_files", 2 * count),
    ):
        if boundary._integer(manifest[field]) != expected:
            boundary._fail()
    result: dict[str, AssayInputBinding] = {}
    for file_value in boundary._records(manifest["files"], len(files)):
        row = boundary._record(
            file_value,
            {
                "file_id",
                "bytes",
                "md5",
                "sha256",
                "relative_path",
                "workflow",
                "official_size_and_md5_verified",
                "source_kind",
                "cached_verified",
            },
        )
        identifier = boundary._uuid(row["file_id"])
        if identifier not in files or identifier in result:
            boundary._fail()
        file = files[identifier]
        workflow = _object(file["analysis"], {"workflow_type"})["workflow_type"]
        length = boundary._integer(row["bytes"], minimum=1)
        if (
            row["relative_path"] != identifier + ".bin"
            or row["source_kind"] != "gdc"
            or type(row["cached_verified"]) is not bool
            or row["official_size_and_md5_verified"] is not True
            or length != file["file_size"]
            or row["md5"] != file["md5sum"]
            or row["workflow"] != workflow
        ):
            boundary._fail()
        result[identifier] = AssayInputBinding(
            identifier + ".bin",
            SourceLock(length, cast("str", row["md5"]), boundary._sha256(row["sha256"])),
            cast("Workflow", workflow),
        )
    total = sum(binding.lock.bytes for binding in result.values())
    if (
        boundary._integer(manifest["verified_bytes"], maximum=2 * _CANDIDATES * MAX_SOURCE_BYTES)
        != total
    ):
        boundary._fail()
    return dict(sorted(result.items()))


def _decode_discovery_plan(
    choices: object,
    mapped: object,
    manifest: object,
    *,
    choices_sha256: str,
    map_bindings_sha256: str,
    files_manifest_sha256: str,
    candidate_count: int,
) -> ExternalAdmissionPlan:
    """Private small-fixture seam; public loader always requires72 candidates."""

    for digest in (choices_sha256, map_bindings_sha256, files_manifest_sha256):
        boundary._sha256(digest)
    boundary._integer(candidate_count, minimum=1, maximum=_CANDIDATES)
    for value in (choices, mapped, manifest):
        boundary._check_json(value)
    source = boundary._record(
        choices,
        {
            "schema",
            "source_candidates_sha256",
            "source_integrity_manifest_sha256",
            "metadata_only",
            "measurement_admitted",
            "candidate_count",
            "file_count",
            "candidates",
            "GDC_paired_official_file_choices",
        },
    )
    if (
        source["schema"] != "discovery-paired-source-metadata/1.0.0"
        or source["metadata_only"] is not True
        or source["measurement_admitted"] is not False
        or boundary._integer(source["candidate_count"]) != candidate_count
        or boundary._integer(source["file_count"]) != 2 * candidate_count
    ):
        boundary._fail()
    boundary._sha256(source["source_candidates_sha256"])
    boundary._sha256(source["source_integrity_manifest_sha256"])
    files: dict[str, dict[str, object]] = {}
    for value in boundary._records(source["GDC_paired_official_file_choices"], 2 * candidate_count):
        file = _official_file(value)
        identifier = cast("str", file["file_id"])
        if identifier in files:
            boundary._fail()
        files[identifier] = file
    source_rows = boundary._records(source["candidates"], candidate_count)
    information = tuple(_pdc_candidate(row, files) for row in source_rows)
    candidates = tuple(row[0] for row in information)
    if len({row[1] for row in information}) != candidate_count:
        boundary._fail()
    for field in ("case_id", "sample_id"):
        if (
            len({_object(_object(row, {"pdc"})["pdc"], {field})[field] for row in source_rows})
            != candidate_count
        ):
            boundary._fail()
    namespaces = (
        "case_submitter_id",
        "sample_submitter_id",
        "gdc_sample_uuid",
        "protein_aliquot_submitter_id",
        "protein_aliquot_uuid",
    )
    if any(
        len({getattr(candidate, field) for candidate in candidates}) != candidate_count
        for field in namespaces
    ):
        boundary._fail()
    used = [
        identifier
        for candidate in candidates
        for identifier in (candidate.rna_file_id, candidate.cnv_file_id)
    ]
    if len(set(used)) != len(used) or set(used) != set(files):
        boundary._fail()
    _map_bindings(mapped, source_rows, choices_sha256=choices_sha256, count=candidate_count)
    bindings = _files_manifest(
        manifest,
        files,
        choices_sha256=choices_sha256,
        map_bindings_sha256=map_bindings_sha256,
        count=candidate_count,
    )
    receipt = ExternalAdmissionReceipt(
        profile_id=PROFILE_ID,
        choices_sha256=choices_sha256,
        files_manifest_sha256=files_manifest_sha256,
        candidate_count=candidate_count,
        rna_file_count=candidate_count,
        cnv_file_count=candidate_count,
        paired_file_count=2 * candidate_count,
        manifest_verified_bytes=sum(row.lock.bytes for row in bindings.values()),
        metadata_candidate_not_admitted=True,
        issuer_authentication=False,
        eligibility_admitted=False,
        measurement_bytes_reverified=False,
        limitations=(
            "Discovery source metadata is explicitly Qualified/nonpool Primary Tumor; clinical and molecular eligibility remain unadmitted.",
            "Caller-supplied file digests bind integrity/replay and do not authenticate GDC/PDC origin or re-query official ancestry.",
            "Exact captured associated-aliquot ancestry and the frozen nonreference TMT channel map are checked without alias or prefix inference.",
            "Local measurement bytes require independent size/MD5/SHA256 verification by the source readers; this plan does not parse them.",
            "The channel-map binding digest is "
            + map_bindings_sha256
            + "; the locked map digest is "
            + MAP_SHA256
            + ".",
            "No donor independence, assay-scale compatibility, biological validation or predictive performance follows from this receipt.",
        ),
    )
    return ExternalAdmissionPlan(
        tuple(
            sorted(
                candidates,
                key=lambda row: (
                    row.case_submitter_id,
                    row.sample_submitter_id,
                    row.gdc_sample_uuid,
                ),
            )
        ),
        bindings,
        receipt,
    )


def load_discovery_plan(
    *,
    choices_path: Path,
    choices_sha256: str,
    map_bindings_path: Path,
    map_bindings_sha256: str,
    files_manifest_path: Path,
    files_manifest_sha256: str,
) -> ExternalAdmissionPlan:
    """Load only the fixed72/144 discovery plan; no network or measurement reads."""

    for digest in (choices_sha256, map_bindings_sha256, files_manifest_sha256):
        boundary._sha256(digest)
    try:
        plan = _decode_discovery_plan(
            boundary._read_json(choices_path, choices_sha256),
            boundary._read_json(map_bindings_path, map_bindings_sha256),
            boundary._read_json(files_manifest_path, files_manifest_sha256),
            choices_sha256=choices_sha256,
            map_bindings_sha256=map_bindings_sha256,
            files_manifest_sha256=files_manifest_sha256,
            candidate_count=_CANDIDATES,
        )
        for binding in plan.files.values():
            if (
                boundary._snapshot((files_manifest_path.parent / binding.relative_path).lstat())[2]
                != binding.lock.bytes
            ):
                raise AdmissionPlanError("local discovery assay byte count did not match")  # noqa: TRY301
    except AdmissionPlanError:
        raise
    except (OSError, TypeError, ValueError, KeyError, RecursionError):
        raise AdmissionPlanError("captured discovery metadata was not accepted") from None
    return plan


@dataclass(frozen=True, slots=True)
class DistinctCohortReceipt:
    training_candidates: int
    test_candidates: int
    checked_identifier_namespaces: tuple[str, ...]
    case_submitter_overlaps: int
    sample_submitter_overlaps: int
    gdc_sample_uuid_overlaps: int
    protein_aliquot_submitter_overlaps: int
    protein_aliquot_uuid_overlaps: int
    assay_file_overlaps: int
    donor_independence_admitted: bool
    limitations: tuple[str, ...]


def assert_distinct_cohort_plans(
    train: ExternalAdmissionPlan, test: ExternalAdmissionPlan
) -> DistinctCohortReceipt:
    """Reject known exact overlaps; absence of overlap does not prove donor identity."""

    if not isinstance(train, ExternalAdmissionPlan) or not isinstance(test, ExternalAdmissionPlan):
        raise AdmissionPlanError("cohort separation requires admitted plan contracts")
    fields = (
        "case_submitter_id",
        "sample_submitter_id",
        "gdc_sample_uuid",
        "protein_aliquot_submitter_id",
        "protein_aliquot_uuid",
    )
    overlaps = [
        len(
            {getattr(row, field) for row in train.candidates}
            & {getattr(row, field) for row in test.candidates}
        )
        for field in fields
    ]
    train_files = set(train.files) | {
        identifier for row in train.candidates for identifier in (row.rna_file_id, row.cnv_file_id)
    }
    test_files = set(test.files) | {
        identifier for row in test.candidates for identifier in (row.rna_file_id, row.cnv_file_id)
    }
    file_overlap = len(train_files & test_files)
    if any(overlaps) or file_overlap:
        raise AdmissionPlanError("cohort plans share exact captured identifiers")
    return DistinctCohortReceipt(
        training_candidates=len(train.candidates),
        test_candidates=len(test.candidates),
        checked_identifier_namespaces=(*fields, "rna_or_cnv_file_id"),
        case_submitter_overlaps=overlaps[0],
        sample_submitter_overlaps=overlaps[1],
        gdc_sample_uuid_overlaps=overlaps[2],
        protein_aliquot_submitter_overlaps=overlaps[3],
        protein_aliquot_uuid_overlaps=overlaps[4],
        assay_file_overlaps=file_overlap,
        donor_independence_admitted=False,
        limitations=(
            "Only exact identifiers present in the shared plan contract were compared; no alias or prefix inference was performed.",
            "Unrecorded donor aliases, germline identity, shared-reference processing and biological independence were not established.",
        ),
    )


__all__ = [
    "MAP_MD5",
    "MAP_SHA256",
    "PROFILE_ID",
    "DistinctCohortReceipt",
    "assert_distinct_cohort_plans",
    "load_discovery_plan",
]
