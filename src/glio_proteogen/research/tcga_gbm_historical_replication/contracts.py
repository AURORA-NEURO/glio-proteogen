"""Source-only historical research authority, separate from clinical qualification.

Operator source authority is an explicit trust input. A self-sealed request or
saved qualification receipt does not establish official origin or diagnosis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Never, SupportsIndex
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import field_validator

from glio_proteogen.kernel.models import FrozenModel
from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock

PROFILE_ID: Final = "tcga-gbm-historical-star-projection/1.0.0"
POPULATION_BASIS: Final = "author2016_histologic_gbm_g4_idhwt_and_case_denovo"
SOURCE_ROLES: Final = (
    "author_workbook",
    "clinical_xml",
    "biospecimen_xml",
    "gdc_metadata",
    "file_association",
)
OFFICIAL_AUTHOR_URL: Final = "https://api.gdc.cancer.gov/data/a0886693-4c6e-40de-9cb1-8bfcb4bb30a7"
OFFICIAL_AUTHOR_LOCK: Final = SourceLock(
    398944,
    "76f76d786f355d1e562abbf65ca71584",
    "84e1b493d045dd0794f2d2dcba77d533311751b5d2e3caa7989a141cba0dfa29",
)
MAX_METADATA_BYTES: Final = 4 * 1024 * 1024


class HistoricalSourceError(ValueError):
    """Sanitized source integrity, role, lineage or population rejection."""


def _text(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or len(value) > 8192
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise HistoricalSourceError("invalid historical source authority text")
    return value


def _uuid(value: object) -> str:
    if (
        type(value) is not str
        or re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value) is None
    ):
        raise HistoricalSourceError("invalid historical source identifier")
    return str(UUID(value))


class _Private:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} private>"

    def __getstate__(self) -> Never:
        raise TypeError("private historical source authority cannot be serialized")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        raise TypeError("private historical source authority cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class HistoricalSourcePaths(_Private):
    author_workbook: Path
    clinical_xml: Path
    biospecimen_xml: Path
    gdc_metadata: Path
    file_association: Path

    def __post_init__(self) -> None:
        if any(not isinstance(getattr(self, role), Path) for role in SOURCE_ROLES):
            raise HistoricalSourceError("historical source paths are invalid")


@dataclass(frozen=True, slots=True, repr=False)
class HistoricalResourceAuthority(_Private):
    role: str
    origin: str
    version: str
    lock: SourceLock

    def __post_init__(self) -> None:
        if self.role not in SOURCE_ROLES or type(self.lock) is not SourceLock:
            raise HistoricalSourceError("historical resource role is invalid")
        SourceLock(self.lock.bytes, self.lock.md5, self.lock.sha256)
        if self.lock.bytes > MAX_METADATA_BYTES:
            raise HistoricalSourceError("historical metadata source bound exceeded")
        _text(self.version)
        parsed = urlsplit(_text(self.origin))
        if (
            parsed.scheme != "https"
            or parsed.netloc != "api.gdc.cancer.gov"
            or parsed.fragment
            or parsed.username is not None
        ):
            raise HistoricalSourceError("historical source origin is outside the reviewed provider")
        if self.role == "author_workbook":
            if self.origin != OFFICIAL_AUTHOR_URL or self.lock != OFFICIAL_AUTHOR_LOCK:
                raise HistoricalSourceError(
                    "historical author source differs from the fixed publication"
                )
        elif self.role in ("clinical_xml", "biospecimen_xml"):
            if not parsed.path.startswith("/data/") or parsed.query:
                raise HistoricalSourceError("historical XML origin is invalid")
            _uuid(parsed.path.removeprefix("/data/"))
        elif self.role == "gdc_metadata":
            if parsed.path not in ("/files", "/files/"):
                raise HistoricalSourceError("historical file metadata origin is invalid")
        else:
            if not parsed.path.startswith("/files/"):
                raise HistoricalSourceError("historical direct file association origin is invalid")
            _uuid(parsed.path.removeprefix("/files/"))


@dataclass(frozen=True, slots=True, repr=False)
class ReviewedRnaAuthority(_Private):
    file_id: str
    lock: SourceLock

    def __post_init__(self) -> None:
        _uuid(self.file_id)
        if type(self.lock) is not SourceLock:
            raise HistoricalSourceError("reviewed RNA byte authority is invalid")
        SourceLock(self.lock.bytes, self.lock.md5, self.lock.sha256)


@dataclass(frozen=True, slots=True, repr=False)
class ReviewedHistoricalSourceAuthority(_Private):
    """Trusted operator configuration, never an untrusted eligibility request.

    The operator must independently review acquisition origins and exact byte
    locks. The factory rechecks contents and joins; hashes alone do not prove an
    issuer. The fixed publication anchor cannot be replaced by this authority.
    """

    resources: tuple[HistoricalResourceAuthority, ...]
    review_id: str
    reviewed_rna: ReviewedRnaAuthority | None = None

    def __post_init__(self) -> None:
        if (
            type(self.resources) is not tuple
            or any(type(r) is not HistoricalResourceAuthority for r in self.resources)
            or tuple(r.role for r in self.resources) != SOURCE_ROLES
        ):
            raise HistoricalSourceError(
                "historical authority requires the closed ordered source roles"
            )
        for resource in self.resources:
            HistoricalResourceAuthority(
                resource.role, resource.origin, resource.version, resource.lock
            )
        if len({r.lock.sha256 for r in self.resources}) != len(SOURCE_ROLES):
            raise HistoricalSourceError("historical source roles cannot alias content")
        _text(self.review_id)
        if self.reviewed_rna is not None:
            if type(self.reviewed_rna) is not ReviewedRnaAuthority:
                raise HistoricalSourceError("historical reviewed RNA authority is invalid")
            ReviewedRnaAuthority(self.reviewed_rna.file_id, self.reviewed_rna.lock)


class HistoricalPopulationReceipt(FrozenModel):
    """Hash-free source scope, not a clinical diagnosis or reusable authority."""

    profile_id: Literal["tcga-gbm-historical-star-projection/1.0.0"] = PROFILE_ID
    population_basis: Literal["author2016_histologic_gbm_g4_idhwt_and_case_denovo"] = (
        POPULATION_BASIS
    )
    source_evidence_kind: Literal["reviewed_official_capture", "synthetic_fixture"]
    source_origin_authority: Literal["trusted_operator_review"] = "trusted_operator_review"
    specimen_material_basis: Literal[
        "file_specific_gdc_tumor_and_original_xml_primary_tumor_role"
    ] = "file_specific_gdc_tumor_and_original_xml_primary_tumor_role"
    original_xml_tissue_type: Literal["unknown", "Tumor"]
    original_xml_tumor_descriptor: Literal["unknown", "Primary"]
    specimen_collection_timepoint: Literal["unknown"] = "unknown"
    specimen_treatment_exposure: Literal["unknown"] = "unknown"
    formal_integrated_diagnosis_established: Literal[False] = False
    who2021_reclassification_performed: Literal[False] = False
    original_cptac_gate_changed: Literal[False] = False
    inference_executed: Literal[False] = False

    @field_validator(
        "formal_integrated_diagnosis_established",
        "who2021_reclassification_performed",
        "original_cptac_gate_changed",
        "inference_executed",
        mode="before",
    )
    @classmethod
    def exact_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("historical source qualification does not grant clinical authority")
        return value


_FACTORY_TOKEN = object()


class HistoricalPopulationQualification(_Private):
    """Factory-owned transient evidence; receipts cannot reconstruct this object."""

    __slots__ = ("_authority", "_binding", "_evidence", "_marker", "_paths", "_receipt")
    _authority: ReviewedHistoricalSourceAuthority | None
    _paths: HistoricalSourcePaths | None
    _evidence: object
    _binding: str
    _marker: object
    _receipt: HistoricalPopulationReceipt

    def __init__(self) -> None:
        raise TypeError("historical qualifications require source admission")

    def __setattr__(self, name: str, value: object) -> Never:
        raise AttributeError("historical source qualification is immutable")

    def __delattr__(self, name: str) -> Never:
        raise AttributeError("historical source qualification is immutable")

    @property
    def receipt(self) -> HistoricalPopulationReceipt:
        return self._receipt


def _qualification(
    *,
    paths: HistoricalSourcePaths | None,
    authority: ReviewedHistoricalSourceAuthority | None,
    evidence: object,
    binding: str,
    fixture: bool,
    xml_tissue_type: Literal["unknown", "Tumor"],
    xml_tumor_descriptor: Literal["unknown", "Primary"],
) -> HistoricalPopulationQualification:
    result = object.__new__(HistoricalPopulationQualification)
    for name, value in (
        ("_paths", paths),
        ("_authority", authority),
        ("_evidence", evidence),
        ("_binding", binding),
        ("_marker", _FACTORY_TOKEN),
        (
            "_receipt",
            HistoricalPopulationReceipt(
                source_evidence_kind="synthetic_fixture"
                if fixture
                else "reviewed_official_capture",
                original_xml_tissue_type=xml_tissue_type,
                original_xml_tumor_descriptor=xml_tumor_descriptor,
            ),
        ),
    ):
        object.__setattr__(result, name, value)
    return result
