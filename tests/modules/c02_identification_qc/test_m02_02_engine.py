"""Representative engine and lifecycle checks for M02-02."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_02 import EntityKind, IdentityLineageResolution
from glio_proteogen.contracts.m02_02 import (
    BindingDisposition,
    BindingState,
    FindingCode,
    IdentificationArtifactBinding,
    IdentityBindingPolicy,
    ScopedBindingToken,
    ValidateIdentityBindingsRequest,
    configuration_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage import (
    IdentityBindingAuthorizationError,
    M0202Plugin,
    M0202Service,
    ValidatedM0202Request,
    evaluate_identity_bindings,
    preflight_identity_binding_authorization,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "m02_02"


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"m0202": label}),
        media_type="application/json",
    )


def _resolution(*, unresolved: bool = False) -> IdentityLineageResolution:
    name = "upstream_unresolved.json" if unresolved else "upstream_resolved.json"
    return TypeAdapter(IdentityLineageResolution).validate_json(
        (FIXTURE_ROOT / name).read_bytes(),
        strict=True,
    )


def _policy() -> IdentityBindingPolicy:
    return IdentityBindingPolicy(
        policy_id="policy.synthetic.m0202",
        version="1.0.0",
        max_bindings=16,
        allowed_entity_kinds=(EntityKind.RUN, EntityKind.DERIVED_OBJECT),
        allowed_token_scope_ids=("scope.synthetic.lab", "scope.synthetic.external"),
        evidence=_artifact("policy"),
    )


def _context(
    resolution: IdentityLineageResolution,
    policy: IdentityBindingPolicy,
) -> ExecutionContext:
    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role, digest),
        )

    identity_state = (
        IdentityLineageState.RESOLVED
        if resolution.decision.value == "resolved"
        else IdentityLineageState.UNRESOLVED
        if resolution.decision.value == "unresolved"
        else IdentityLineageState.CONFLICTED
    )
    return ExecutionContext(
        request_id="request.synthetic.m0202",
        actor_id="actor.synthetic.m0202",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", configuration_digest(policy)),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.identity",
                state=identity_state,
                policy_version="1.0.0",
                binding_digest=resolution.resolution_digest,
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _binding(
    resolution: IdentityLineageResolution,
    entity_id: str,
    *,
    binding_id: str,
    opaque_label: str,
    artifact_digest: str | None = None,
) -> IdentificationArtifactBinding:
    node = next(item for item in resolution.graph.nodes if item.entity_id == entity_id)
    return IdentificationArtifactBinding(
        binding_id=binding_id,
        artifact=_artifact(f"result.{binding_id}", artifact_digest),
        state=BindingState.BOUND,
        entity_id=node.entity_id,
        entity_kind=node.kind,
        component_id=node.component_id,
        observed_subject_component_ids=node.subject_component_ids,
        scoped_token=ScopedBindingToken(
            scope_id="scope.synthetic.lab",
            token_digest=sha256_digest({"opaque": opaque_label}),
        ),
        evidence=(_artifact(f"binding.{binding_id}"),),
    )


def _request(
    bindings: tuple[IdentificationArtifactBinding, ...] | None = None,
    *,
    unresolved: bool = False,
) -> ValidateIdentityBindingsRequest:
    resolution = _resolution(unresolved=unresolved)
    policy = _policy()
    if bindings is None:
        bindings = (
            _binding(
                resolution,
                "entity.synthetic.run.a",
                binding_id="binding.a",
                opaque_label="a",
            ),
        )
    return ValidateIdentityBindingsRequest(
        context=_context(resolution, policy),
        identity_resolution=resolution,
        policy=policy,
        bindings=bindings,
    )


def test_conformant_binding_uses_authoritative_upstream_node() -> None:
    result = evaluate_identity_bindings(_request())

    assert result.disposition is BindingDisposition.CONFORMANT
    assert result.findings == ()
    assert result.bindings[0].upstream_subject_component_ids == (
        result.lineage_graph.nodes[4].subject_component_ids
    )


def test_observed_subject_swap_is_quarantined() -> None:
    request = _request()
    other_subject = next(
        item.subject_component_ids
        for item in request.identity_resolution.graph.nodes
        if item.entity_id == "entity.synthetic.run.b"
    )
    binding = request.bindings[0].model_copy(
        update={"observed_subject_component_ids": other_subject}
    )
    request = request.model_copy(update={"bindings": (binding,)})

    result = evaluate_identity_bindings(request)

    assert result.disposition is BindingDisposition.QUARANTINED
    assert {item.code for item in result.findings} >= {FindingCode.SWAP}


def test_claimed_component_mismatch_is_a_swap_not_a_relink() -> None:
    request = _request()
    wrong = next(
        item.component_id
        for item in request.identity_resolution.graph.nodes
        if item.entity_id == "entity.synthetic.run.b"
    )
    binding = request.bindings[0].model_copy(update={"component_id": wrong})

    result = evaluate_identity_bindings(request.model_copy(update={"bindings": (binding,)}))

    assert result.bindings[0].entity_component_id != wrong
    assert FindingCode.SWAP in result.bindings[0].finding_codes


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (BindingState.UNRESOLVED, FindingCode.UNRESOLVED_BINDING),
        (BindingState.UNSUPPORTED, FindingCode.UNSUPPORTED_BINDING),
    ],
)
def test_non_bound_states_abstain_without_negative_identity(
    state: BindingState,
    code: FindingCode,
) -> None:
    request = _request()
    binding = request.bindings[0].model_copy(
        update={
            "state": state,
            "observed_subject_component_ids": (),
            "scoped_token": None,
        }
    )

    result = evaluate_identity_bindings(request.model_copy(update={"bindings": (binding,)}))

    assert result.disposition is BindingDisposition.ABSTAINED
    assert {item.code for item in result.findings} == {code}


def test_same_scope_token_and_duplicate_content_findings_are_deterministic() -> None:
    resolution = _resolution()
    shared_content = sha256_digest({"content": "shared"})
    bindings = (
        _binding(
            resolution,
            "entity.synthetic.run.a",
            binding_id="binding.a",
            opaque_label="shared",
            artifact_digest=shared_content,
        ),
        _binding(
            resolution,
            "entity.synthetic.run.b",
            binding_id="binding.b",
            opaque_label="shared",
            artifact_digest=shared_content,
        ),
    )

    result = evaluate_identity_bindings(_request(bindings))

    assert result.disposition is BindingDisposition.QUARANTINED
    assert {item.code for item in result.findings} == {
        FindingCode.TOKEN_COLLISION,
        FindingCode.DUPLICATE_CONTENT_ASSIGNMENT,
    }


def test_unresolved_upstream_resolution_abstains_with_typed_finding() -> None:
    resolution = _resolution(unresolved=True)
    binding = _binding(
        resolution,
        "entity.synthetic.run.a",
        binding_id="binding.a",
        opaque_label="a",
    )

    result = evaluate_identity_bindings(_request((binding,), unresolved=True))

    assert result.disposition is BindingDisposition.ABSTAINED
    assert FindingCode.UPSTREAM_IDENTITY_UNRESOLVED in {
        item.code for item in result.findings
    }


def test_service_and_raw_json_plugin_replay_identically() -> None:
    request = _request()
    service = M0202Service()
    plugin = M0202Plugin(service)

    expected = service.execute(request)
    token = plugin.validate(request.model_dump_json())

    assert plugin.run(token) == expected
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M02-02"
    with pytest.raises(TypeError):
        plugin.run(cast("ValidatedM0202Request", object()))


def test_upstream_graph_presentation_order_does_not_change_full_output() -> None:
    request = _request()
    graph = request.identity_resolution.graph.model_copy(
        update={"nodes": tuple(reversed(request.identity_resolution.graph.nodes))}
    )
    resolution = request.identity_resolution.model_copy(update={"graph": graph})
    reordered = request.model_copy(update={"identity_resolution": resolution})

    expected = evaluate_identity_bindings(request)
    replay = evaluate_identity_bindings(reordered)

    assert replay == expected
    assert replay.model_dump_json() == expected.model_dump_json()


def test_authorization_rejects_before_binding_traversal() -> None:
    payload = _request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["bindings"] = cast("Mapping[str, object]", object())

    with pytest.raises(IdentityBindingAuthorizationError):
        preflight_identity_binding_authorization(payload)


def test_direct_evaluator_preflights_before_request_revalidation() -> None:
    request = _request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": ConsentState.WITHHELD}
                    )
                }
            )
        }
    )
    hostile = ValidateIdentityBindingsRequest.model_construct(
        context=denied_context,
        identity_resolution=request.identity_resolution,
        policy=request.policy,
        bindings=cast("tuple[IdentificationArtifactBinding, ...]", object()),
    )

    with pytest.raises(IdentityBindingAuthorizationError):
        evaluate_identity_bindings(hostile)
