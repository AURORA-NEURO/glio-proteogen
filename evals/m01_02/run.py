"""Run the M01-02 locked qualification corpus and emit machine-readable evidence."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, median
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from typing import Any, NotRequired, TypedDict, cast
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from pydantic import TypeAdapter, ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m01_02.canonical import (
    canonical_request_digest,
    resolution_core_digest,
)
from glio_proteogen.contracts.m01_02.schema import (
    CONTRACT_VERSION,
    JSON_SCHEMA_DIALECT,
    SCHEMA_ID_PREFIX,
    ContractName,
    contract_json_schema,
)
from glio_proteogen.contracts.m01_02.v1 import (
    M0102_MAX_ASSERTIONS,
    M0102_MAX_COMPONENT_SIZE,
    M0102_MAX_DEPTH,
    M0102_MAX_ENTITIES,
    M0102_MAX_EVIDENCE,
    M0102_MAX_EVIDENCE_PER_ITEM,
    M0102_MAX_ISSUES,
    M0102_MAX_OBSERVATIONS,
    M0102_MAX_OPERATIONS,
    IdentityComponent,
    IdentityControlRole,
    IdentityLineageResolution,
    IdentityLineageResolutionDraft,
    ReconcileIdentityLineageRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ConsentState, UpstreamDecisionState
from glio_proteogen.kernel.strict_json import (
    MAX_JSON_BYTES,
    StrictJsonError,
    strict_json_loads,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage import (
    service as service_module,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage import (
    solver as solver_module,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    GENESIS_DIGEST,
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    IdentityLineageAuthorizationError,
    M0102Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.solver import (
    ReconciliationAuthorizationError,
    reconcile_identity_lineage,
)

MODULE_ID = "GLIO-PROTEOGEN-M01-02"
ROOT = Path(__file__).parents[2]
SCENARIO_PATH = ROOT / "tests" / "fixtures" / "m01_02" / "scenarios.json"
SNAPSHOT_PATH = ROOT / "tests" / "snapshots" / "m01_02" / "schema_digests.json"
MEAN_BUDGET_NS = 5_000_000
P95_BUDGET_NS = 10_000_000
PUBLIC_SCHEMA_NAMES: tuple[ContractName, ...] = (
    "request",
    "output",
    "policy",
    "entity",
    "operation",
    "resolution",
)
_REQUEST_ADAPTER = TypeAdapter(ReconcileIdentityLineageRequest)
_OUTPUT_ADAPTER = TypeAdapter(IdentityLineageResolution)
_CONCORDANCE_FIELDS = {
    "concordant_observations": "concordant",
    "discordant_observations": "discordant",
    "indeterminate_observations": "indeterminate",
    "missing_observations": "missing",
    "unsupported_observations": "unsupported",
    "excluded_dependent_observations": "excluded_dependent",
}
_EXPECTED_HARD_CAPS = (10_000, 40_000, 20_000, 50_000, 256, 64, 50_000, 64, 1_000)


class ContractExpectation(TypedDict):
    accepted: bool
    error_contains: NotRequired[str]


class ScenarioExpected(TypedDict):
    issue_codes: list[str]
    edge_count: NotRequired[int]
    concordance: NotRequired[dict[str, int]]
    bindings: NotRequired[dict[str, list[str]]]
    same_components: NotRequired[list[list[str]]]
    distinct_components: NotRequired[list[list[str]]]
    quarantined_members: NotRequired[list[str]]


class Scenario(TypedDict):
    case_id: str
    request: dict[str, Any]
    expected: ScenarioExpected
    contract_expectation: ContractExpectation


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class LatencySummary:
    workload: str
    iterations: int
    mean_ns: float
    p50_ns: float
    p95_ns: int
    maximum_ns: int
    mean_budget_ns: int = MEAN_BUDGET_NS
    p95_budget_ns: int = P95_BUDGET_NS


@dataclass(frozen=True, slots=True)
class ScenarioRun:
    scenario: Scenario
    request: ReconcileIdentityLineageRequest
    permuted_request: ReconcileIdentityLineageRequest
    draft: IdentityLineageResolutionDraft


class _PreauthorizationBoundaryViolatedError(AssertionError):
    def __init__(self) -> None:
        super().__init__("analysis, hashing, or persistence ran before authorization")


def _scenarios() -> list[Scenario]:
    corpus = cast("dict[str, Any]", strict_json_loads(SCENARIO_PATH.read_bytes()))
    return cast("list[Scenario]", corpus["scenarios"])


def _strict_request(payload: dict[str, Any]) -> ReconcileIdentityLineageRequest:
    return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(payload), strict=True)


def _contract_checks(
    scenarios: list[Scenario],
) -> tuple[list[EvalCheck], list[tuple[Scenario, ReconcileIdentityLineageRequest]]]:
    checks: list[EvalCheck] = []
    accepted: list[tuple[Scenario, ReconcileIdentityLineageRequest]] = []
    request_validator = Draft202012Validator(
        contract_json_schema("request"),
        format_checker=FormatChecker(),
    )
    for scenario in scenarios:
        expectation = scenario["contract_expectation"]
        try:
            request = _strict_request(scenario["request"])
        except ValidationError as error:
            expected_error = expectation.get("error_contains", "")
            passed = not expectation["accepted"] and expected_error in str(error)
            detail = f"rejected:{expected_error or type(error).__name__}"
        else:
            standard_errors = list(request_validator.iter_errors(scenario["request"]))
            passed = expectation["accepted"] and not standard_errors
            detail = (
                "runtime-and-schema-accepted"
                if passed
                else f"unexpected_acceptance_or_schema_errors={len(standard_errors)}"
            )
            if expectation["accepted"]:
                accepted.append((scenario, request))
        checks.append(EvalCheck(f"contract.{scenario['case_id']}", passed, detail))
    return checks, accepted


def _permuted_request(request: ReconcileIdentityLineageRequest) -> ReconcileIdentityLineageRequest:
    payload = request.model_dump(mode="json")
    payload["policy"]["allowed_operation_kinds"].reverse()
    for entity in payload["entities"]:
        entity["identity_tokens"].reverse()
        entity["evidence"].reverse()
    payload["entities"].reverse()
    for assertion in payload["assertions"]:
        assertion["evidence"].reverse()
    payload["assertions"].reverse()
    for operation in payload["lineage_operations"]:
        operation["source_entity_ids"].reverse()
        operation["target_entity_ids"].reverse()
        for channel in operation["channels"]:
            channel["evidence"].reverse()
        operation["channels"].reverse()
        operation["evidence"].reverse()
    payload["lineage_operations"].reverse()
    for observation in payload["concordance_observations"]:
        observation["evidence"].reverse()
    payload["concordance_observations"].reverse()
    return _strict_request(payload)


def _component_by_member(
    draft: IdentityLineageResolutionDraft,
) -> dict[str, IdentityComponent]:
    return {
        member: component
        for component in draft.components
        for member in component.member_entity_ids
    }


def _component_expectations_match(
    expected: ScenarioExpected,
    component_by_member: dict[str, IdentityComponent],
) -> bool:
    same = all(
        len({component_by_member[member].component_id for member in group}) == 1
        for group in expected.get("same_components", [])
    )
    distinct = all(
        len({component_by_member[member].component_id for member in group}) == len(group)
        for group in expected.get("distinct_components", [])
    )
    return same and distinct


def _binding_expectations_match(
    expected: ScenarioExpected,
    draft: IdentityLineageResolutionDraft,
    component_by_member: dict[str, IdentityComponent],
) -> bool:
    nodes = {node.entity_id: node for node in draft.graph.nodes}
    return all(
        set(nodes[entity_id].subject_component_ids)
        == {component_by_member[subject].component_id for subject in subjects}
        for entity_id, subjects in expected.get("bindings", {}).items()
    )


def _concordance_expectations_match(
    expected: ScenarioExpected,
    draft: IdentityLineageResolutionDraft,
) -> bool:
    return all(
        getattr(draft.concordance, _CONCORDANCE_FIELDS[field]) == count
        for field, count in expected.get("concordance", {}).items()
    )


def _quarantine_expectations_match(
    expected: ScenarioExpected,
    draft: IdentityLineageResolutionDraft,
) -> bool:
    expected_members = set(expected.get("quarantined_members", []))
    known_members = {
        member for component in draft.components for member in component.member_entity_ids
    }
    return not expected_members or (
        draft.decision.value == "quarantined" and expected_members.issubset(known_members)
    )


def _expanded_edge_count(draft: IdentityLineageResolutionDraft) -> int:
    return sum(
        len(operation.source_entity_ids) * len(operation.target_entity_ids)
        for operation in draft.graph.operations
    )


def _public_solver_check(
    scenario: Scenario,
    request: ReconcileIdentityLineageRequest,
) -> tuple[tuple[EvalCheck, EvalCheck], ScenarioRun]:
    before = request.model_dump_json()
    draft = reconcile_identity_lineage(request)
    permuted = _permuted_request(request)
    permuted_draft = reconcile_identity_lineage(permuted)
    expected = scenario["expected"]
    component_by_member = _component_by_member(draft)
    actual_codes = [issue.code for issue in draft.issues]
    semantics = (
        actual_codes == expected["issue_codes"]
        and ("edge_count" not in expected or _expanded_edge_count(draft) == expected["edge_count"])
        and _component_expectations_match(expected, component_by_member)
        and _binding_expectations_match(expected, draft, component_by_member)
        and _concordance_expectations_match(expected, draft)
        and _quarantine_expectations_match(expected, draft)
    )
    deterministic = (
        request.model_dump_json() == before
        and canonical_request_digest(permuted) == canonical_request_digest(request)
        and permuted_draft == draft
        and resolution_core_digest(draft) == draft.core_digest
    )
    detail = (
        f"decision={draft.decision.value};issues={','.join(actual_codes) or 'none'};"
        f"edges={_expanded_edge_count(draft)};components={len(draft.components)}"
    )
    checks = (
        EvalCheck(f"solver.{scenario['case_id']}", semantics, detail),
        EvalCheck(
            f"canonical.{scenario['case_id']}",
            deterministic,
            "request, graph, and resolution-core identity are order-invariant and immutable",
        ),
    )
    return checks, ScenarioRun(scenario, request, permuted, draft)


def _solver_checks(
    accepted: list[tuple[Scenario, ReconcileIdentityLineageRequest]],
) -> tuple[list[EvalCheck], list[ScenarioRun]]:
    evaluated = [_public_solver_check(scenario, request) for scenario, request in accepted]
    return (
        [check for checks, _run in evaluated for check in checks],
        [item[1] for item in evaluated],
    )


def _denied_request(
    request: ReconcileIdentityLineageRequest,
    role: IdentityControlRole,
) -> ReconcileIdentityLineageRequest:
    references = request.context.references
    current = getattr(references, role.value)
    state = (
        ConsentState.WITHHELD
        if role is IdentityControlRole.CONSENT
        else UpstreamDecisionState.REJECTED
    )
    denied_reference = current.model_copy(update={"state": state})
    denied_references = references.model_copy(update={role.value: denied_reference})
    denied_context = request.context.model_copy(update={"references": denied_references})
    return request.model_copy(update={"context": denied_context})


def _authorization_check(reference: ReconcileIdentityLineageRequest) -> EvalCheck:
    roles_passed: set[IdentityControlRole] = set()
    boundary_error = _PreauthorizationBoundaryViolatedError()
    with (
        patch.object(solver_module, "_analyze", side_effect=boundary_error),
        patch.object(
            solver_module,
            "canonical_request_digest",
            side_effect=boundary_error,
        ),
        patch.object(
            service_module,
            "canonical_request_digest",
            side_effect=boundary_error,
        ),
        patch.object(
            service_module,
            "reconcile_identity_lineage",
            side_effect=boundary_error,
        ),
    ):
        for role in IdentityControlRole:
            denied = _denied_request(reference, role)
            try:
                reconcile_identity_lineage(denied)
            except ReconciliationAuthorizationError as error:
                solver_passed = error.role is role
            else:
                solver_passed = False
            raw = denied.model_dump(mode="python")
            try:
                M0102Service(cast("Any", object())).execute(raw)
            except IdentityLineageAuthorizationError as error:
                service_passed = error.role is role
            else:
                service_passed = False
            if solver_passed and service_passed:
                roles_passed.add(role)
    passed = roles_passed == set(IdentityControlRole)
    return EvalCheck(
        "authorization.precedes_analysis_hash_and_io",
        passed,
        f"public_solver_and_service_roles={len(roles_passed)}/{len(IdentityControlRole)}",
    )


def _service_checks(
    runs: list[ScenarioRun],
) -> tuple[list[EvalCheck], list[IdentityLineageResolution], list[dict[str, Any]]]:
    checks: list[EvalCheck] = []
    outputs: list[IdentityLineageResolution] = []
    payloads: list[dict[str, Any]] = []
    output_validator = Draft202012Validator(
        contract_json_schema("output"),
        format_checker=FormatChecker(),
    )
    previous_digest = GENESIS_DIGEST
    with (
        TemporaryDirectory(prefix="m0102-eval-") as directory,
        M0102EventStore(Path(directory) / "identity-lineage.sqlite3") as store,
    ):
        runtime = M0102Service(store)
        for sequence, run in enumerate(runs, start=1):
            before_count = runtime.verify_event_chain().event_count
            output = runtime.execute(run.request)
            after_commit = runtime.verify_event_chain()
            replay = runtime.execute(run.permuted_request)
            after_replay = runtime.verify_event_chain()
            retrieved = runtime.get_resolution(output.resolution_digest)
            record = store.get_resolution(output.resolution_digest)
            strict_round_trip = _OUTPUT_ADAPTER.validate_json(
                canonical_json_bytes(output.model_dump(mode="json")),
                strict=True,
            )
            schema_errors = list(output_validator.iter_errors(output.model_dump(mode="json")))
            exact_replay = output == replay == retrieved == strict_round_trip
            digest_bound = (
                output.core_digest == run.draft.core_digest
                and resolution_core_digest(output) == run.draft.core_digest
            )
            chain_bound = (
                after_commit.valid
                and after_replay.valid
                and after_commit.event_count == before_count + 1 == sequence
                and after_replay.event_count == after_commit.event_count
                and record.sequence == sequence
                and record.previous_digest == previous_digest
                and record.event_digest == output.event_digest
                and "event_digest" not in record.payload
            )
            passed = exact_replay and digest_bound and chain_bound and not schema_errors
            checks.append(
                EvalCheck(
                    f"service.{run.scenario['case_id']}",
                    passed,
                    f"event={sequence};exact_replay={str(exact_replay).lower()};"
                    f"digest_bound={str(digest_bound).lower()};"
                    f"chain_bound={str(chain_bound).lower()};"
                    f"schema_errors={len(schema_errors)}",
                )
            )
            outputs.append(output)
            payloads.append(record.payload)
            previous_digest = record.event_digest
        final = runtime.verify_event_chain()
        checks.append(
            EvalCheck(
                "ledger.exact_replay_and_chain",
                final.valid
                and final.event_count == len(runs)
                and final.head_digest == previous_digest,
                f"events={final.event_count};head={final.head_digest}",
            )
        )
    return checks, outputs, payloads


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list | tuple):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _private_canaries(runs: list[ScenarioRun]) -> set[str]:
    values: set[str] = set()
    allowed_artifacts: set[str] = set()
    for run in runs:
        payload = run.scenario["request"]
        references = payload["context"]["references"]
        allowed_artifacts.update(
            reference["evidence"]["artifact_id"] for reference in references.values()
        )
        for entity in payload["entities"]:
            for token in entity["identity_tokens"]:
                values.add(token["token_digest"])
                values.add(token["evidence"]["artifact_id"])
        for assertion in payload["assertions"]:
            allowed_artifacts.update(item["artifact_id"] for item in assertion["evidence"])
        for operation in payload["lineage_operations"]:
            allowed_artifacts.update(item["artifact_id"] for item in operation["evidence"])
            for channel in operation.get("channels", []):
                values.add(channel["tag_digest"])
                values.update(item["artifact_id"] for item in channel["evidence"])
        for observation in payload["concordance_observations"]:
            allowed_artifacts.update(item["artifact_id"] for item in observation["evidence"])
    return values - allowed_artifacts


def _privacy_canary_request(
    scenarios: list[Scenario],
) -> tuple[ReconcileIdentityLineageRequest, set[str]]:
    source = next(
        scenario
        for scenario in scenarios
        if scenario["case_id"] == "ambiguous_demultiplex_fails_closed"
    )
    payload = copy.deepcopy(source["request"])
    payload["context"]["request_id"] = "request.synthetic.privacy-canary"
    operation = payload["lineage_operations"][0]
    operation["channels"][1]["channel_id"] = "channel-2"
    operation["channels"][1]["tag_digest"] = "sha256:" + ("2" * 64)
    canaries = {channel["tag_digest"] for channel in operation["channels"]}
    subject_id = "pat-privacy"
    shared_subject_evidence = {
        "artifact_id": "artifact.synthetic.privacy-subject",
        "version": "1.0.0",
        "digest": "sha256:" + ("9" * 64),
        "media_type": "application/json",
    }
    for index, entity in enumerate(payload["entities"], start=3):
        entity["composition"] = "single_subject"
        artifact_id = f"private.entity-evidence-{index}"
        entity["evidence"] = [
            {
                "artifact_id": artifact_id,
                "version": "1.0.0",
                "digest": f"sha256:{str(index) * 64}",
                "media_type": "application/json",
            }
        ]
        canaries.add(artifact_id)
    payload["entities"].append(
        {
            "entity_id": subject_id,
            "kind": "patient",
            "composition": "single_subject",
            "identity_tokens": [],
            "evidence": [shared_subject_evidence],
        }
    )
    payload["assertions"] = [
        {
            "assertion_type": "subject_membership",
            "assertion_id": f"assert-privacy-{index}",
            "entity_id": entity["entity_id"],
            "subject_entity_id": subject_id,
            "authority_decision_id": "authority.synthetic.v1",
            "policy_version": "1.0.0",
            "evidence": [shared_subject_evidence],
        }
        for index, entity in enumerate(payload["entities"][:3], start=1)
    ]
    token_digest = "sha256:" + ("1" * 64)
    private_evidence_id = "private.identity-evidence-canary"
    payload["entities"][0]["identity_tokens"] = [
        {
            "issuer_id": "issuer.private-canary",
            "namespace_id": "namespace.private-canary",
            "scope_id": "scope.private-canary",
            "key_id": "key.private-canary",
            "token_version": "1.0.0",
            "entity_kind": "analyte",
            "token_digest": token_digest,
            "evidence": {
                "artifact_id": private_evidence_id,
                "version": "1.0.0",
                "digest": "sha256:" + ("6" * 64),
                "media_type": "application/json",
            },
        }
    ]
    canaries.update((token_digest, private_evidence_id))
    for index, channel in enumerate(operation["channels"], start=7):
        artifact_id = f"private.channel-evidence-{index}"
        channel["evidence"] = [
            {
                "artifact_id": artifact_id,
                "version": "1.0.0",
                "digest": f"sha256:{str(index) * 64}",
                "media_type": "application/json",
            }
        ]
        canaries.add(artifact_id)
    return _strict_request(payload), canaries


def _execute_privacy_canary(
    scenarios: list[Scenario],
) -> tuple[IdentityLineageResolution, dict[str, Any], set[str], bool]:
    request, canaries = _privacy_canary_request(scenarios)
    with (
        TemporaryDirectory(prefix="m0102-privacy-eval-") as directory,
        M0102EventStore(Path(directory) / "privacy.sqlite3") as store,
    ):
        runtime = M0102Service(store)
        output = runtime.execute(request)
        record = store.get_resolution(output.resolution_digest)
        verified = runtime.verify_event_chain()
    qualified = output.decision.value == "resolved" and verified.valid and verified.event_count == 1
    return output, record.payload, canaries, qualified


def _privacy_check(
    scenarios: list[Scenario],
    runs: list[ScenarioRun],
    outputs: list[IdentityLineageResolution],
    payloads: list[dict[str, Any]],
) -> EvalCheck:
    forbidden_keys = {
        "ancestry",
        "authority_decision_id",
        "channel_id",
        "channels",
        "date_of_birth",
        "genotype",
        "identity_tokens",
        "issuer_id",
        "key_id",
        "kinship",
        "medical_record_number",
        "namespace_id",
        "patient_name",
        "raw_allele_counts",
        "raw_reads",
        "scope_id",
        "sex",
        "tag_digest",
        "token_digest",
        "token_version",
        "treatment_recommendation",
    }
    canary_output, canary_payload, canary_values, canary_verified = _execute_privacy_canary(
        scenarios
    )
    public_values: list[object] = [
        *(output.model_dump(mode="json") for output in outputs),
        *payloads,
        canary_output.model_dump(mode="json"),
        canary_payload,
    ]
    leaked_keys = sorted(forbidden_keys.intersection(_all_keys(public_values)))
    rendered = canonical_json_bytes(public_values).decode("utf-8")
    private_values = _private_canaries(runs) | canary_values
    leaked_values = sorted(value for value in private_values if value in rendered)
    persisted_payloads = [*payloads, canary_payload]
    embedded_event_digests = any("event_digest" in payload for payload in persisted_payloads)
    passed = (
        canary_verified and not leaked_keys and not leaked_values and not embedded_event_digests
    )
    detail = (
        "no token, tag, non-causal canary evidence, raw scientific, or direct-identity material"
        if passed
        else (
            f"keys={','.join(leaked_keys) or 'none'};"
            f"canaries={len(leaked_values)};canary_chain={canary_verified};"
            f"embedded_event_digest={embedded_event_digests}"
        )
    )
    return EvalCheck("privacy.public_and_persisted_outputs", passed, detail)


def _uncapped_array_paths(node: object, path: str = "$") -> list[str]:
    if isinstance(node, list):
        return [
            nested
            for index, value in enumerate(node)
            for nested in _uncapped_array_paths(value, f"{path}/{index}")
        ]
    if not isinstance(node, dict):
        return []
    current = [path] if node.get("type") == "array" and "maxItems" not in node else []
    return [
        *current,
        *(
            nested
            for key, value in node.items()
            for nested in _uncapped_array_paths(value, f"{path}/{key}")
        ),
    ]


def _schema_check() -> EvalCheck:
    snapshot = cast("dict[str, Any]", strict_json_loads(SNAPSHOT_PATH.read_bytes()))
    expected = cast("dict[str, dict[str, str]]", snapshot["schemas"])
    passed = (
        snapshot["contract_version"] == CONTRACT_VERSION
        and snapshot["dialect"] == JSON_SCHEMA_DIALECT
        and set(expected) == set(PUBLIC_SCHEMA_NAMES)
    )
    failures: list[str] = []
    for name in PUBLIC_SCHEMA_NAMES:
        document = contract_json_schema(name)
        try:
            Draft202012Validator.check_schema(document)
        except SchemaError:
            failures.append(f"{name}:invalid-dialect")
            continue
        schema_passed = (
            document["$schema"] == JSON_SCHEMA_DIALECT
            and document["$id"] == f"{SCHEMA_ID_PREFIX}:{name}"
            and expected[name]["$id"] == document["$id"]
            and expected[name]["digest"] == sha256_digest(document)
        )
        if not schema_passed:
            failures.append(f"{name}:snapshot-mismatch")
    return EvalCheck(
        "schema.dialect_and_locked_snapshots",
        passed and not failures,
        f"schemas={len(PUBLIC_SCHEMA_NAMES)};failures={','.join(failures) or 'none'}",
    )


def _active_cap_probe(
    scenario: Scenario,
    collection: str,
    policy_limit: str,
    expected_error: str,
) -> bool:
    payload = copy.deepcopy(scenario["request"])
    payload["policy"][policy_limit] = len(payload[collection]) - 1
    try:
        _strict_request(payload)
    except ValidationError as error:
        return expected_error in str(error)
    return False


def _resource_check(scenarios: list[Scenario]) -> EvalCheck:
    by_id = {scenario["case_id"]: scenario for scenario in scenarios}
    probes = (
        _active_cap_probe(
            by_id["complete_ordinary_lineage"],
            "entities",
            "max_entities",
            "entity count exceeds the active policy",
        ),
        _active_cap_probe(
            by_id["complete_ordinary_lineage"],
            "lineage_operations",
            "max_operations",
            "lineage operation count exceeds the active policy",
        ),
        _active_cap_probe(
            by_id["authorized_explicit_same_as"],
            "assertions",
            "max_assertions",
            "assertion count exceeds the active policy",
        ),
        _active_cap_probe(
            by_id["duplicate_concordance_counts_once"],
            "concordance_observations",
            "max_observations",
            "concordance observation count exceeds the active policy",
        ),
    )
    uncapped = [
        path
        for name in PUBLIC_SCHEMA_NAMES
        for path in _uncapped_array_paths(contract_json_schema(name))
    ]
    try:
        strict_json_loads(b" " * (MAX_JSON_BYTES + 1))
    except StrictJsonError:
        transport_cap = True
    else:
        transport_cap = False
    hard_caps = (
        M0102_MAX_ENTITIES,
        M0102_MAX_OPERATIONS,
        M0102_MAX_ASSERTIONS,
        M0102_MAX_OBSERVATIONS,
        M0102_MAX_COMPONENT_SIZE,
        M0102_MAX_DEPTH,
        M0102_MAX_EVIDENCE,
        M0102_MAX_EVIDENCE_PER_ITEM,
        M0102_MAX_ISSUES,
    ) == _EXPECTED_HARD_CAPS
    passed = all(probes) and not uncapped and transport_cap and hard_caps
    return EvalCheck(
        "resource.closed_caps",
        passed,
        (
            f"active_count_probes={sum(probes)}/{len(probes)};"
            f"uncapped_arrays={len(uncapped)};transport_cap={str(transport_cap).lower()};"
            f"maximum_fixture_nodes={M0102_MAX_ENTITIES}"
        ),
    )


def _measure_latency(
    request: ReconcileIdentityLineageRequest,
    iterations: int,
) -> LatencySummary:
    for _ in range(100):
        reconcile_identity_lineage(request)
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        reconcile_identity_lineage(request)
        samples.append(perf_counter_ns() - started)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, (len(ordered) * 95 + 99) // 100 - 1)
    return LatencySummary(
        workload="public_typed_solver",
        iterations=iterations,
        mean_ns=fmean(samples),
        p50_ns=median(samples),
        p95_ns=ordered[p95_index],
        maximum_ns=max(samples),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=1_000)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.iterations < 1:
        _parser().error("--iterations must be positive")
    scenarios = _scenarios()
    contract_checks, accepted = _contract_checks(scenarios)
    solver_checks, runs = _solver_checks(accepted)
    service_checks, outputs, payloads = _service_checks(runs)
    checks = [
        *contract_checks,
        *solver_checks,
        _authorization_check(runs[0].request),
        _schema_check(),
        _resource_check(scenarios),
        *service_checks,
        _privacy_check(scenarios, runs, outputs, payloads),
    ]
    latency = _measure_latency(runs[0].request, args.iterations)
    checks.append(
        EvalCheck(
            "performance.public_typed_solver",
            latency.mean_ns <= latency.mean_budget_ns and latency.p95_ns <= latency.p95_budget_ns,
            f"mean={latency.mean_ns:.0f}ns;p95={latency.p95_ns}ns",
        )
    )
    passed = all(check.passed for check in checks)
    result = {
        "module_id": MODULE_ID,
        "passed": passed,
        "scenario_count": len(scenarios),
        "accepted_scenario_count": len(runs),
        "rejected_scenario_count": len(scenarios) - len(runs),
        "committed_event_count": len(outputs),
        "checks": [asdict(check) for check in checks],
        "latency": asdict(latency),
    }
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(serialized)
    else:
        args.output.write_text(serialized, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
