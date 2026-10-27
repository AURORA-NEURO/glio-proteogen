"""Admit exact public CPTAC clinical sources without inventing IDH-wildtype status.

Source bytes and selected specimen ancestry are checked before a clinical hold is
returned. This module never opens a path, reads RNA, or executes a fitted model.
Clinical negatives, author somatic alterations, source withdrawal and specimen QC
remain separate observations. The unchanged integrated-diagnosis gate stays closed.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import stat
import tarfile
import zipfile
import zlib
from collections import Counter
from pathlib import PurePosixPath
from typing import Final, Literal, Never, Self, SupportsIndex, cast
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from pydantic import Field, model_validator

from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.cptac_gbm_rna_purity_admission.context import (
    COMPONENTS,
    ComponentStateCounts,
    ContextState,
    ContextStateCounts,
)

from .contracts import ExecutionError, canonical_bytes, digest, validate_digest

_N: Final = 72
_MAX_SOURCE_BYTES: Final = 4 * 1_024 * 1_024
_MAX_EXPANDED_BYTES: Final = 20 * 1_024 * 1_024
_MAX_ROWS: Final = 2_048
_MAX_TEXT: Final = 8_192
_SHEET_NS: Final = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL_NS: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
_DOCUMENT_REL: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_METADATA_PREFIX: Final = "GBM_Metadata_CancerCell2021/"
_PATIENT_MEMBER: Final = (
    _METADATA_PREFIX + "S057_S048_CPTAC_GBM_Discovery_Cohort_Clinical_Data_Feb2021_r2.xlsx"
)
_MAP_MEMBER: Final = (
    _METADATA_PREFIX
    + "S057_S048_CPTAC_GBM_Discovery_Cohort_TMT11_CaseID_SampleID_AliquotID_Map_Feb2021_r2.xlsx"
)
_CORE_MEMBER: Final = "Clinical_Data_Subtypes/clinical_data_core.v5.1.tsv.gz"
_SUBTYPE_MEMBER: Final = "Clinical_Data_Subtypes/all_subtypes.v5.1.tsv"
_IDH_PERFORMED: Final = "ancillary_studies_IDH1/2_mutational_analysis_performed"
_IDH_RESULT: Final = "ancillary_studies_IDH1/2_mutation_identified"
_IDH_DETAIL: Final = "ancillary_studies_if_IDH1/2_mutation_yes_specify"
_IDH_METHOD: Final = "ancillary_studies_IDH1/2_mutational_testing_method"
_IDH_FIELDS: Final = (_IDH_PERFORMED, _IDH_RESULT, _IDH_DETAIL, _IDH_METHOD)
_IHC_METHODS: Final = frozenset(
    ("IHC", "IHC with Dianova antiboy R132H", "Immunohistochemistry", "immunohistochemical stain")
)
_MOLECULAR_METHODS: Final = frozenset(
    (
        "ARMS",
        "Cancer Hotspot analysis by Next Generation sequencing ",
        "Massively parallel sequencing",
        "Next Gen Sequencing",
        "Next Generation Sequencing",
        "Next Generation sequencing",
        "Next generation sequencing",
        "Tempus xT assay measuring by hybrid capture next-generaton sequencing.",
    )
)
_PATIENT_FIELDS: Final = (
    "case_id",
    "case_withdrawn",
    "histologic_type",
    *_IDH_FIELDS,
    "history_of_cancer",
    "history_of_any_treatment",
)
_CORE_FIELDS: Final = (
    "case_id",
    "expert_path_review",
    "expert_path_review_details",
    "excluded_in_downstream_analysis",
    "exclusion_reason",
    "tumor_reoccur_after_treatment",
)
_BIO_FIELDS: Final = (
    "case_id",
    "specimen_id",
    "tissue_type",
    "histological_type_eligible",
    "consistent_with_diagnostic_report",
)
_MAP_FIELDS: Final = (
    "Case ID (Participant ID)",
    "Parent Sample ID(s)",
    "Aliquot ID",
    "Sample type",
)
_SOURCE_ROLES: Final = (
    "metadata_archive",
    "subtypes_archive",
    "pdc_biospecimens",
    "gdc_clinical",
    "pdc_status",
    "gdc_status",
)
ComponentStates = tuple[
    ContextState, ContextState, ContextState, ContextState, ContextState, ContextState, ContextState
]


class ClinicalAdmissionError(ExecutionError):
    """Sanitized public-source integrity, schema or ancestry admission failure."""


class ClinicalSourceLock(FrozenModel):
    role: str
    filename: str
    bytes: int = Field(ge=1, le=_MAX_SOURCE_BYTES)
    md5: str = Field(pattern=r"^[0-9a-f]{32}$")
    sha256: Sha256Digest


SOURCE_LOCKS: Final = (
    ClinicalSourceLock(
        role="metadata_archive",
        filename="GBM_Metadata_CancerCell2021.tar.gz",
        bytes=1_264_802,
        md5="bcf5af8507ff395b676541bcab2f1f4f",
        sha256="sha256:887c424edcfbd7093456cba9439a1a0389c76a991cc66c83afd732397642e54c",
    ),
    ClinicalSourceLock(
        role="subtypes_archive",
        filename="Clinical_Data_Subtypes.tar.gz",
        bytes=14_970,
        md5="4671506646bd705ecee24838b646b91c",
        sha256="sha256:8398c978f55654e10131e10d59fdfe9d2d2345dfec2f9bed96167f388e46d80d",
    ),
    ClinicalSourceLock(
        role="pdc_biospecimens",
        filename="PDC000204.v1.taxon-biospecimens.response.raw.private.json",
        bytes=41_645,
        md5="f74d46271702ed9f8de6702ede9cd39d",
        sha256="sha256:7318d6b510bbaf80b9bc504bfbeedd1174fe9a790d6b2859f54baedfd7426985",
    ),
    ClinicalSourceLock(
        role="gdc_clinical",
        filename="GDC.exact72.clinical-biospecimen.response.raw.private.json",
        bytes=659_690,
        md5="b17268c6baa10442f3513459337032c5",
        sha256="sha256:f67974de441f1c36c3424395accf3908f3f8d9600c13cf4407bd32878868b84d",
    ),
    ClinicalSourceLock(
        role="pdc_status",
        filename="PDC000204.v1.source-status.response.raw.private.json",
        bytes=39_112,
        md5="37abf618caade08de71a7a865b3989a1",
        sha256="sha256:553c20904e70d288118338613aad4477d323d453dc362c93a2eef68ecbb31e10",
    ),
    ClinicalSourceLock(
        role="gdc_status",
        filename="GDC.exact72.source-status.response.raw.private.json",
        bytes=10_911,
        md5="9f92a759788776d0cacfe1c9c5dedb10",
        sha256="sha256:73b68c2a0772890b8bdac8afcb29058611edf605c92c8c380ebcf69d8e12cc25",
    ),
)


def _require(condition: bool, message: str) -> None:  # noqa: FBT001 -- boundary assertion
    if not condition:
        raise ClinicalAdmissionError(message)


def _text(value: object, *, identifier: bool = False) -> str:
    _require(type(value) is str and len(value) <= _MAX_TEXT, "clinical text is invalid")
    result = cast("str", value)
    _require(not any(ord(c) < 32 and c not in "\r\n\t" for c in result), "clinical text is invalid")
    if identifier:
        _require(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", result) is not None,
            "clinical source identifier is invalid",
        )
    return result


class _Private:
    __slots__ = ()

    def __setattr__(self, _name: str, _value: object) -> Never:
        raise AttributeError("private clinical evidence is immutable")

    def __delattr__(self, _name: str) -> Never:
        raise AttributeError("private clinical evidence is immutable")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} private>"

    def __getstate__(self) -> Never:
        raise TypeError("private clinical evidence cannot be implicitly serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> Never:
        raise TypeError("private clinical evidence cannot be implicitly serialized")


class ClinicalTarget(_Private):
    """An exact inherited candidate; UUID ancestry is derived from verified sources."""

    __slots__ = ("_values",)
    _values: tuple[str, str, str, str, str, str]

    def __init__(
        self,
        *,
        case_key: str,
        sample_key: str,
        gdc_sample_id: str,
        protein_aliquot_key: str,
        protein_aliquot_id: str,
        lineage_digest: str,
    ) -> None:
        values = tuple(
            _text(value, identifier=True)
            for value in (
                case_key,
                sample_key,
                gdc_sample_id,
                protein_aliquot_key,
                protein_aliquot_id,
            )
        )
        object.__setattr__(self, "_values", (*values, validate_digest(lineage_digest)))

    @property
    def case_key(self) -> str:
        return self._values[0]

    @property
    def sample_key(self) -> str:
        return self._values[1]

    @property
    def gdc_sample_id(self) -> str:
        return self._values[2]

    @property
    def protein_aliquot_key(self) -> str:
        return self._values[3]

    @property
    def protein_aliquot_id(self) -> str:
        return self._values[4]

    @property
    def lineage_digest(self) -> str:
        return self._values[5]

    def _document(self) -> dict[str, str]:
        return dict(
            zip(
                (
                    "case_key",
                    "sample_key",
                    "gdc_sample_id",
                    "protein_aliquot_key",
                    "protein_aliquot_id",
                    "lineage_digest",
                ),
                self._values,
                strict=True,
            )
        )


class ClinicalSources(_Private):
    """Immutable byte snapshots, checked against six exact role-specific locks."""

    __slots__ = ("_payloads",)
    _payloads: tuple[bytes, ...]

    def __init__(
        self,
        *,
        metadata_archive: bytes,
        subtypes_archive: bytes,
        pdc_biospecimens: bytes,
        gdc_clinical: bytes,
        pdc_status: bytes,
        gdc_status: bytes,
    ) -> None:
        values = (
            metadata_archive,
            subtypes_archive,
            pdc_biospecimens,
            gdc_clinical,
            pdc_status,
            gdc_status,
        )
        _require(
            all(type(value) is bytes and 1 <= len(value) <= _MAX_SOURCE_BYTES for value in values),
            "clinical source byte type or bound is invalid",
        )
        object.__setattr__(self, "_payloads", values)


def _checked_sources(sources: ClinicalSources) -> dict[str, bytes]:
    _require(type(sources) is ClinicalSources, "exact clinical source snapshots are required")
    try:
        values = sources._payloads
        _require(
            type(values) is tuple and len(values) == len(SOURCE_LOCKS),
            "clinical source role inventory is invalid",
        )
        _require(
            tuple(lock.role for lock in SOURCE_LOCKS) == _SOURCE_ROLES,
            "clinical source lock inventory is invalid",
        )
        for payload, lock in zip(values, SOURCE_LOCKS, strict=True):
            _require(
                type(payload) is bytes
                and len(payload) == lock.bytes
                and hashlib.sha256(payload).hexdigest() == lock.sha256.removeprefix("sha256:")
                and hashlib.md5(payload, usedforsecurity=False).hexdigest() == lock.md5,
                "clinical source integrity or role is invalid",
            )
        return dict(zip(_SOURCE_ROLES, values, strict=True))
    except (AttributeError, TypeError, ValueError):
        raise ClinicalAdmissionError("clinical source integrity or role is invalid") from None


def _gunzip(payload: bytes) -> bytes:
    try:
        decoder = zlib.decompressobj(31)
        raw = decoder.decompress(payload, _MAX_EXPANDED_BYTES + 1)
        _require(
            len(raw) <= _MAX_EXPANDED_BYTES
            and decoder.eof
            and not decoder.unused_data
            and not decoder.unconsumed_tail,
            "clinical compressed source is invalid or exceeds its bound",
        )
    except zlib.error:
        raise ClinicalAdmissionError("clinical compressed source is invalid") from None
    return raw


def _safe_member(name: str) -> None:
    path = PurePosixPath(name)
    _require(
        bool(name)
        and "\\" not in name
        and not path.is_absolute()
        and ".." not in path.parts
        and ":" not in name,
        "clinical archive member path is invalid",
    )


def _archive(payload: bytes) -> dict[str, bytes]:
    try:
        with tarfile.open(fileobj=io.BytesIO(_gunzip(payload)), mode="r:") as archive:
            members = archive.getmembers()
            _require(
                1 <= len(members) <= 128
                and sum(member.size for member in members) <= _MAX_EXPANDED_BYTES,
                "clinical archive inventory exceeds its bound",
            )
            _require(
                len({member.name for member in members}) == len(members),
                "clinical archive members are duplicated",
            )
            output = {}
            for member in members:
                _safe_member(member.name)
                _require(
                    member.isfile() or member.isdir(), "clinical archive member type is invalid"
                )
                if member.isfile():
                    stream = archive.extractfile(member)
                    _require(stream is not None, "clinical archive member is unreadable")
                    output[member.name] = cast("io.BufferedReader", stream).read(
                        _MAX_EXPANDED_BYTES + 1
                    )
                    _require(
                        len(output[member.name]) == member.size,
                        "clinical archive member is truncated",
                    )
    except (tarfile.TarError, EOFError, OSError, ValueError):
        raise ClinicalAdmissionError("clinical archive is invalid") from None
    return output


def _xml(payload: bytes) -> Element:
    try:
        return SafeET.fromstring(
            payload, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except (SafeET.ParseError, DefusedXmlException, ValueError):
        raise ClinicalAdmissionError("clinical workbook XML is invalid") from None


def _workbook(payload: bytes) -> dict[str, list[dict[str, str]]]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            _require(
                1 <= len(members) <= 128
                and sum(member.file_size for member in members) <= _MAX_EXPANDED_BYTES,
                "clinical workbook inventory exceeds its bound",
            )
            _require(
                len({member.filename for member in members}) == len(members),
                "clinical workbook members are duplicated",
            )
            for member in members:
                _safe_member(member.filename)
                _require(
                    not member.flag_bits & 1
                    and member.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    and not stat.S_ISLNK(member.external_attr >> 16),
                    "clinical workbook member type is invalid",
                )
                _require(
                    not any(
                        part in member.filename.lower()
                        for part in ("vbaproject", "externallink", "oleobject", "activex")
                    ),
                    "clinical workbook active content is forbidden",
                )
                if member.filename.endswith(".rels"):
                    _require(
                        all(
                            row.attrib.get("TargetMode") != "External"
                            for row in _xml(archive.read(member))
                        ),
                        "clinical workbook external relationship is forbidden",
                    )
            strings = []
            if "xl/sharedStrings.xml" in archive.namelist():
                strings = [
                    "".join(row.itertext())
                    for row in _xml(archive.read("xl/sharedStrings.xml")).findall("s:si", _SHEET_NS)
                ]
            relationships = _xml(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {
                row.attrib["Id"]: row.attrib["Target"]
                for row in relationships.findall(f"{{{_REL_NS}}}Relationship")
            }
            sheets = _xml(archive.read("xl/workbook.xml")).find("s:sheets", _SHEET_NS)
            _require(
                sheets is not None and 1 <= len(sheets) <= 16,
                "clinical workbook sheet inventory is invalid",
            )
            result = {}
            for sheet in cast("Element", sheets):
                name = _text(sheet.attrib["name"])
                _require(bool(name) and len(name) <= 128, "clinical workbook sheet name is invalid")
                _require(name not in result, "clinical workbook sheet names are duplicated")
                target = targets[sheet.attrib[f"{{{_DOCUMENT_REL}}}id"]]
                member_name = (
                    target.removeprefix("/") if target.startswith("/xl/") else "xl/" + target
                )
                _safe_member(member_name)
                rows = _xml(archive.read(member_name)).findall("s:sheetData/s:row", _SHEET_NS)
                _require(len(rows) <= _MAX_ROWS, "clinical workbook row bound exceeded")
                data = []
                for row in rows:
                    cells: dict[str, str] = {}
                    for cell in row.findall("s:c", _SHEET_NS):
                        _require(
                            cell.find("s:f", _SHEET_NS) is None and cell.attrib.get("t") != "e",
                            "clinical workbook formula or error cell is forbidden",
                        )
                        match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]*)", cell.attrib["r"])
                        _require(match is not None, "clinical workbook cell coordinate is invalid")
                        column = cast("re.Match[str]", match)[1]
                        _require(
                            column not in cells and len(cells) < 512,
                            "clinical workbook columns are invalid",
                        )
                        value_node = cell.find("s:v", _SHEET_NS)
                        inline = cell.find("s:is", _SHEET_NS)
                        value = (
                            value_node.text or ""
                            if value_node is not None
                            else "".join(inline.itertext())
                            if inline is not None
                            else ""
                        )
                        if cell.attrib.get("t") == "s":
                            _require(
                                re.fullmatch(r"[0-9]+", value) is not None
                                and int(value) < len(strings),
                                "clinical workbook shared string is invalid",
                            )
                            value = strings[int(value)]
                        cells[column] = _text(value)
                    data.append(cells)
                result[name] = data
    except (zipfile.BadZipFile, KeyError, TypeError, ValueError, OSError, RuntimeError):
        raise ClinicalAdmissionError("clinical workbook is invalid") from None
    return result


def _table(rows: list[dict[str, str]], required: tuple[str, ...]) -> list[dict[str, str]]:
    headers = [
        (index, {column: value for column, value in row.items() if value})
        for index, row in enumerate(rows)
        if set(required) <= set(row.values())
    ]
    _require(len(headers) == 1, "clinical table header is absent or ambiguous")
    index, header = headers[0]
    _require(len(set(header.values())) == len(header), "clinical table headers are duplicated")
    return [
        {name: row.get(column, "") for column, name in header.items()}
        for row in rows[index + 1 :]
        if any(row.values())
    ]


def _tsv(payload: bytes, required: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        reader = csv.DictReader(
            io.StringIO(payload.decode("utf-8-sig")), delimiter="\t", strict=True
        )
        fields = reader.fieldnames
        _require(
            fields is not None and len(fields) == len(set(fields)) and set(required) <= set(fields),
            "clinical text table header is invalid",
        )
        rows = list(reader)
        _require(
            1 <= len(rows) <= _MAX_ROWS
            and all(
                None not in row and all(type(value) is str for value in row.values())
                for row in rows
            ),
            "clinical text table shape is invalid",
        )
        return [{_text(key): _text(value) for key, value in row.items()} for row in rows]
    except (csv.Error, UnicodeError, TypeError, ValueError):
        raise ClinicalAdmissionError("clinical text table is invalid") from None


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        _require(key not in result, "clinical JSON object keys are duplicated")
        result[key] = value
    return result


def _json_rows(payload: bytes, collection: str) -> list[dict[str, object]]:
    try:
        doc = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
        _require(
            type(doc) is dict and "errors" not in doc and type(doc.get("data")) is dict,
            "clinical JSON envelope is invalid",
        )
        data = doc["data"]
        rows = data.get(collection)
        _require(
            type(rows) is list
            and 1 <= len(rows) <= _MAX_ROWS
            and all(type(row) is dict for row in rows),
            "clinical JSON record collection is invalid",
        )
        if collection == "hits":
            pagination = data.get("pagination")
            _require(
                type(pagination) is dict
                and type(pagination.get("total")) is int
                and pagination["total"] == len(rows)
                and pagination.get("from") == 0,
                "clinical JSON pagination is incomplete",
            )
        return cast("list[dict[str, object]]", rows)
    except (ValueError, UnicodeError, TypeError, RecursionError, KeyError):
        raise ClinicalAdmissionError("clinical JSON is invalid") from None


def _one(
    rows: list[dict[str, object]] | list[dict[str, str]], field: str, value: str
) -> dict[str, object]:
    selected = [row for row in rows if row.get(field) == value]
    _require(len(selected) == 1, "clinical source identifier join is absent or ambiguous")
    return cast("dict[str, object]", selected[0])


def _rows(value: object) -> list[dict[str, object]]:
    _require(
        type(value) is list
        and 1 <= len(cast("list[object]", value)) <= _MAX_ROWS
        and all(type(row) is dict for row in cast("list[object]", value)),
        "clinical nested source records are invalid",
    )
    return cast("list[dict[str, object]]", value)


class ClinicalObservation(_Private):
    """Original field values and locations; no implicit JSON or dataclass export."""

    __slots__ = ("_values",)
    _values: tuple[str, str, str, str]

    def __init__(self, source_role: str, source_location: str, field: str, value: str) -> None:
        _require(source_role in _SOURCE_ROLES, "clinical observation source role is invalid")
        object.__setattr__(
            self, "_values", (source_role, _text(source_location), _text(field), _text(value))
        )

    @property
    def source_role(self) -> str:
        return self._values[0]

    @property
    def source_location(self) -> str:
        return self._values[1]

    @property
    def field(self) -> str:
        return self._values[2]

    @property
    def value(self) -> str:
        return self._values[3]

    def _document(self) -> dict[str, str]:
        return dict(
            zip(("source_role", "source_location", "field", "value"), self._values, strict=True)
        )


def _state(states: ComponentStates) -> ContextState:
    return next(
        (
            state
            for state in (ContextState.CONFLICTING, ContextState.OUT_OF_SCOPE, ContextState.UNKNOWN)
            if state in states
        ),
        ContextState.SOURCE_SUPPORTED,
    )


class ClinicalCase(_Private):
    __slots__ = ("_digest", "_flags", "_hold", "_observations", "_states", "_target")
    _target: ClinicalTarget
    _states: ComponentStates
    _observations: tuple[ClinicalObservation, ...]
    _hold: tuple[str, ...]
    _flags: tuple[bool, bool, bool, bool]
    _digest: str

    def __init__(
        self,
        target: ClinicalTarget,
        states: ComponentStates,
        observations: tuple[ClinicalObservation, ...],
        holds: tuple[str, ...],
        flags: tuple[bool, bool, bool, bool],
    ) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_states", states)
        object.__setattr__(self, "_observations", observations)
        object.__setattr__(self, "_hold", holds)
        object.__setattr__(self, "_flags", flags)
        object.__setattr__(
            self,
            "_digest",
            digest(
                {
                    "target": target._document(),
                    "component_states": states,
                    "observations": [observation._document() for observation in observations],
                    "source_hold_reasons": holds,
                    "flags": flags,
                }
            ),
        )

    @property
    def target(self) -> ClinicalTarget:
        return self._target

    @property
    def component_states(self) -> ComponentStates:
        return self._states

    @property
    def state(self) -> ContextState:
        return _state(self._states)

    @property
    def source_hold(self) -> bool:
        return bool(self._hold)

    @property
    def source_hold_reasons(self) -> tuple[str, ...]:
        return self._hold

    @property
    def observations(self) -> tuple[ClinicalObservation, ...]:
        return self._observations

    @property
    def observations_digest(self) -> str:
        return self._digest

    @property
    def clinical_idh_positive(self) -> bool:
        return self._flags[0]

    @property
    def author_idh1_alteration(self) -> bool:
        return self._flags[1]

    @property
    def idh_alteration_reported(self) -> bool:
        return any(self._flags[:2])


class ClinicalAdmissionReceipt(FrozenModel):
    schema_version: Literal["cptac-gbm-source-clinical-admission/1.0.0"] = (
        "cptac-gbm-source-clinical-admission/1.0.0"
    )
    planned_cases: Literal[72] = 72
    exact_case_joins: Literal[72] = 72
    exact_protein_map_joins: Literal[72] = 72
    exact_gdc_specimen_joins: Literal[72] = 72
    exact_author_biospecimen_joins: int = Field(ge=0, le=_N)
    missing_author_biospecimen_rows: int = Field(ge=0, le=_N)
    explicit_integrated_diagnosis_cases: Literal[0] = 0
    target_context_ready_cases: Literal[0] = 0
    clinical_idh_positive_cases: int = Field(ge=0, le=_N)
    author_idh1_alteration_cases: int = Field(ge=0, le=_N)
    reported_idh_alteration_union_cases: int = Field(ge=0, le=_N)
    clinical_negative_cases: int = Field(ge=0, le=_N)
    molecular_method_negative_cases: int = Field(ge=0, le=_N)
    ihc_only_negative_cases: int = Field(ge=0, le=_N)
    unknown_method_negative_cases: int = Field(ge=0, le=_N)
    no_clinical_result_cases: int = Field(ge=0, le=_N)
    source_hold_cases: int = Field(ge=0, le=_N)
    source_hold_reason_counts: tuple[tuple[str, int], ...]
    state_counts: ContextStateCounts
    component_state_counts: tuple[ComponentStateCounts, ...]
    source_locks: tuple[ClinicalSourceLock, ...]
    source_set_digest: Sha256Digest
    ordered_axis_digest: Sha256Digest
    evidence_digest: Sha256Digest
    clinical_validation: Literal[False] = False
    raw_count_processing_proven: Literal[False] = False
    operational_declarations_inferred: Literal[False] = False
    models_executed: Literal[False] = False
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def conserved(self) -> Self:
        _require(
            self.exact_author_biospecimen_joins + self.missing_author_biospecimen_rows == _N
            and self.state_counts.total == _N
            and self.state_counts.source_supported == 0,
            "clinical receipt case counts are not conserved",
        )
        _require(
            self.clinical_negative_cases
            + self.clinical_idh_positive_cases
            + self.no_clinical_result_cases
            == _N
            and self.molecular_method_negative_cases
            + self.ihc_only_negative_cases
            + self.unknown_method_negative_cases
            == self.clinical_negative_cases,
            "clinical receipt IDH counts are not conserved",
        )
        _require(
            max(self.clinical_idh_positive_cases, self.author_idh1_alteration_cases)
            <= self.reported_idh_alteration_union_cases
            <= min(_N, self.clinical_idh_positive_cases + self.author_idh1_alteration_cases),
            "clinical receipt alteration counts are not conserved",
        )
        _require(
            tuple(row.component for row in self.component_state_counts) == COMPONENTS[:7]
            and all(row.states.total == _N for row in self.component_state_counts)
            and self.component_state_counts[2].states.unknown == _N
            and self.component_state_counts[1].states.source_supported == 0
            and self.component_state_counts[1].states.out_of_scope
            == self.clinical_idh_positive_cases
            and self.component_state_counts[1].states.unknown
            == _N - self.clinical_idh_positive_cases
            and all(row.states.unknown == _N for row in self.component_state_counts[4:]),
            "clinical receipt component counts are not conserved",
        )
        _require(
            tuple(lock.role for lock in self.source_locks) == _SOURCE_ROLES
            and self.source_locks == SOURCE_LOCKS
            and digest([lock.model_dump(mode="json") for lock in self.source_locks])
            == self.source_set_digest,
            "clinical receipt source binding is invalid",
        )
        reasons = self.source_hold_reason_counts
        allowed = {
            "historical_case_withdrawal",
            "historical_withdrawal_current_release_disagreement",
            "current_source_status_not_qualified",
            "author_analysis_exclusion",
        }
        _require(
            tuple(sorted({reason for reason, _ in reasons}))
            == tuple(reason for reason, _ in reasons)
            and all(
                reason in allowed and type(count) is int and 1 <= count <= self.source_hold_cases
                for reason, count in reasons
            )
            and self.source_hold_cases
            <= sum(count for _, count in reasons)
            <= len(allowed) * self.source_hold_cases,
            "clinical receipt hold counts are not conserved",
        )
        values = self.model_dump(mode="json")
        values.pop("receipt_digest")
        _require(digest(values) == self.receipt_digest, "clinical receipt seal is invalid")
        return self


class ClinicalAdmission(_Private):
    __slots__ = ("_cases", "_receipt")
    _cases: tuple[ClinicalCase, ...]
    _receipt: ClinicalAdmissionReceipt

    def __init__(self, cases: tuple[ClinicalCase, ...], receipt: ClinicalAdmissionReceipt) -> None:
        object.__setattr__(self, "_cases", cases)
        object.__setattr__(self, "_receipt", receipt)

    @property
    def cases(self) -> tuple[ClinicalCase, ...]:
        return self._cases

    @property
    def receipt(self) -> ClinicalAdmissionReceipt:
        return self._receipt


def _counts(states: tuple[ContextState, ...]) -> ContextStateCounts:
    return ContextStateCounts(**{state.value: states.count(state) for state in ContextState})


def _source_tables(payloads: dict[str, bytes]) -> dict[str, list[dict[str, object]]]:
    metadata = _archive(payloads["metadata_archive"])
    subtypes = _archive(payloads["subtypes_archive"])
    _require(
        {_PATIENT_MEMBER, _MAP_MEMBER} <= set(metadata)
        and {_CORE_MEMBER, _SUBTYPE_MEMBER} <= set(subtypes),
        "clinical source archive required members are absent",
    )
    clinical = _workbook(metadata[_PATIENT_MEMBER])
    mapping = _workbook(metadata[_MAP_MEMBER])
    try:
        tables: dict[str, list[dict[str, object]]] = {
            "patient": cast(
                "list[dict[str, object]]",
                _table(clinical["Patient_Clinical_Attributes"], _PATIENT_FIELDS),
            ),
            "biospecimen": cast(
                "list[dict[str, object]]", _table(clinical["Biospecimen_Attributes"], _BIO_FIELDS)
            ),
            "mapping": cast(
                "list[dict[str, object]]", _table(mapping["GBM TMT Plexes"], _MAP_FIELDS)
            ),
            "core": cast(
                "list[dict[str, object]]", _tsv(_gunzip(subtypes[_CORE_MEMBER]), _CORE_FIELDS)
            ),
            "subtypes": cast(
                "list[dict[str, object]]",
                _tsv(subtypes[_SUBTYPE_MEMBER], ("case", "sample_type", "IDH1_alter_status")),
            ),
        }
    except KeyError:
        raise ClinicalAdmissionError("clinical source worksheet is absent") from None
    for role in ("pdc_biospecimens", "pdc_status", "gdc_clinical", "gdc_status"):
        tables[role] = _json_rows(
            payloads[role], "hits" if role.startswith("gdc") else "biospecimenPerStudy"
        )
    _require(
        len(tables["gdc_clinical"]) == _N and len(tables["gdc_status"]) == _N,
        "clinical GDC case axis is not exact72",
    )
    return tables


def _observe(
    role: str, location: str, row: dict[str, object], fields: tuple[str, ...]
) -> list[ClinicalObservation]:
    result = []
    for field in fields:
        _require(field in row, "clinical required source field is absent")
        value = row[field]
        literal = str(value) if type(value) in (bool, int) or value is None else _text(value)
        result.append(ClinicalObservation(role, location, field, literal))
    return result


def _admit_case(target: ClinicalTarget, tables: dict[str, list[dict[str, object]]]) -> ClinicalCase:
    patient = _one(tables["patient"], "case_id", target.case_key)
    core = _one(tables["core"], "case_id", target.case_key)
    subtype = _one(tables["subtypes"], "case", target.case_key)
    mapping = _one(tables["mapping"], "Aliquot ID", target.protein_aliquot_key)
    pdc = _one(tables["pdc_biospecimens"], "aliquot_id", target.protein_aliquot_id)
    pdc_status = _one(tables["pdc_status"], "aliquot_id", target.protein_aliquot_id)
    gdc = _one(tables["gdc_clinical"], "submitter_id", target.case_key)
    gdc_status = _one(tables["gdc_status"], "case_id", _text(gdc.get("case_id"), identifier=True))
    sample = _one(_rows(gdc.get("samples")), "sample_id", target.gdc_sample_id)
    _require(
        mapping.get("Case ID (Participant ID)") == target.case_key
        and mapping.get("Parent Sample ID(s)") == target.sample_key
        and mapping.get("Sample type") == "tumor",
        "author case-to-selected-specimen map disagrees",
    )
    for row in (pdc, pdc_status):
        _require(
            row.get("case_submitter_id") == target.case_key
            and row.get("sample_submitter_id") == target.sample_key
            and row.get("aliquot_submitter_id") == target.protein_aliquot_key,
            "PDC selected specimen ancestry disagrees",
        )
    _require(
        all(
            pdc.get(field) == pdc_status.get(field)
            for field in ("case_id", "sample_id", "aliquot_id")
        )
        and sample.get("submitter_id") == target.sample_key
        and gdc_status.get("submitter_id") == target.case_key,
        "clinical source UUID ancestry disagrees",
    )
    diagnoses = _rows(gdc.get("diagnoses"))
    _require(len(diagnoses) == 1, "clinical diagnosis lineage is ambiguous")
    diagnosis = diagnoses[0]
    _require(
        type(diagnosis.get("diagnosis_is_primary_disease")) is bool,
        "clinical primary-disease semantic type is invalid",
    )
    _require(
        patient.get("histologic_type") == "Glioblastoma"
        and diagnosis.get("primary_diagnosis") == "Glioblastoma",
        "clinical historical diagnosis is outside the admitted source label",
    )
    performed, result = patient[_IDH_PERFORMED], patient[_IDH_RESULT]
    _require(
        (performed, result) in (("Yes", "No"), ("Yes", "Yes"), ("No", ""), ("Unknown", "")),
        "clinical IDH test result semantics are invalid",
    )
    _require(
        patient.get("case_withdrawn") in ("Yes", "No")
        and subtype.get("IDH1_alter_status") in ("NA", "Missense"),
        "clinical source status semantics are invalid",
    )
    biospecimen = [
        row
        for row in tables["biospecimen"]
        if row.get("case_id") == target.case_key and row.get("specimen_id") == target.sample_key
    ]
    _require(len(biospecimen) <= 1, "author selected biospecimen lineage is ambiguous")
    holds = []
    _require(
        core.get("excluded_in_downstream_analysis") in ("TRUE", "FALSE"),
        "author clinical inclusion status is invalid",
    )
    if core["excluded_in_downstream_analysis"] == "TRUE":
        holds.append("author_analysis_exclusion")
    if patient["case_withdrawn"] == "Yes":
        holds.append("historical_case_withdrawal")
        if gdc_status.get("state") == "released" and pdc_status.get("case_status") == "Qualified":
            holds.append("historical_withdrawal_current_release_disagreement")
    if gdc_status.get("state") != "released" or any(
        pdc_status.get(field) != "Qualified"
        for field in ("case_status", "sample_status", "aliquot_status")
    ):
        holds.append("current_source_status_not_qualified")
    positive = result == "Yes"
    altered = subtype["IDH1_alter_status"] == "Missense"
    method = _text(patient[_IDH_METHOD])
    molecular_negative = result == "No" and method in _MOLECULAR_METHODS
    ihc_negative = result == "No" and method in _IHC_METHODS
    if result == "No":
        _require(
            method in _MOLECULAR_METHODS | _IHC_METHODS | {"Unknown"},
            "clinical negative test method is unrecognized",
        )
    supported, unknown = ContextState.SOURCE_SUPPORTED, ContextState.UNKNOWN
    disease_state = ContextState.OUT_OF_SCOPE if positive else unknown
    states: ComponentStates = (
        supported if pdc.get("taxon") == "Homo sapiens" else ContextState.OUT_OF_SCOPE,
        disease_state,
        unknown,
        supported
        if sample.get("specimen_type") == "Solid Tissue"
        and sample.get("tissue_type") == "Tumor"
        and pdc.get("sample_type") == "Primary Tumor"
        else unknown,
        unknown,
        unknown,
        unknown,
    )
    observations = [
        *_observe(
            "metadata_archive",
            _PATIENT_MEMBER + ":Patient_Clinical_Attributes",
            patient,
            _PATIENT_FIELDS,
        ),
        *_observe("metadata_archive", _MAP_MEMBER + ":GBM TMT Plexes", mapping, _MAP_FIELDS),
        *_observe("subtypes_archive", _CORE_MEMBER, core, _CORE_FIELDS),
        *_observe(
            "subtypes_archive",
            _SUBTYPE_MEMBER,
            subtype,
            ("case", "sample_type", "IDH1_alter_status"),
        ),
        *_observe(
            "pdc_biospecimens",
            "data.biospecimenPerStudy:selected_aliquot",
            pdc,
            ("case_id", "sample_id", "aliquot_id", "taxon", "primary_site", "sample_type"),
        ),
        *_observe(
            "gdc_clinical",
            "data.hits:selected_case.diagnoses",
            diagnosis,
            ("primary_diagnosis", "diagnosis_is_primary_disease"),
        ),
        *_observe(
            "gdc_clinical",
            "data.hits:selected_case.samples:selected_sample",
            sample,
            (
                "sample_id",
                "sample_type",
                "tissue_type",
                "specimen_type",
                "preservation_method",
                "tumor_descriptor",
            ),
        ),
        *_observe(
            "pdc_status",
            "data.biospecimenPerStudy:selected_aliquot",
            pdc_status,
            ("case_status", "sample_status", "aliquot_status"),
        ),
        *_observe("gdc_status", "data.hits:selected_case", gdc_status, ("state",)),
    ]
    if biospecimen:
        observations.extend(
            _observe(
                "metadata_archive",
                _PATIENT_MEMBER + ":Biospecimen_Attributes",
                biospecimen[0],
                _BIO_FIELDS,
            )
        )
    return ClinicalCase(
        target,
        states,
        tuple(observations),
        tuple(holds),
        (positive, altered, molecular_negative, ihc_negative),
    )


def admit_clinical_context(
    targets: tuple[ClinicalTarget, ...], sources: ClinicalSources
) -> ClinicalAdmission:
    """Conserve all 72 inherited candidates and every source hold before RNA access."""
    _require(
        type(targets) is tuple
        and len(targets) == _N
        and all(type(target) is ClinicalTarget for target in targets),
        "exact72 clinical target axis is required",
    )
    try:
        targets = tuple(ClinicalTarget(**target._document()) for target in targets)
        _require(
            all(
                len({getattr(target, field) for target in targets}) == _N
                for field in (
                    "case_key",
                    "sample_key",
                    "gdc_sample_id",
                    "protein_aliquot_key",
                    "protein_aliquot_id",
                    "lineage_digest",
                )
            ),
            "clinical target axis has duplicate identities",
        )
        tables = _source_tables(_checked_sources(sources))
        cases = tuple(_admit_case(target, tables) for target in targets)
    except ClinicalAdmissionError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        raise ClinicalAdmissionError("clinical source admission failed") from None
    negative = sum(
        any(
            observation.field == _IDH_RESULT and observation.value == "No"
            for observation in case.observations
        )
        for case in cases
    )
    molecular = sum(case._flags[2] for case in cases)
    ihc = sum(case._flags[3] for case in cases)
    biospecimen_count = sum(
        any(
            observation.source_location.endswith(":Biospecimen_Attributes")
            for observation in case.observations
        )
        for case in cases
    )
    hold_counts = Counter(reason for case in cases for reason in case.source_hold_reasons)
    values: dict[str, object] = {
        "schema_version": "cptac-gbm-source-clinical-admission/1.0.0",
        "planned_cases": _N,
        "exact_case_joins": _N,
        "exact_protein_map_joins": _N,
        "exact_gdc_specimen_joins": _N,
        "exact_author_biospecimen_joins": biospecimen_count,
        "missing_author_biospecimen_rows": _N - biospecimen_count,
        "explicit_integrated_diagnosis_cases": 0,
        "target_context_ready_cases": 0,
        "clinical_idh_positive_cases": sum(case.clinical_idh_positive for case in cases),
        "author_idh1_alteration_cases": sum(case.author_idh1_alteration for case in cases),
        "reported_idh_alteration_union_cases": sum(case.idh_alteration_reported for case in cases),
        "clinical_negative_cases": negative,
        "molecular_method_negative_cases": molecular,
        "ihc_only_negative_cases": ihc,
        "unknown_method_negative_cases": negative - molecular - ihc,
        "no_clinical_result_cases": _N
        - negative
        - sum(case.clinical_idh_positive for case in cases),
        "source_hold_cases": sum(case.source_hold for case in cases),
        "source_hold_reason_counts": tuple(sorted(hold_counts.items())),
        "state_counts": _counts(tuple(case.state for case in cases)).model_dump(mode="json"),
        "component_state_counts": [
            ComponentStateCounts(
                component=component,
                states=_counts(tuple(case.component_states[index] for case in cases)),
            ).model_dump(mode="json")
            for index, component in enumerate(COMPONENTS[:7])
        ],
        "source_locks": [lock.model_dump(mode="json") for lock in SOURCE_LOCKS],
        "source_set_digest": digest([lock.model_dump(mode="json") for lock in SOURCE_LOCKS]),
        "ordered_axis_digest": digest([target._document() for target in targets]),
        "evidence_digest": digest([case.observations_digest for case in cases]),
        "clinical_validation": False,
        "raw_count_processing_proven": False,
        "operational_declarations_inferred": False,
        "models_executed": False,
    }
    receipt = ClinicalAdmissionReceipt.model_validate_json(
        canonical_bytes({**values, "receipt_digest": digest(values)})
    )
    return ClinicalAdmission(cases, receipt)


__all__ = [
    "SOURCE_LOCKS",
    "ClinicalAdmission",
    "ClinicalAdmissionError",
    "ClinicalAdmissionReceipt",
    "ClinicalCase",
    "ClinicalObservation",
    "ClinicalSourceLock",
    "ClinicalSources",
    "ClinicalTarget",
    "admit_clinical_context",
]
