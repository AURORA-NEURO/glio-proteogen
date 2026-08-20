"""Bounded, replayable research-only proteomics pilot.

The pilot composes the additive research primitives into one explicit local
workflow.  It accepts a caller-supplied PDC metadata response and local FASTA
and mzML bytes; it never performs network I/O, downloads a cohort file, or
registers a production/module ABI.  A successful run is an exploratory
computation receipt, not a clinical, disease, protein-identity, or abundance
claim.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Literal

from .fasta import digest_trypsin, read_fasta
from .mzml import parse_mzml
from .protein import ProteinGroup, infer_protein_groups
from .public_proteomics import (
    PDCMetadataClient,
    SourceManifest,
    SourceReference,
    aggregate_evidence,
    extract_fasta_structure,
    extract_mzml_structure,
    sha256_digest,
)
from .quantification import PeptideQuant, median_normalize
from .search import Psm, SearchParameters, search_spectrum, target_decoy_qvalues

PilotStatus = Literal["COMPLETED", "ABSTAINED"]
_PILOT_TERMS = "local research fixture; no production or clinical use"
_NO_CLAIMS = (
    "research-only exploratory computation; not a governed production ABI",
    "target-decoy q-values are not calibrated for a validated search space",
    "protein groups retain shared-peptide ambiguity and are not identity claims",
    "signal proxies are not peptide or protein abundance estimates",
    "no clinical, disease, glioma-specific, treatment, or mechanistic claim is emitted",
    "public metadata is provenance-bound but issuer truth is not authenticated",
)


class PilotError(ValueError):
    """Raised when a research pilot request or replay receipt is unsafe."""


@dataclass(frozen=True, slots=True)
class PilotPolicy:
    """Closed policy values for the non-governed pilot surface."""

    research_only: Literal[True] = True
    owner_review_required: Literal[True] = True
    network_access: Literal[False] = False
    clinical_claims: Literal[False] = False
    disease_claims: Literal[False] = False
    treatment_claims: Literal[False] = False
    mechanistic_claims: Literal[False] = False

    def __post_init__(self) -> None:
        expected = {
            "research_only": True,
            "owner_review_required": True,
            "network_access": False,
            "clinical_claims": False,
            "disease_claims": False,
            "treatment_claims": False,
            "mechanistic_claims": False,
        }
        for name, value in expected.items():
            if getattr(self, name) is not value:
                raise PilotError(f"pilot policy {name} cannot be changed")

    def as_dict(self) -> dict[str, bool]:
        return {
            "clinical_claims": self.clinical_claims,
            "disease_claims": self.disease_claims,
            "mechanistic_claims": self.mechanistic_claims,
            "network_access": self.network_access,
            "owner_review_required": self.owner_review_required,
            "research_only": self.research_only,
            "treatment_claims": self.treatment_claims,
        }


@dataclass(frozen=True, slots=True)
class PilotLimits:
    """Resource ceilings applied before decoding or scoring local inputs."""

    max_input_bytes: int = 64 * 1024 * 1024
    max_spectra: int = 10_000
    max_peptides: int = 250_000
    max_psms: int = 10_000

    def __post_init__(self) -> None:
        if type(self.max_input_bytes) is not int or not 0 < self.max_input_bytes <= 512 * 1024 * 1024:
            raise PilotError("pilot input byte cap is outside the bounded range")
        if type(self.max_spectra) is not int or not 0 < self.max_spectra <= 1_000_000:
            raise PilotError("pilot spectrum cap is outside the bounded range")
        if type(self.max_peptides) is not int or not 0 < self.max_peptides <= 2_000_000:
            raise PilotError("pilot peptide cap is outside the bounded range")
        if type(self.max_psms) is not int or not 0 < self.max_psms <= self.max_spectra:
            raise PilotError("pilot PSM cap is outside the bounded range")

    def as_dict(self) -> dict[str, int]:
        """Return the resource policy that is bound into a pilot receipt."""

        return {
            "max_input_bytes": self.max_input_bytes,
            "max_peptides": self.max_peptides,
            "max_psms": self.max_psms,
            "max_spectra": self.max_spectra,
        }


@dataclass(frozen=True, slots=True)
class PilotRequest:
    """Caller-declared bytes for one offline, metadata-bound pilot run."""

    metadata_response: bytes
    fasta_bytes: bytes
    mzml_bytes: bytes
    study_id: str = "PDC000204"
    sample_id: str = "local-research-fixture"
    retrieved_at: str = "2026-08-17T00:00:00Z"
    parameters: SearchParameters = field(default_factory=SearchParameters)
    limits: PilotLimits = field(default_factory=PilotLimits)
    policy: PilotPolicy = field(default_factory=PilotPolicy)

    def __post_init__(self) -> None:
        for name in ("metadata_response", "fasta_bytes", "mzml_bytes"):
            value = getattr(self, name)
            if not isinstance(value, bytes):
                raise PilotError(f"{name} must be caller-supplied bytes")
            if len(value) > self.limits.max_input_bytes:
                raise PilotError(f"{name} exceeds the pilot byte cap")
        if not self.sample_id.strip() or not self.retrieved_at.endswith("Z"):
            raise PilotError("pilot sample and UTC retrieval timestamp are required")
        if not 0 < self.parameters.fragment_tolerance_da <= 1.0:
            raise PilotError("fragment tolerance is outside the bounded range")
        if self.parameters.min_matched_ions < 1:
            raise PilotError("minimum matched ions must be positive")


@dataclass(frozen=True, slots=True)
class SignalProxy:
    """A spectrum-derived signal used only for exploratory normalization."""

    sample_id: str
    peptide: str
    spectrum_id: str
    total_peak_signal: float
    normalized_peak_signal: float

    def as_dict(self) -> dict[str, object]:
        return {
            "normalized_peak_signal": self.normalized_peak_signal,
            "peptide": self.peptide,
            "sample_id": self.sample_id,
            "spectrum_id": self.spectrum_id,
            "total_peak_signal": self.total_peak_signal,
        }


@dataclass(frozen=True, slots=True)
class PilotResult:
    """Immutable computation receipt with explicit abstention and limitations."""

    status: PilotStatus
    abstention_reason: str | None
    study_id: str
    sample_id: str
    spectra_seen: int
    ms2_spectra: int
    searched_spectra: int
    matched_psms: tuple[Psm, ...]
    protein_groups: tuple[ProteinGroup, ...]
    signal_proxies: tuple[SignalProxy, ...]
    source_manifest_digest: str
    metadata_digest: str
    evidence_digest: str
    fasta_digest: str
    mzml_digest: str
    policy: PilotPolicy
    parameters: SearchParameters
    limits: PilotLimits
    limitations: tuple[str, ...]
    result_digest: str

    def as_dict(self) -> dict[str, object]:
        payload = _result_payload(self)
        payload["result_digest"] = self.result_digest
        return payload


def _result_payload(result: PilotResult) -> dict[str, object]:
    return {
        "abstention_reason": result.abstention_reason,
        "fasta_digest": result.fasta_digest,
        "limitations": list(result.limitations),
        "matched_psms": [_psm_payload(psm) for psm in result.matched_psms],
        "metadata_digest": result.metadata_digest,
        "ms2_spectra": result.ms2_spectra,
        "mzml_digest": result.mzml_digest,
        "policy": result.policy.as_dict(),
        "limits": result.limits.as_dict(),
        "parameters": {
            "allowed_modifications": list(result.parameters.allowed_modifications),
            "decoy_prefix": result.parameters.decoy_prefix,
            "fragment_charges": list(result.parameters.fragment_charges),
            "fragment_tolerance_da": result.parameters.fragment_tolerance_da,
            "max_variable_modifications": result.parameters.max_variable_modifications,
            "min_matched_ions": result.parameters.min_matched_ions,
            "precursor_charge": result.parameters.precursor_charge,
            "precursor_tolerance_ppm": result.parameters.precursor_tolerance_ppm,
            "require_precursor_mz": result.parameters.require_precursor_mz,
        },
        "protein_groups": [
            {
                "accessions": list(group.accessions),
                "shared_peptides": list(group.shared_peptides),
                "unique_peptides": list(group.unique_peptides),
            }
            for group in result.protein_groups
        ],
        "sample_id": result.sample_id,
        "searched_spectra": result.searched_spectra,
        "signal_proxies": [signal.as_dict() for signal in result.signal_proxies],
        "spectra_seen": result.spectra_seen,
        "status": result.status,
        "study_id": result.study_id,
        "source_manifest_digest": result.source_manifest_digest,
        "evidence_digest": result.evidence_digest,
    }


def _psm_payload(psm: Psm) -> dict[str, object]:
    """Project every scored PSM field into the replay digest.

    The pilot remains research-only, but omitting measurement/error fields from
    the receipt would allow a caller to mutate the scientific evidence while
    retaining the same digest.  Keep this projection in lockstep with ``Psm``.
    """

    return {
        "decoy": psm.decoy,
        "matched_intensity": psm.matched_intensity,
        "matched_ions": psm.matched_ions,
        "mean_fragment_error_da": psm.mean_fragment_error_da,
        "peptide": psm.peptide,
        "precursor_error_ppm": psm.precursor_error_ppm,
        "protein_accessions": list(psm.protein_accessions),
        "q_value": psm.q_value,
        "score": psm.score,
        "spectrum_id": psm.spectrum_id,
        "target_decoy_collision": psm.target_decoy_collision,
    }


def _finish(result: PilotResult) -> PilotResult:
    return replace(result, result_digest=sha256_digest(_result_payload(result)))


def _manifest_and_metadata(
    request: PilotRequest,
) -> tuple[str, str, str, str]:
    response = request.metadata_response

    def fixture_transport(
        _url: str,
        _payload: bytes,
        _timeout: float,
        _user_agent: str,
        _max_bytes: int,
    ) -> tuple[int, bytes, str]:
        return 200, response, "application/json"

    snapshot = PDCMetadataClient(transport=fixture_transport).fetch(
        request.study_id, retrieved_at=request.retrieved_at
    )
    fasta_ref = SourceReference(
        "local:fasta",
        "memory:pilot-fasta",
        "text/plain",
        sha256_digest(request.fasta_bytes),
        len(request.fasta_bytes),
        request.retrieved_at,
        _PILOT_TERMS,
    )
    mzml_ref = SourceReference(
        "local:mzml",
        "memory:pilot-mzml",
        "application/xml",
        sha256_digest(request.mzml_bytes),
        len(request.mzml_bytes),
        request.retrieved_at,
        _PILOT_TERMS,
    )
    manifest = SourceManifest(
        f"research-pilot-{request.study_id.lower()}-v1",
        request.retrieved_at,
        "offline spectrum search and exploratory signal normalization",
        (snapshot.source_reference, fasta_ref, mzml_ref),
        "caller-supplied PDC metadata plus bounded local FASTA/mzML bytes",
    )
    aggregate = aggregate_evidence(
        manifest,
        snapshot,
        {
            "local:fasta": extract_fasta_structure(request.fasta_bytes),
            "local:mzml": extract_mzml_structure(request.mzml_bytes),
        },
    )
    return manifest.digest, snapshot.digest, aggregate.digest, sha256_digest(response)


def _abstained(
    request: PilotRequest,
    *,
    reason: str,
    spectra_seen: int,
    ms2_spectra: int,
    searched_spectra: int,
    manifest_digest: str,
    metadata_digest: str,
    evidence_digest: str,
) -> PilotResult:
    return _finish(
        PilotResult(
            status="ABSTAINED",
            abstention_reason=reason,
            study_id=request.study_id,
            sample_id=request.sample_id,
            spectra_seen=spectra_seen,
            ms2_spectra=ms2_spectra,
            searched_spectra=searched_spectra,
            matched_psms=(),
            protein_groups=(),
            signal_proxies=(),
            source_manifest_digest=manifest_digest,
            metadata_digest=metadata_digest,
            evidence_digest=evidence_digest,
            fasta_digest=sha256_digest(request.fasta_bytes),
            mzml_digest=sha256_digest(request.mzml_bytes),
            policy=request.policy,
            parameters=request.parameters,
            limits=request.limits,
            limitations=_NO_CLAIMS,
            result_digest="",
        )
    )


def run_pilot(request: PilotRequest) -> PilotResult:
    """Run the bounded offline pilot and abstain on unsupported input."""

    manifest_digest, metadata_digest, evidence_digest, _response_digest = _manifest_and_metadata(
        request
    )
    entries = read_fasta(request.fasta_bytes)
    peptide_map = digest_trypsin(entries, min_length=2, max_length=80)
    if len(peptide_map) > request.limits.max_peptides:
        raise PilotError("digested peptide search space exceeds the pilot cap")
    spectra = parse_mzml(
        request.mzml_bytes,
        max_bytes=request.limits.max_input_bytes,
        max_spectra=request.limits.max_spectra,
    )
    ms2 = tuple(spectrum for spectrum in spectra if spectrum.ms_level == 2)
    if not ms2:
        return _abstained(
            request,
            reason="NO_MS2_SPECTRA",
            spectra_seen=len(spectra),
            ms2_spectra=0,
            searched_spectra=0,
            manifest_digest=manifest_digest,
            metadata_digest=metadata_digest,
            evidence_digest=evidence_digest,
        )
    psms: list[Psm] = []
    signal_by_spectrum: dict[str, float] = {}
    searched_spectra = 0
    for spectrum in ms2:
        searched_spectra += 1
        signal_by_spectrum[spectrum.spectrum_id] = sum(spectrum.intensity)
        if request.parameters.require_precursor_mz and (
            spectrum.precursor_mz is None
            or spectrum.precursor_charge is None
            or spectrum.precursor_charge != request.parameters.precursor_charge
        ):
            continue
        psm = search_spectrum(
            spectrum.spectrum_id,
            spectrum.precursor_mz if spectrum.precursor_mz is not None else 0.0,
            peptide_map,
            spectrum.mz,
            spectrum.intensity,
            parameters=request.parameters,
        )
        if psm is not None:
            psms.append(psm)
        if len(psms) >= request.limits.max_psms:
            break
    scored = target_decoy_qvalues(psms, decoy_prefix=request.parameters.decoy_prefix)
    if not scored:
        return _abstained(
            request,
            reason="NO_SUPPORTED_PSM",
            spectra_seen=len(spectra),
            ms2_spectra=len(ms2),
            searched_spectra=searched_spectra,
            manifest_digest=manifest_digest,
            metadata_digest=metadata_digest,
            evidence_digest=evidence_digest,
        )
    group_input = {psm.peptide: psm.protein_accessions for psm in scored if psm.protein_accessions}
    groups = infer_protein_groups(group_input)
    quant = median_normalize(
        tuple(
            PeptideQuant(
                request.sample_id,
                psm.peptide,
                signal_by_spectrum[psm.spectrum_id],
            )
            for psm in scored
        )
    )
    signals = tuple(
        SignalProxy(
            item.sample_id,
            item.peptide,
            scored[index].spectrum_id,
            item.intensity,
            item.intensity,
        )
        for index, item in enumerate(quant)
    )
    return _finish(
        PilotResult(
            status="COMPLETED",
            abstention_reason=None,
            study_id=request.study_id,
            sample_id=request.sample_id,
            spectra_seen=len(spectra),
            ms2_spectra=len(ms2),
            searched_spectra=searched_spectra,
            matched_psms=scored,
            protein_groups=groups,
            signal_proxies=signals,
            source_manifest_digest=manifest_digest,
            metadata_digest=metadata_digest,
            evidence_digest=evidence_digest,
            fasta_digest=sha256_digest(request.fasta_bytes),
            mzml_digest=sha256_digest(request.mzml_bytes),
            policy=request.policy,
            parameters=request.parameters,
            limits=request.limits,
            limitations=_NO_CLAIMS,
            result_digest="",
        )
    )


def verify_pilot_replay(request: PilotRequest, result: PilotResult) -> PilotResult:
    """Rerun the exact offline request and reject a changed receipt."""

    replay = run_pilot(request)
    if replay.result_digest != result.result_digest or replay.as_dict() != result.as_dict():
        raise PilotError("pilot replay digest or payload differs")
    return replay


def result_json(result: PilotResult) -> str:
    """Serialize a receipt with stable key ordering for evidence storage."""

    return json.dumps(result.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = [
    "PilotError",
    "PilotLimits",
    "PilotPolicy",
    "PilotRequest",
    "PilotResult",
    "SignalProxy",
    "result_json",
    "run_pilot",
    "verify_pilot_replay",
]
