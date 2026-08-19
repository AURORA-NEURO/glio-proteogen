"""Deterministic synthetic-truth generation for the provisional M24-02 lane."""

from __future__ import annotations

from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_02 import (
    M2402_CONTRACT_VERSION,
    M2402_MODULE_ID,
    BiomarkerPanelSyntheticTruthResult,
    FixtureKind,
    GenerateBiomarkerPanelSyntheticTruthRequest,
    GenerationManifest,
    GenerationStatus,
    SyntheticTruthCase,
    SyntheticTruthCorpus,
    TruthRepresentation,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import Limitation, SupportStatus
from glio_proteogen.kernel.strict_json import strict_json_loads

from .._m24_runtime_common import (
    AuthorizationError,
    evidence,
    preflight,
    provenance,
    support,
    uncertainty,
)

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateBiomarkerPanelSyntheticTruthRequest)
_EVIDENCE_CLAIM: Final = (
    "Caller-declared synthetic truth fixture and reproducibility evidence; "
    "issuer authority and biological validity are not authenticated."
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_upstream",
        statement=(
            "The M24-01 reference is bound by media type and digest only; it is not inspected."
        ),
    ),
    Limitation(
        code="synthetic_not_biological",
        statement=(
            "Cases are deterministic analytic or semi-synthetic fixtures and do not infer "
            "proteins, proteoforms, isoforms, glioma biology or treatment."
        ),
    ),
    Limitation(
        code="provisional_abi",
        statement="M24-02 remains 0.1.0-provisional pending owner confirmation.",
    ),
)


class M2402ReplayError(ValueError):
    """Raised when an M24-02 result fails semantic replay."""


def _result_id(request_digest: str) -> str:
    return "m2402.result." + request_digest.removeprefix("sha256:")


def _case(
    request: GenerateBiomarkerPanelSyntheticTruthRequest,
    index: int,
    kind: FixtureKind,
) -> SyntheticTruthCase:
    seed = request.configuration.seed + index
    feature_count = 3 + (seed % 3)
    features = tuple(f"panel.feature.{index:03d}.{j:02d}" for j in range(feature_count))
    values = tuple(f"{((seed * (j + 3) + 17) % 10000) / 10000:.6f}" for j in range(feature_count))
    representation = (
        TruthRepresentation.ANALYTIC
        if kind in {FixtureKind.NORMAL, FixtureKind.EDGE, FixtureKind.MISSING}
        else TruthRepresentation.SEMI_SYNTHETIC
    )
    perturbations = {
        FixtureKind.NORMAL: (),
        FixtureKind.EDGE: ("boundary_value",),
        FixtureKind.MISSING: ("missing_feature",),
        FixtureKind.SHIFTED: ("distribution_shift",),
        FixtureKind.ADVERSARIAL: ("hostile_label", "unsupported_perturbation"),
    }[kind]
    return SyntheticTruthCase(
        case_id=f"m2402.case.{index:04d}",
        fixture_kind=kind,
        representation=representation,
        seed=seed,
        expected_features=features,
        truth_values=values,
        perturbations=perturbations,
        evidence=evidence(request.source_artifacts, _EVIDENCE_CLAIM),
    )


def _manifest(
    request: GenerateBiomarkerPanelSyntheticTruthRequest,
    cases: tuple[SyntheticTruthCase, ...],
) -> GenerationManifest:
    case_ids = tuple(case.case_id for case in cases)
    reproducibility_digest = sha256_digest(
        {
            "configuration": request.configuration.model_dump(mode="json"),
            "cases": [case.model_dump(mode="json") for case in cases],
        }
    )
    return GenerationManifest(
        manifest_id="m2402.manifest." + reproducibility_digest.removeprefix("sha256:"),
        version=request.configuration.version,
        configuration=request.configuration,
        case_ids=case_ids,
        reproducibility_digest=reproducibility_digest,
        fixture_summary=tuple(
            f"{kind.value}:{sum(case.fixture_kind is kind for case in cases)}"
            for kind in request.configuration.requested_fixture_kinds
        ),
        evidence=evidence(request.source_artifacts, _EVIDENCE_CLAIM),
    )


class M2402SyntheticTruthGenerator:
    """Generate deterministic fixtures without claiming biological truth."""

    __slots__ = ()

    def evaluate(self, request: object) -> BiomarkerPanelSyntheticTruthResult:
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request)
            validated = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight(request, M2402_MODULE_ID)
            validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight(validated, M2402_MODULE_ID)
        canonical = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(validated), strict=True)
        request_digest = canonical_request_digest(canonical)
        kinds = canonical.configuration.requested_fixture_kinds
        cases = tuple(
            _case(canonical, index, kinds[index % len(kinds)])
            for index in range(canonical.requested_case_count)
        )
        manifest = _manifest(canonical, cases)
        corpus = SyntheticTruthCorpus(
            corpus_id="m2402.corpus." + request_digest.removeprefix("sha256:"),
            version=canonical.configuration.version,
            cases=cases,
            manifest=manifest,
            source_artifacts=canonical.source_artifacts,
            evidence=evidence(canonical.source_artifacts, _EVIDENCE_CLAIM),
        )
        payload: dict[str, Any] = {
            "output_type": "biomarker_panel_synthetic_truth",
            "result_id": _result_id(request_digest),
            "result_version": M2402_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + "0" * 64,
            "request": canonical,
            "status": GenerationStatus.GENERATED,
            "corpus": corpus,
            "manifest": manifest,
            "findings": (),
            "abstention_reason": None,
            "parent_target": "biomarker panel",
            "emits_parent": False,
            "support_decision": support(
                SupportStatus.SUPPORTED,
                "deterministic_fixture_generation_complete",
                "All requested fixture kinds were generated under the locked configuration.",
            ),
            "uncertainty": uncertainty(M2402_MODULE_ID),
            "provenance": provenance(
                canonical.context,
                (canonical.upstream_result, *canonical.source_artifacts),
                request_digest,
                M2402_MODULE_ID,
                M2402_CONTRACT_VERSION,
                canonical_request_digest(canonical.configuration),
            ),
            "evidence": evidence(
                (canonical.upstream_result, *canonical.source_artifacts), _EVIDENCE_CLAIM
            ),
            "limitations": _LIMITATIONS,
            "human_review_required": False,
        }
        provisional = BiomarkerPanelSyntheticTruthResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return BiomarkerPanelSyntheticTruthResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def verify_replay(
        self,
        result: BiomarkerPanelSyntheticTruthResult,
    ) -> BiomarkerPanelSyntheticTruthResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2402ReplayError("M24-02 request digest mismatch")  # noqa: TRY003
        if result.result_id != _result_id(result.request_digest):
            raise M2402ReplayError("M24-02 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2402ReplayError("M24-02 result payload digest mismatch")  # noqa: TRY003
        try:
            replayed = BiomarkerPanelSyntheticTruthResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
            expected = self.evaluate(replayed.request)
        except Exception as error:
            raise M2402ReplayError from error
        if canonical_json_bytes(expected) != canonical_json_bytes(replayed):
            raise M2402ReplayError("M24-02 semantic replay mismatch")  # noqa: TRY003
        return replayed


def generate_biomarker_panel_synthetic_truth(
    request: object,
) -> BiomarkerPanelSyntheticTruthResult:
    return M2402SyntheticTruthGenerator().evaluate(request)


def preflight_m2402_authorization(candidate: object) -> None:
    preflight(candidate, M2402_MODULE_ID)


__all__ = [
    "AuthorizationError",
    "M2402ReplayError",
    "M2402SyntheticTruthGenerator",
    "generate_biomarker_panel_synthetic_truth",
    "preflight_m2402_authorization",
]
