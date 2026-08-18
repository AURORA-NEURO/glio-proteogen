"""Bounded client for public Proteomic Data Commons study metadata.

This client intentionally stops at source metadata.  It does not fetch cohort
files, interpret measurements, or emit biological claims.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from urllib.parse import urlparse

from .provenance import SourceReference, canonical_json_bytes, sha256_digest

PDC_ENDPOINT: Final = "https://pdc.cancer.gov/graphql"
PDC_QUERY: Final = (
    '{ study(pdc_study_id: "{study_id}") { study_id pdc_study_id '
    "study_submitter_id project_id study_name study_description program_name "
    "project_name disease_type primary_site analytical_fraction experiment_type "
    "cases_count aliquots_count } }"
)
PDC_TERMS: Final = (
    "Public PDC GraphQL metadata response; verify current API terms at "
    "https://pdc.cancer.gov/pdc-docs/api-documentation"
)
_ALLOWED_HOSTS: Final = frozenset({"pdc.cancer.gov", "proteomic.datacommons.cancer.gov"})
_MAX_TIMEOUT_SECONDS: Final = 60.0
_MAX_RESPONSE_BYTES: Final = 4 * 1024 * 1024
_PDC_ID_LENGTH: Final = 9
_HTTP_OK: Final = 200


class PDCError(ValueError):
    """Raised when a bounded PDC request or response is unsafe or malformed."""


type Transport = Callable[[str, bytes, float, str, int], tuple[int, bytes, str]]


@dataclass(frozen=True, slots=True)
class PDCClientConfig:
    """Network and response limits for one metadata client."""

    endpoint: str = PDC_ENDPOINT
    timeout_seconds: float = 10.0
    max_response_bytes: int = 256 * 1024
    user_agent: str = "glio-proteogen-research-metadata/0.1"

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
            raise PDCError("PDC endpoint must be an allow-listed HTTPS host")
        if not 0.0 < self.timeout_seconds <= _MAX_TIMEOUT_SECONDS:
            raise PDCError("timeout must be greater than zero and at most 60 seconds")
        if not 0 < self.max_response_bytes <= _MAX_RESPONSE_BYTES:
            raise PDCError("response cap is outside the bounded range")
        if not self.user_agent.strip():
            raise PDCError("user agent is required")


@dataclass(frozen=True, slots=True)
class PDCStudyMetadata:
    """Typed metadata fields returned by the public study lookup."""

    study_id: str
    pdc_study_id: str
    study_submitter_id: str
    project_id: str
    study_name: str
    study_description: str
    program_name: str
    project_name: str
    disease_type: str
    primary_site: str
    analytical_fraction: str
    experiment_type: str
    cases_count: int
    aliquots_count: int

    @classmethod
    def from_dict(cls, value: object) -> PDCStudyMetadata:
        if not isinstance(value, dict):
            raise PDCError("PDC study record must be an object")
        text_fields = (
            "study_id",
            "pdc_study_id",
            "study_submitter_id",
            "project_id",
            "study_name",
            "study_description",
            "program_name",
            "project_name",
            "disease_type",
            "primary_site",
            "analytical_fraction",
            "experiment_type",
        )
        text: dict[str, str] = {}
        for field in text_fields:
            candidate = value.get(field)
            if not isinstance(candidate, str) or not candidate.strip():
                raise PDCError(f"PDC study field {field!r} must be non-empty text")
            text[field] = candidate
        counts: dict[str, int] = {}
        for field in ("cases_count", "aliquots_count"):
            candidate = value.get(field)
            if isinstance(candidate, bool) or not isinstance(candidate, int) or candidate < 0:
                raise PDCError(f"PDC study field {field!r} must be a non-negative integer")
            counts[field] = candidate
        return cls(
            study_id=text["study_id"],
            pdc_study_id=text["pdc_study_id"],
            study_submitter_id=text["study_submitter_id"],
            project_id=text["project_id"],
            study_name=text["study_name"],
            study_description=text["study_description"],
            program_name=text["program_name"],
            project_name=text["project_name"],
            disease_type=text["disease_type"],
            primary_site=text["primary_site"],
            analytical_fraction=text["analytical_fraction"],
            experiment_type=text["experiment_type"],
            cases_count=counts["cases_count"],
            aliquots_count=counts["aliquots_count"],
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "aliquots_count": self.aliquots_count,
            "analytical_fraction": self.analytical_fraction,
            "cases_count": self.cases_count,
            "disease_type": self.disease_type,
            "experiment_type": self.experiment_type,
            "primary_site": self.primary_site,
            "program_name": self.program_name,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "pdc_study_id": self.pdc_study_id,
            "study_description": self.study_description,
            "study_id": self.study_id,
            "study_name": self.study_name,
            "study_submitter_id": self.study_submitter_id,
        }


@dataclass(frozen=True, slots=True)
class PDCSnapshot:
    """A bounded, content-addressed metadata response."""

    metadata: PDCStudyMetadata
    endpoint: str
    query: str
    query_sha256: str
    response_sha256: str
    response_bytes: int
    source_reference: SourceReference

    @property
    def digest(self) -> str:
        return sha256_digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "endpoint": self.endpoint,
            "metadata": self.metadata.as_dict(),
            "query": self.query,
            "query_sha256": self.query_sha256,
            "response_bytes": self.response_bytes,
            "response_sha256": self.response_sha256,
            "source_reference": self.source_reference.as_dict(),
        }


def _default_transport(
    url: str,
    payload: bytes,
    timeout_seconds: float,
    user_agent: str,
    max_response_bytes: int,
) -> tuple[int, bytes, str]:
    request = urllib.request.Request(  # noqa: S310
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": user_agent,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            body = response.read(max_response_bytes + 1)
            content_type = response.headers.get("Content-Type", "")
            return response.status, body, content_type
    except (urllib.error.URLError, TimeoutError) as error:
        raise PDCError("PDC metadata request failed") from error


class PDCMetadataClient:
    """Fetch one small public study record with strict bounds and provenance."""

    def __init__(
        self, config: PDCClientConfig | None = None, transport: Transport | None = None
    ) -> None:
        self._config = config or PDCClientConfig()
        self._transport = transport or _default_transport

    @staticmethod
    def build_query(study_id: str) -> str:
        if (
            not study_id.startswith("PDC")
            or len(study_id) != _PDC_ID_LENGTH
            or not study_id[3:].isdigit()
        ):
            raise PDCError("study id must match the bounded PDC###### form")
        return PDC_QUERY.replace("{study_id}", study_id)

    def fetch(self, study_id: str, *, retrieved_at: str | None = None) -> PDCSnapshot:
        query = self.build_query(study_id)
        payload = canonical_json_bytes({"query": query})
        status, response, content_type = self._transport(
            self._config.endpoint,
            payload,
            self._config.timeout_seconds,
            self._config.user_agent,
            self._config.max_response_bytes,
        )
        if status != _HTTP_OK:
            raise PDCError(f"PDC returned HTTP status {status}")
        if len(response) > self._config.max_response_bytes:
            raise PDCError("PDC response exceeds the configured byte cap")
        if "json" not in content_type.lower():
            raise PDCError("PDC response is not declared as JSON")
        try:
            decoded = json.loads(response)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PDCError("PDC response is not valid UTF-8 JSON") from error
        metadata = self._parse_response(decoded, study_id)
        timestamp = retrieved_at or datetime.now(UTC).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
        source = SourceReference(
            source_id=f"pdc:{study_id}:metadata",
            locator=self._config.endpoint,
            media_type="application/json",
            sha256=sha256_digest(response),
            byte_length=len(response),
            retrieved_at=timestamp,
            license_or_terms=PDC_TERMS,
        )
        return PDCSnapshot(
            metadata=metadata,
            endpoint=self._config.endpoint,
            query=query,
            query_sha256=sha256_digest(query),
            response_sha256=sha256_digest(response),
            response_bytes=len(response),
            source_reference=source,
        )

    @staticmethod
    def _parse_response(value: object, study_id: str) -> PDCStudyMetadata:
        if not isinstance(value, dict):
            raise PDCError("PDC response root must be an object")
        if value.get("errors"):
            raise PDCError("PDC returned a GraphQL error")
        data = value.get("data")
        if not isinstance(data, dict):
            raise PDCError("PDC response has no data object")
        studies = data.get("study")
        if not isinstance(studies, list) or len(studies) != 1:
            raise PDCError(f"PDC study lookup for {study_id} was not unique")
        return PDCStudyMetadata.from_dict(studies[0])
