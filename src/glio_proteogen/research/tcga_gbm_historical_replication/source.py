"""Reparse exact historical source observations; never diagnose or run a model."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from contextlib import suppress
from pathlib import Path
from typing import Literal, Never, cast
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element, ParseError

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock
from glio_proteogen.research.cptac_gbm_external_admission.source import read_verified_source
from glio_proteogen.research.cptac_gbm_rna_purity_execution.clinical import _workbook

from .contracts import (
    _FACTORY_TOKEN,
    MAX_METADATA_BYTES,
    SOURCE_ROLES,
    HistoricalPopulationQualification,
    HistoricalSourceError,
    HistoricalSourcePaths,
    ReviewedHistoricalSourceAuthority,
    _Private,
    _qualification,
    _uuid,
)

_BIO = "http://tcga.nci/bcr/xml/biospecimen/2.7"
_CLINICAL = "http://tcga.nci/bcr/xml/clinical/gbm/2.7"
_SHARED = "http://tcga.nci/bcr/xml/shared/2.7"
_SHEET = "S1A. TCGA discovery dataset"
_AUTHOR_FIELDS = {
    "A": "Case",
    "C": "Study",
    "G": "RNAseq",
    "M": "Histology",
    "N": "Grade",
    "V": "IDH status",
    "X": "IDH/codel subtype",
}
_AUTHOR_TARGET = {
    "Study": "Glioblastoma multiforme",
    "RNAseq": "Yes",
    "Histology": "glioblastoma",
    "Grade": "G4",
    "IDH status": "WT",
    "IDH/codel subtype": "IDHwt",
}


def _require(condition: bool) -> None:  # noqa: FBT001 - closed source assertions.
    if not condition:
        raise HistoricalSourceError("historical source evidence was not admitted")


class _HistoricalEvidence(_Private):
    __slots__ = ("_values",)
    _values: tuple[
        str,
        str,
        str,
        int,
        str,
        tuple[tuple[str, str], ...],
        Literal["unknown", "Tumor"],
        Literal["unknown", "Primary"],
    ]

    def __init__(
        self,
        case_id: str,
        case_barcode: str,
        file_id: str,
        file_bytes: int,
        file_md5: str,
        *,
        lineage: tuple[tuple[str, str], ...],
        xml_tissue_type: Literal["unknown", "Tumor"],
        xml_tumor_descriptor: Literal["unknown", "Primary"],
    ) -> None:
        object.__setattr__(
            self,
            "_values",
            (
                case_id,
                case_barcode,
                file_id,
                file_bytes,
                file_md5,
                lineage,
                xml_tissue_type,
                xml_tumor_descriptor,
            ),
        )

    def __setattr__(self, name: str, value: object) -> Never:
        raise AttributeError("historical evidence is immutable")

    def __delattr__(self, name: str) -> Never:
        raise AttributeError("historical evidence is immutable")

    @property
    def case_id(self) -> str:
        return self._values[0]

    @property
    def case_barcode(self) -> str:
        return self._values[1]

    @property
    def file_id(self) -> str:
        return self._values[2]

    @property
    def file_bytes(self) -> int:
        return self._values[3]

    @property
    def file_md5(self) -> str:
        return self._values[4]

    @property
    def lineage(self) -> tuple[tuple[str, str], ...]:
        return self._values[5]

    @property
    def xml_tissue_type(self) -> Literal["unknown", "Tumor"]:
        return self._values[6]

    @property
    def xml_tumor_descriptor(self) -> Literal["unknown", "Primary"]:
        return self._values[7]


def _one(values: object) -> dict[str, object]:
    if type(values) is not list or len(values) != 1:
        raise HistoricalSourceError("historical source cardinality is invalid")
    return _object(values[0])


def _object(value: object) -> dict[str, object]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        raise HistoricalSourceError("historical source object is invalid")
    return cast("dict[str, object]", value)


def _string(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > 8192
        or value.strip() != value
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise HistoricalSourceError("historical source text is invalid")
    return value


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for name, value in values:
        _require(name not in out)
        out[name] = value
    return out


def _json(payload: bytes) -> dict[str, object]:
    _require(type(payload) is bytes and 0 < len(payload) <= MAX_METADATA_BYTES)
    result = _object(
        json.loads(
            payload,
            object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    )
    _require("errors" not in result)
    _require(result.get("warnings", {}) == {})
    return result


def _field(
    parent: Element,
    name: str,
    namespace: str = _BIO,
    *,
    empty: bool = False,
    allow_missing: bool = False,
) -> str:
    values = parent.findall(f"{{{namespace}}}{name}")
    _require(len(values) == 1 and len(values[0]) == 0)
    text = values[0].text or ""
    if empty:
        _require(text == "")
    elif text or not allow_missing:
        _string(text)
    return text


def _xml(payload: bytes, *, root_namespace: str) -> Element:
    _require(type(payload) is bytes and 0 < len(payload) <= MAX_METADATA_BYTES)
    root = SafeET.fromstring(payload, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    _require(root.tag == f"{{{root_namespace}}}tcga_bcr" and sum(1 for _ in root.iter()) <= 16384)
    patients = root.findall(f"{{{root_namespace}}}patient")
    _require(len(patients) == 1)
    return patients[0]


def _author(payload: bytes, case_barcode: str) -> None:
    workbook = _workbook(payload)
    _require(_SHEET in workbook and len(workbook[_SHEET]) >= 3)
    rows = workbook[_SHEET]
    _require(all(rows[1].get(column) == name for column, name in _AUTHOR_FIELDS.items()))
    matching = [row for row in rows[2:] if row.get("A") == case_barcode]
    _require(len(matching) == 1)
    row = matching[0]
    _require(
        all(
            row.get(column) == _AUTHOR_TARGET[name]
            for column, name in _AUTHOR_FIELDS.items()
            if name != "Case"
        )
    )


def _join_impl(payloads: dict[str, bytes], *, target_file_id: str) -> _HistoricalEvidence:  # noqa: PLR0915 - exact source joins.
    _require(type(payloads) is dict and set(payloads) == set(SOURCE_ROLES))
    selected_id = _uuid(target_file_id)
    metadata = _json(payloads["gdc_metadata"])
    data = _object(metadata.get("data"))
    hits = data.get("hits")
    if type(hits) is not list or not 1 <= len(hits) <= 256:
        raise HistoricalSourceError("historical file inventory is invalid")
    chosen = [_object(row) for row in hits if _uuid(_object(row).get("file_id")) == selected_id]
    _require(len(chosen) == 1)
    file = chosen[0]
    _require(_uuid(file.get("id")) == selected_id)
    for key, expected in (
        ("access", "open"),
        ("state", "released"),
        ("data_format", "TSV"),
        ("data_type", "Gene Expression Quantification"),
        ("experimental_strategy", "RNA-Seq"),
    ):
        _require(file.get(key) == expected)
    _require(_object(file.get("analysis")).get("workflow_type") == "STAR - Counts")
    size = file.get("file_size")
    md5 = file.get("md5sum")
    _require(type(size) is int and 0 < size <= 201326592)
    _require(type(md5) is str and re.fullmatch(r"[0-9a-f]{32}", md5) is not None)
    case = _one(file.get("cases"))
    _require(_object(case.get("project")).get("project_id") == "TCGA-GBM")
    case_id, case_barcode = _uuid(case.get("case_id")), _string(case.get("submitter_id"))
    _require(re.fullmatch(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}", case_barcode) is not None)
    _author(payloads["author_workbook"], case_barcode)
    clinical = _xml(payloads["clinical_xml"], root_namespace=_CLINICAL)
    bio = _xml(payloads["biospecimen_xml"], root_namespace=_BIO)
    # Every identity in the source hierarchy must be one-to-one, including
    # branches other than the selected RNA chain. No identifier prefix joins.
    for kind in ("sample", "portion", "analyte", "aliquot"):
        nodes = tuple(bio.iter(f"{{{_BIO}}}{kind}"))
        identifiers = tuple(_uuid(_field(node, f"bcr_{kind}_uuid")) for node in nodes)
        barcodes = tuple(_field(node, f"bcr_{kind}_barcode") for node in nodes)
        _require(len(set(identifiers)) == len(nodes) and len(set(barcodes)) == len(nodes))
    for patient in (clinical, bio):
        _require(_uuid(_field(patient, "bcr_patient_uuid", _SHARED)) == case_id)
        _require(_field(patient, "bcr_patient_barcode", _SHARED) == case_barcode)
    _require(_field(clinical, "histological_type", _SHARED) == "Untreated primary (de novo) GBM")
    _require(_field(clinical, "history_of_neoadjuvant_treatment", _SHARED) == "No")
    _require(_field(clinical, "prior_glioma", _CLINICAL) == "NO")
    sample = _one(case.get("samples"))
    portion = _one(sample.get("portions"))
    analyte = _one(portion.get("analytes"))
    aliquot = _one(analyte.get("aliquots"))
    _require(
        sample.get("sample_type") == "Primary Tumor"
        and sample.get("tissue_type") == "Tumor"
        and sample.get("tumor_descriptor") == "Primary"
    )
    _require(analyte.get("analyte_type") == "RNA")
    lineage = tuple(
        (_uuid(row.get(f"{kind}_id")), _string(row.get("submitter_id")))
        for kind, row in (
            ("sample", sample),
            ("portion", portion),
            ("analyte", analyte),
            ("aliquot", aliquot),
        )
    )
    parents = [bio]
    xml_tissue_type: Literal["unknown", "Tumor"] = "unknown"
    xml_tumor_descriptor: Literal["unknown", "Primary"] = "unknown"
    for index, (container, kind) in enumerate(
        (
            ("samples", "sample"),
            ("portions", "portion"),
            ("analytes", "analyte"),
            ("aliquots", "aliquot"),
        )
    ):
        children = [
            child
            for parent in parents
            for group in parent.findall(f"{{{_BIO}}}{container}")
            for child in group.findall(f"{{{_BIO}}}{kind}")
        ]
        matching = [
            child
            for child in children
            if _uuid(_field(child, f"bcr_{kind}_uuid")) == lineage[index][0]
            and _field(child, f"bcr_{kind}_barcode") == lineage[index][1]
        ]
        _require(len(matching) == 1)
        parents = matching
        if kind == "sample":
            tissue = _field(matching[0], "tissue_type", allow_missing=True)
            descriptor = _field(matching[0], "tumor_descriptor", allow_missing=True)
            _require(
                _field(matching[0], "sample_type") == "Primary Tumor"
                and tissue in ("", "Tumor")
                and descriptor in ("", "Primary")
            )
            xml_tissue_type = "Tumor" if tissue == "Tumor" else "unknown"
            xml_tumor_descriptor = "Primary" if descriptor == "Primary" else "unknown"
            _field(matching[0], "days_to_collection", empty=True)
            _field(matching[0], "days_to_sample_procurement", _SHARED, empty=True)
        if kind == "analyte":
            _require(_field(matching[0], "analyte_type") == "RNA")
    association = _json(payloads["file_association"])
    _require(association.get("warnings", {}) == {})
    associated_file = _object(association.get("data"))
    _require(_uuid(associated_file.get("file_id")) == selected_id)
    entity = _one(associated_file.get("associated_entities"))
    _require(
        entity.get("entity_type") == "aliquot"
        and _uuid(entity.get("entity_id")) == lineage[-1][0]
        and _string(entity.get("entity_submitter_id")) == lineage[-1][1]
        and _uuid(entity.get("case_id")) == case_id
    )
    return _HistoricalEvidence(
        case_id,
        case_barcode,
        selected_id,
        cast("int", size),
        cast("str", md5),
        lineage=lineage,
        xml_tissue_type=xml_tissue_type,
        xml_tumor_descriptor=xml_tumor_descriptor,
    )


def _join_sources(payloads: dict[str, bytes], *, target_file_id: str) -> _HistoricalEvidence:
    """Private synthetic-test seam: validate joins, never authenticate a publisher."""
    result: _HistoricalEvidence | None = None
    with suppress(
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
        OverflowError,
        DefusedXmlException,
        ParseError,
        RecursionError,
    ):
        result = _join_impl(payloads, target_file_id=target_file_id)
    if result is None:
        raise HistoricalSourceError("historical source evidence was not admitted")
    return result


def _path_snapshot(path: Path) -> tuple[int, int, int, int]:
    absolute = path.absolute()
    for part in (absolute, *absolute.parents):
        info = part.lstat()
        _require(
            not stat.S_ISLNK(info.st_mode)
            and not (
                getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            )
        )
    info = absolute.stat()
    _require(stat.S_ISREG(info.st_mode))
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _authority_values(authority: ReviewedHistoricalSourceAuthority) -> dict[str, object]:
    return {
        "review_id": authority.review_id,
        "resources": tuple(
            {
                "role": r.role,
                "origin": r.origin,
                "version": r.version,
                "bytes": r.lock.bytes,
                "md5": r.lock.md5,
                "sha256": r.lock.sha256,
            }
            for r in authority.resources
        ),
        "reviewed_rna": None
        if authority.reviewed_rna is None
        else {
            "file_id": _uuid(authority.reviewed_rna.file_id),
            "bytes": authority.reviewed_rna.lock.bytes,
            "md5": authority.reviewed_rna.lock.md5,
            "sha256": authority.reviewed_rna.lock.sha256,
        },
    }


def _admit(
    paths: HistoricalSourcePaths,
    *,
    authority: ReviewedHistoricalSourceAuthority,
    target_file_id: str,
) -> HistoricalPopulationQualification:
    _require(
        type(paths) is HistoricalSourcePaths
        and type(authority) is ReviewedHistoricalSourceAuthority
    )
    HistoricalSourcePaths(*(getattr(paths, role) for role in SOURCE_ROLES))
    ReviewedHistoricalSourceAuthority(
        authority.resources, authority.review_id, authority.reviewed_rna
    )
    snapshots = tuple(_path_snapshot(getattr(paths, role)) for role in SOURCE_ROLES)
    _require(len({(row[0], row[1]) for row in snapshots}) == len(SOURCE_ROLES))
    payloads = {
        r.role: read_verified_source(getattr(paths, r.role), r.lock, max_bytes=MAX_METADATA_BYTES)
        for r in authority.resources
    }
    _require(snapshots == tuple(_path_snapshot(getattr(paths, role)) for role in SOURCE_ROLES))
    evidence = _join_sources(payloads, target_file_id=target_file_id)
    association_resource = authority.resources[-1]
    _require(
        _uuid(urlsplit(association_resource.origin).path.removeprefix("/files/"))
        == evidence.file_id
    )
    if authority.reviewed_rna is not None:
        _require(
            _uuid(authority.reviewed_rna.file_id) == evidence.file_id
            and authority.reviewed_rna.lock.bytes == evidence.file_bytes
            and authority.reviewed_rna.lock.md5 == evidence.file_md5
        )
    binding = sha256_digest(
        {
            "authority": _authority_values(authority),
            "evidence": evidence._values,
            "snapshots": snapshots,
            "paths": tuple(str(getattr(paths, role).absolute()) for role in SOURCE_ROLES),
        }
    )
    return _qualification(
        paths=paths,
        authority=authority,
        evidence=evidence,
        binding=binding,
        fixture=False,
        xml_tissue_type=evidence.xml_tissue_type,
        xml_tumor_descriptor=evidence.xml_tumor_descriptor,
    )


def admit_historical_population(
    paths: HistoricalSourcePaths,
    *,
    authority: ReviewedHistoricalSourceAuthority,
    target_file_id: str,
) -> HistoricalPopulationQualification:
    """Reverify trusted source locks and raw exact joins, without assay access.

    Authority is independently reviewed operator configuration, not a request
    semantic flag or saved receipt. Its issuer review is a stated trust boundary.
    """
    result: HistoricalPopulationQualification | None = None
    with suppress(
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
        OverflowError,
        RecursionError,
    ):
        result = _admit(paths, authority=authority, target_file_id=target_file_id)
    if result is None:
        raise HistoricalSourceError("historical source qualification was not admitted")
    return result


def _fixture_qualification(
    payloads: dict[str, bytes], *, target_file_id: str, rna_lock: SourceLock
) -> HistoricalPopulationQualification:
    """Test-only joins; the production RNA verifier rejects this capability."""
    evidence = _join_sources(payloads, target_file_id=target_file_id)
    _require(
        type(rna_lock) is SourceLock
        and rna_lock.bytes == evidence.file_bytes
        and rna_lock.md5 == evidence.file_md5
    )
    return _qualification(
        paths=None,
        authority=None,
        evidence=evidence,
        binding=sha256_digest({"fixture": evidence._values}),
        fixture=True,
        xml_tissue_type=evidence.xml_tissue_type,
        xml_tumor_descriptor=evidence.xml_tumor_descriptor,
    )


def verify_rna_payload(
    payload: bytes, *, qualification: HistoricalPopulationQualification
) -> SourceLock:
    """Revalidate live source authority and separately reviewed RNA bytes.

    No RNA is parsed or read from a path here. A newly computed hash never
    substitutes for the independently reviewed acquisition SHA in the authority.
    """
    result: SourceLock | None = None
    try:
        _require(
            type(qualification) is HistoricalPopulationQualification
            and qualification._marker is _FACTORY_TOKEN
        )
        _require(
            qualification.receipt.source_evidence_kind == "reviewed_official_capture"
            and qualification._paths is not None
            and qualification._authority is not None
            and type(qualification._evidence) is _HistoricalEvidence
        )
        authority = qualification._authority
        paths = qualification._paths
        evidence = qualification._evidence
        if authority is None or paths is None or type(evidence) is not _HistoricalEvidence:
            raise HistoricalSourceError("historical qualification has no source authority")
        reviewed_rna = authority.reviewed_rna
        if reviewed_rna is None:
            raise HistoricalSourceError(
                "historical qualification has no reviewed RNA byte authority"
            )
        fresh = _admit(
            paths,
            authority=authority,
            target_file_id=evidence.file_id,
        )
        fresh_evidence = fresh._evidence
        _require(
            type(fresh_evidence) is _HistoricalEvidence
            and type(evidence._values) is tuple
            and evidence._values == fresh_evidence._values
        )
        _require(
            fresh._binding == qualification._binding
            and canonical_json_bytes(fresh.receipt) == canonical_json_bytes(qualification.receipt)
        )
        lock = reviewed_rna.lock
        _require(type(payload) is bytes and len(payload) == lock.bytes)
        _require(
            hashlib.md5(payload, usedforsecurity=False).hexdigest() == lock.md5
            and hashlib.sha256(payload).hexdigest() == lock.sha256
        )
        result = lock
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
        OverflowError,
        RecursionError,
    ):
        pass
    if result is None:
        raise HistoricalSourceError("historical RNA source binding was not verified")
    return result
