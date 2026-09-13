"""Deterministic, fail-closed M14-02 context and subtype stratifier."""

# The adapter intentionally sanitizes generic authorization and validation failures.
# ruff: noqa: TRY003, TRY301

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_02 import (
    ApplicableMechanism,
    ContextDimension,
    ContextFinding,
    ContextFindingCode,
    ContextObservation,
    ContextObservationStatus,
    ContextStratificationStatus,
    MechanismApplicability,
    ProteinSubtypeContextProfile,
    ProteinSubtypeContextStratificationResult,
    StratifyProteinSubtypeContextRequest,
    expected_provenance,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER = TypeAdapter(StratifyProteinSubtypeContextRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinSubtypeContextStratificationResult)
_SUPPORTED_METHODS: Final = frozenset(
    {
        "bayesian_graph",
        "state_space",
        "mechanistic",
        "foundation_assisted",
        "curated_rule",
        "enrichment",
        "cn_to_protein_regression",
        "orthogonal_consensus_negative_control",
    }
)
_METHOD_LABELS: Final = {
    "bayesian_graph": "Bayesian context graph",
    "state_space": "Context state-space trajectory",
    "mechanistic": "Mechanistic context rule",
    "foundation_assisted": "Foundation-assisted context residual",
    "curated_rule": "Curated context rule",
    "enrichment": "Context enrichment baseline",
    "cn_to_protein_regression": "CN-to-protein residual baseline",
    "orthogonal_consensus_negative_control": "Orthogonal context consensus",
}


@dataclass(frozen=True)
class _GliomaContextRule:
    """One explicit GBM context-to-mechanism mapping.

    M14-02 receives typed context observations rather than raw omics.  These
    rules therefore do not pretend to fit a hidden classifier; they make the
    permitted glioma vocabulary executable and auditable.  A rule can fire only
    for a supported observation and its evidence is carried into the mechanism
    record.
    """

    dimension: ContextDimension
    aliases: frozenset[str]
    mechanism_id: str
    label: str
    rationale: str


_GLIOMA_CONTEXT_RULES: Final[tuple[_GliomaContextRule, ...]] = (
    _GliomaContextRule(
        ContextDimension.SUBTYPE,
        frozenset({"mes", "mes1", "mes2", "mes-like", "mesenchymal", "mesenchymal-like"}),
        "mechanism.glioma.mesenchymal-inflammatory",
        "Mesenchymal/inflammatory GBM program",
        (
            "Mesenchymal-like tumor-cell context is consistent with inflammatory and "
            "extracellular-matrix remodeling."
        ),
    ),
    _GliomaContextRule(
        ContextDimension.SUBTYPE,
        frozenset({"ac", "ac-like", "astrocyte-like", "astrocytic"}),
        "mechanism.glioma.astrocytic-glial",
        "Astrocytic/glial GBM program",
        (
            "Astrocytic-like context is consistent with glial homeostasis and "
            "astrocyte-associated proteomic programs."
        ),
    ),
    _GliomaContextRule(
        ContextDimension.SUBTYPE,
        frozenset({"opc", "opc-like", "oligodendrocyte", "oligodendrocyte-progenitor"}),
        "mechanism.glioma.opc-developmental",
        "OPC-like developmental program",
        (
            "OPC-like context is consistent with oligodendrocyte-progenitor "
            "differentiation and myelination programs."
        ),
    ),
    _GliomaContextRule(
        ContextDimension.SUBTYPE,
        frozenset({"npc", "npc-like", "neural-progenitor", "neural-progenitor-like"}),
        "mechanism.glioma.neural-progenitor",
        "Neural-progenitor GBM program",
        (
            "Neural-progenitor-like context is consistent with neuronal development "
            "and synaptic signaling programs."
        ),
    ),
    _GliomaContextRule(
        ContextDimension.BIOLOGICAL_CONTEXT,
        frozenset({"hypoxia", "hypoxic", "low-oxygen", "oxygen-deprived", "necrotic"}),
        "mechanism.glioma.hypoxia-angiogenesis",
        "Hypoxia/angiogenesis microenvironment",
        (
            "Hypoxic or necrotic context is consistent with oxygen stress and "
            "vascular remodeling programs."
        ),
    ),
    _GliomaContextRule(
        ContextDimension.BIOLOGICAL_CONTEXT,
        frozenset(
            {"immune-inflamed", "myeloid-rich", "microglial", "macrophage-rich", "t-cell-inflamed"}
        ),
        "mechanism.glioma.myeloid-immune",
        "Myeloid/immune-inflamed microenvironment",
        (
            "Immune or myeloid-rich context is consistent with microglial/macrophage "
            "inflammatory programs."
        ),
    ),
    _GliomaContextRule(
        ContextDimension.BIOLOGICAL_CONTEXT,
        frozenset({"angiogenic", "vascular", "vascularized", "endothelial-rich"}),
        "mechanism.glioma.vascular-remodeling",
        "Vascular remodeling microenvironment",
        (
            "Vascular context is consistent with endothelial and extracellular-matrix "
            "remodeling programs."
        ),
    ),
    _GliomaContextRule(
        ContextDimension.BIOLOGICAL_CONTEXT,
        frozenset({"proliferative", "cell-cycle", "cycling", "replicative"}),
        "mechanism.glioma.proliferative-cell-cycle",
        "Proliferative/cell-cycle program",
        (
            "Proliferative context is consistent with DNA-replication and cell-cycle "
            "proteomic programs."
        ),
    ),
    _GliomaContextRule(
        ContextDimension.TERRITORY,
        frozenset({"enhancing-core", "enhancing", "necrotic-core", "tumor-core"}),
        "mechanism.glioma.core-hypoxic-vascular",
        "Enhancing-core hypoxic/vascular niche",
        (
            "Enhancing or necrotic core territory is consistent with hypoxic and "
            "vascular niche remodeling."
        ),
    ),
    _GliomaContextRule(
        ContextDimension.TERRITORY,
        frozenset({"infiltrative-edge", "infiltrative-margin", "tumor-margin", "invasion-front"}),
        "mechanism.glioma.invasive-edge",
        "Infiltrative tumor-edge program",
        (
            "Infiltrative edge territory is consistent with extracellular-matrix "
            "interaction and migration programs."
        ),
    ),
)
_PROHIBITED_PROXY_TOKENS: Final = (
    "kinase",
    "all-omics",
    "all_omics",
    "treatment recommendation",
    "identity inference",
    "consent inference",
)


class M1402AuthorizationError(ValueError):
    """Raised when the seven required upstream controls do not authorize work."""


class M1402InferenceError(ValueError):
    """Raised when a typed context request cannot be safely evaluated."""


class M1402ReplayVerificationError(ValueError):
    """Raised when a result digest or deterministic replay does not match."""


def _control_state(value: object) -> str:
    if not isinstance(value, Mapping):
        raise M1402AuthorizationError("M14-02 controls are unavailable")
    state = value.get("state")
    if not isinstance(state, str):
        raise M1402AuthorizationError("M14-02 controls are unavailable")
    return state


def preflight_context_authorization(request: object) -> None:
    """Check controls without traversing arbitrary caller-owned objects."""

    try:
        if isinstance(request, StratifyProteinSubtypeContextRequest):
            references = request.context.references
            if (
                references.approved_configuration.state.value != "accepted"
                or references.identity_lineage.state.value != "resolved"
                or references.provenance.state.value != "accepted"
                or references.consent.state.value != "granted"
                or references.quality.state.value != "accepted"
                or references.support.state.value != "accepted"
                or references.intended_use.state.value != "accepted"
            ):
                raise M1402AuthorizationError("M14-02 controls do not authorize stratification")
            return
        if not isinstance(request, Mapping):
            raise M1402AuthorizationError("M14-02 request controls are unavailable")
        context = request.get("context")
        if not isinstance(context, Mapping):
            raise M1402AuthorizationError("M14-02 request controls are unavailable")
        raw_references = context.get("references")
        if not isinstance(raw_references, Mapping):
            raise M1402AuthorizationError("M14-02 request controls are unavailable")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        for role, state in expected.items():
            if _control_state(raw_references.get(role)) != state:
                raise M1402AuthorizationError("M14-02 controls do not authorize stratification")
    except M1402AuthorizationError:
        raise
    except Exception as error:
        raise M1402AuthorizationError("M14-02 controls are unavailable") from error


def _evidence(request: StratifyProteinSubtypeContextRequest) -> tuple[EvidenceReference, ...]:
    references: list[ArtifactReference] = [
        request.microenvironment_deconvolution_result,
        request.policy.configuration.model_reference,
        *request.source_artifacts,
    ]
    unique: dict[str, ArtifactReference] = {item.digest: item for item in references}
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M14-02 context stratification evidence.",
        )
        for artifact in unique.values()
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m1402_no_kinase_or_treatment",
            statement=(
                "Context stratification does not infer kinase activity or recommend treatment."
            ),
        ),
        Limitation(
            code="m1402_provisional_abi",
            statement=(
                "The M14-02 ABI and context vocabulary remain provisional pending owner review."
            ),
        ),
        Limitation(
            code=("m1402_supported_domain" if supported else "m1402_abstained_domain"),
            statement=(
                "Applicability is limited to declared context observations and locked policy."
                if supported
                else (
                    "Unsupported, unresolved, conflicted, or proxy-bearing context is not "
                    "extrapolated."
                )
            ),
        ),
    )


def _finding(
    finding_id: str,
    code: ContextFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> ContextFinding:
    return ContextFinding(finding_id=finding_id, code=code, message=message, evidence=evidence[:1])


def _normalized_context_token(value: str) -> str:
    """Normalize a caller-declared context label without fuzzy matching."""

    token = value.casefold().replace("_", "-")
    return "-".join(part for part in token.split() if part)


def _domain_mechanisms(
    observations: tuple[ContextObservation, ...],
) -> tuple[ApplicableMechanism, ...]:
    """Apply the locked GBM context vocabulary to supported observations.

    Matching is exact after case/underscore/whitespace normalization.  This is
    intentionally conservative: an unknown label remains usable for generic
    context stratification but never gets silently assigned a biology program.
    """

    matched: dict[str, tuple[_GliomaContextRule, ContextObservation]] = {}
    for observation in observations:
        if observation.status is not ContextObservationStatus.SUPPORTED:
            continue
        values = (observation.normalized_value, observation.value)
        for value in values:
            if value is None:
                continue
            token = _normalized_context_token(value)
            for rule in _GLIOMA_CONTEXT_RULES:
                if rule.dimension is observation.dimension and token in rule.aliases:
                    matched.setdefault(rule.mechanism_id, (rule, observation))
    output: list[ApplicableMechanism] = []
    for mechanism_id in sorted(matched):
        rule, observation = matched[mechanism_id]
        observed = observation.normalized_value or observation.value
        output.append(
            ApplicableMechanism(
                mechanism_id=rule.mechanism_id,
                label=rule.label,
                applicability=MechanismApplicability.APPLICABLE,
                rationale=(
                    f"{rule.rationale} Matched supported "
                    f"{observation.dimension.value}='{observed}'."
                ),
                evidence=observation.evidence,
            )
        )
    return tuple(output)


class M1402ContextStratifier:
    """Stateless deterministic context profile and mechanism applicability engine."""

    def infer(self, request: object) -> ProteinSubtypeContextStratificationResult:
        preflight_context_authorization(request)
        try:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            raise M1402InferenceError from error
        request_digest = sha256_digest(typed.model_dump(mode="json"))
        evidence = _evidence(typed)
        required = set(typed.policy.required_dimensions)
        by_dimension = {item.dimension: item for item in typed.observations}
        unsupported_proxy = any(
            token in f"{item.value} {item.normalized_value or ''}".casefold()
            for item in typed.observations
            for token in _PROHIBITED_PROXY_TOKENS
        )
        missing = required - set(by_dimension)
        unsafe = {
            item.dimension
            for item in typed.observations
            if item.status is not ContextObservationStatus.SUPPORTED
        }
        supported = (
            typed.policy.configuration.locked
            and typed.policy.quarantine_unresolved
            and typed.policy.prohibit_all_omics_fusion
            and typed.policy.configuration.method in _SUPPORTED_METHODS
            and not missing
            and not unsafe
            and not unsupported_proxy
        )
        profile = None
        mechanisms: tuple[ApplicableMechanism, ...] = ()
        findings: tuple[ContextFinding, ...]
        if supported:
            profile = ProteinSubtypeContextProfile(
                profile_id=f"profile.{request_digest.removeprefix('sha256:')}",
                version=typed.policy.configuration.version,
                observations=typed.observations,
                unresolved_dimensions=(),
                evidence=evidence,
            )
            method = typed.policy.configuration.method
            mechanisms = _domain_mechanisms(typed.observations)
            if not mechanisms:
                mechanisms = (
                    ApplicableMechanism(
                        mechanism_id=f"mechanism.{method}",
                        label=_METHOD_LABELS[method],
                        applicability=MechanismApplicability.APPLICABLE,
                        rationale=(
                            "Declared context dimensions satisfy the locked stratifier policy; "
                            "no known GBM context label was asserted."
                        ),
                        evidence=evidence[:1],
                    ),
                )
            findings = (
                _finding(
                    "finding.provisional-abi",
                    ContextFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    "M14-02 ABI remains provisional pending owner confirmation.",
                    evidence,
                ),
            )
        else:
            code = (
                ContextFindingCode.UNSUPPORTED_PROXY_BLOCKED
                if unsupported_proxy or typed.policy.configuration.method not in _SUPPORTED_METHODS
                else ContextFindingCode.CONTEXT_CONFLICT
                if unsafe or missing
                else ContextFindingCode.PROVISIONAL_ABI_PENDING_REVIEW
            )
            findings = (
                _finding(
                    "finding.abstention",
                    code,
                    "Context support is outside the safe provisional stratification domain.",
                    evidence,
                ),
                _finding(
                    "finding.provisional-abi",
                    ContextFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    "M14-02 ABI remains provisional pending owner confirmation.",
                    evidence,
                ),
            )
        payload: dict[str, Any] = {
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "request_digest": request_digest,
            "result_digest": sha256_digest("placeholder"),
            "request": typed,
            "status": ContextStratificationStatus.STRATIFIED
            if supported
            else ContextStratificationStatus.ABSTAINED,
            "context_profile": profile,
            "applicable_mechanisms": mechanisms,
            "findings": findings,
            "abstention_reason": None
            if supported
            else "Context is unsupported, unresolved, conflicted, or proxy-bearing.",
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1402_context_supported" if supported else "m1402_context_abstained",
                rationale=(
                    "All required context dimensions are supported under the locked policy."
                    if supported
                    else "The safe support domain does not cover this context request."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(typed, request_digest),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ProteinSubtypeContextStratificationResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M1402InferenceError from error

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ProteinSubtypeContextStratificationResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1402ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1402ReplayVerificationError
        if replay:
            try:
                expected = self.infer(validated.request)
            except Exception as error:
                raise M1402ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1402ReplayVerificationError
        return validated


def stratify_protein_subtype_context(
    request: object,
) -> ProteinSubtypeContextStratificationResult:
    """Public provisional M14-02 operation."""

    return M1402ContextStratifier().infer(request)


__all__ = [
    "M1402AuthorizationError",
    "M1402ContextStratifier",
    "M1402InferenceError",
    "M1402ReplayVerificationError",
    "preflight_context_authorization",
    "stratify_protein_subtype_context",
]
