"""Deterministic M10-08 evaluator matrix."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m10_08.v1 import (
    EvidencePublicationStatus,
    PublisherAssumption,
    PublisherCounterEvidence,
    PublisherEvidenceSource,
    PublisherSourceKind,
    PublishProteinRnaEvidenceRequest,
    ReconstructionStep,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c10_pathway_proteotype_factors import (
    m10_08_evidence_explanation_publisher as m1008_runtime,
)

AUTHORITY_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_LINES: Final = "3584-3627"
_DIGEST = "sha256:" + ("a" * 64)


def _artifact(identifier: str, media_type: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=identifier,
        version="1.0.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def _decision(identifier: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=identifier,
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{identifier}"),
    )


def build_request(
    *, complete: bool = True, accepted: bool = True
) -> PublishProteinRnaEvidenceRequest:
    """Build one deterministic fixture without traversing external payloads."""

    references = ContextReferences(
        approved_configuration=_decision("configuration"),
        identity_lineage=IdentityLineageReference(
            decision_id="lineage",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_DIGEST,
            evidence=_artifact("evidence.lineage"),
        ),
        provenance=_decision("provenance"),
        consent=ConsentReference(
            decision_id="consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("evidence.consent"),
        ),
        quality=_decision("quality"),
        support=_decision("support"),
        intended_use=_decision("intended-use"),
    )
    if not accepted:
        references = references.model_copy(
            update={
                "support": references.support.model_copy(
                    update={"state": UpstreamDecisionState.REJECTED}
                )
            }
        )
    context = ExecutionContext(
        request_id="eval.m1008.request",
        actor_id="eval.m1008.actor",
        occurred_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        references=references,
    )
    evidence = EvidenceReference(
        reference=_artifact("evidence.publisher"),
        role="evidence",
        claim="Caller-declared evaluation evidence.",
    )
    sources = tuple(
        PublisherEvidenceSource(
            source_id=f"source.{index}",
            kind=kind,
            artifact=_artifact(f"source-artifact.{index}"),
            claim="Caller-declared source; authority is not inferred.",
            evidence=(evidence,),
        )
        for index, kind in enumerate(PublisherSourceKind)
    )
    return PublishProteinRnaEvidenceRequest(
        request_id="eval.m1008.request",
        context=context,
        upstream_result=_artifact(
            "upstream.m1007",
            "application/vnd.glio-proteogen.m10-07+json",
        ),
        source_artifacts=sources,
        assumptions=(
            PublisherAssumption(
                assumption_id="assumption.units",
                statement="Caller declares units are reviewed.",
                evidence=(evidence,),
            ),
        )
        if complete
        else (),
        counter_evidence=(
            PublisherCounterEvidence(
                counter_evidence_id="counter.discordance",
                statement="Caller declares counter-evidence remains visible.",
                impact="Requires review.",
                evidence=(evidence,),
            ),
        )
        if complete
        else (),
        reconstruction_steps=(
            ReconstructionStep(
                sequence=1,
                operation="bind-caller-evidence",
                input_digests=(_DIGEST,),
                output_digest=_DIGEST,
                evidence=(evidence,),
            ),
        )
        if complete
        else (),
    )


def evaluate() -> dict[str, object]:
    """Run publication, abstention, replay, tamper, and boundary scenarios."""

    request = build_request()
    result = m1008_runtime.publish_protein_rna_evidence(request)
    incomplete = m1008_runtime.publish_protein_rna_evidence(build_request(complete=False))
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("b" * 64)})
    plugin = m1008_runtime.M1008EvidencePublisherPlugin(
        m1008_runtime.M1008EvidencePublisherService()
    )
    checks = {
        "complete_publication": result.status is EvidencePublicationStatus.PUBLISHED
        and result.bundle is not None
        and result.explanation is not None
        and result.emits_parent is False,
        "incomplete_abstention": incomplete.status is EvidencePublicationStatus.ABSTAINED
        and incomplete.bundle is None
        and incomplete.explanation is None
        and incomplete.human_review_required,
        "deterministic_replay": result.model_dump(mode="json")
        == m1008_runtime.publish_protein_rna_evidence(request).model_dump(mode="json"),
        "tampered_digest_rejected": not m1008_runtime.verify_publication_result(tampered),
        "unaccepted_controls_fail_closed": _raises_authorization(),
        "wrong_upstream_media_rejected": _raises_wrong_media(request),
        "duplicate_json_rejected": _raises_duplicate(plugin, request),
    }
    return {
        "module": "GLIO-PROTEOGEN-M10-08",
        "authority_sha256": AUTHORITY_SHA256,
        "authority_lines": AUTHORITY_LINES,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _raises_authorization() -> bool:
    try:
        m1008_runtime.publish_protein_rna_evidence(build_request(accepted=False))
    except m1008_runtime.M1008AuthorizationError:
        return True
    return False


def _raises_wrong_media(request: PublishProteinRnaEvidenceRequest) -> bool:
    try:
        m1008_runtime.publish_protein_rna_evidence(
            request.model_copy(update={"upstream_result": _artifact("wrong", "application/json")})
        )
    except ValueError:
        return True
    return False


def _raises_duplicate(
    plugin: m1008_runtime.M1008EvidencePublisherPlugin,
    request: PublishProteinRnaEvidenceRequest,
) -> bool:
    try:
        plugin.validate(request.model_dump_json())
        strict_json_loads('{"request_id":"one","request_id":"two"}')
    except StrictJsonError:
        return True
    return False


def main() -> None:
    print(json.dumps(evaluate(), indent=2, sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["AUTHORITY_LINES", "AUTHORITY_SHA256", "build_request", "evaluate"]
