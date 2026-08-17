"""Replay the locked M02-03 synthetic identification raw-ingestion corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, TypedDict, cast

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m01_03 import Compression, RawFormat, RawIngestionPolicy
from glio_proteogen.contracts.m02_03 import (
    IdentificationIngestionPolicy,
    IdentificationRawIngestionResult,
    IdentificationRawSource,
    IngestIdentificationRawInputsRequest,
    RawInputRole,
    RawSourceDescriptor,
    RoleFormatRequirement,
    RoleRequirement,
    configuration_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c02_identification_qc.m02_03_raw_ingestion import (
    IdentificationRawIngestionAuthorizationError,
    evaluate_identification_raw_ingestion,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M02-03"
ROOT: Final = Path(__file__).parents[2]
RAW_FIXTURE_ROOT: Final = ROOT / "tests" / "fixtures" / "m01_03"
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m02_03" / "scenarios.json"
EXPECTED_SCENARIO_COUNT: Final = 8
EXPECTED_SCENARIOS: Final = (
    ("conformant_required_bundle", "none", "accepted", None),
    (
        "gzip_magic_over_extension",
        "gzip_sequence_database_with_generic_filename",
        "accepted",
        "extension_content_mismatch",
    ),
    (
        "extension_content_mismatch",
        "mzml_named_as_fasta",
        "accepted",
        "extension_content_mismatch",
    ),
    (
        "checksum_mismatch_rejected",
        "wrong_transport_digest",
        "rejected",
        "checksum_mismatch",
    ),
    (
        "malformed_content_quarantined",
        "truncated_mzml",
        "quarantined",
        "malformed_content",
    ),
    (
        "required_role_missing",
        "remove_peptide_identifications",
        "quarantined",
        "required_role_missing",
    ),
    (
        "role_format_mismatch",
        "assign_vcf_to_spectra_role",
        "quarantined",
        "role_format_mismatch",
    ),
    (
        "consent_denied_preflight",
        "withheld_consent_and_unreadable_sources",
        "boundary_rejected",
        "authorization_denied",
    ),
)


class Scenario(TypedDict):
    id: str
    mutation: str
    expected_disposition: str
    expected_code: str | None


class Corpus(TypedDict):
    module_id: str
    contract_version: str
    claims_ceiling: str
    scenarios: list[Scenario]


@dataclass(frozen=True, slots=True)
class ScenarioSubmission:
    """One fully public request plus its separately supplied byte boundary."""

    request: IngestIdentificationRawInputsRequest
    sources: dict[str, bytes]
    filenames: dict[str, str]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _bytes(name: str) -> bytes:
    return (RAW_FIXTURE_ROOT / name).read_bytes()


def _content_digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _artifact(
    label: str,
    digest: str | None = None,
    *,
    media_type: str = "application/json",
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m0203.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"m0203": label}),
        media_type=media_type,
    )


def _policy() -> IdentificationIngestionPolicy:
    base_policy = RawIngestionPolicy(
        policy_id="policy.synthetic.m0203.parser",
        version="1.0.0",
        allowed_formats=tuple(RawFormat),
        allowed_compressions=tuple(Compression),
        max_source_bytes=16_384,
        max_decoded_bytes=32_768,
        max_sources=16,
        max_diagnostics_per_source=16,
        require_checksum=True,
    )
    formats = {
        RawInputRole.SPECTRA: (RawFormat.MZML,),
        RawInputRole.PEPTIDE_IDENTIFICATIONS: (RawFormat.MZIDENTML,),
        RawInputRole.SEQUENCE_DATABASE: (RawFormat.FASTA,),
        RawInputRole.GENOMIC_VARIANTS: (RawFormat.VCF,),
        RawInputRole.TRANSCRIPT_ANNOTATIONS: (RawFormat.GFF3,),
        RawInputRole.PTM_ANNOTATIONS: (RawFormat.MZTAB_M,),
    }
    required = {
        RawInputRole.SPECTRA,
        RawInputRole.PEPTIDE_IDENTIFICATIONS,
        RawInputRole.SEQUENCE_DATABASE,
    }
    return IdentificationIngestionPolicy(
        policy_id="policy.synthetic.m0203.identification-raw",
        version="1.0.0",
        base_policy=base_policy,
        role_requirements=tuple(
            RoleFormatRequirement(
                role=role,
                requirement=(
                    RoleRequirement.REQUIRED
                    if role in required
                    else RoleRequirement.OPTIONAL
                ),
                allowed_formats=formats[role],
                min_sources=1 if role in required else 0,
                max_sources=2,
            )
            for role in RawInputRole
        ),
    )


def _context(policy: IdentificationIngestionPolicy) -> ExecutionContext:
    def accepted(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.m0203.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control.{role}", digest),
        )

    return ExecutionContext(
        request_id="request.synthetic.m0203",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 12, 18, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted("configuration", configuration_digest(policy)),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.m0203.identity-lineage",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"m0203": "identity-lineage"}),
                evidence=_artifact("control.identity-lineage"),
            ),
            provenance=accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.m0203.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control.consent"),
            ),
            quality=accepted("quality"),
            support=accepted("support"),
            intended_use=accepted("intended-use"),
        ),
    )


def _source(  # noqa: PLR0913 - explicit synthetic source dimensions.
    role: RawInputRole,
    label: str,
    payload: bytes,
    declared_format: RawFormat | None,
    *,
    declared_compression: Compression = Compression.NONE,
    digest: str | None = None,
) -> IdentificationRawSource:
    return IdentificationRawSource(
        role=role,
        source=RawSourceDescriptor(
            source_id=f"source.synthetic.m0203.{label}",
            artifact=_artifact(
                f"source.{label}",
                digest or _content_digest(payload),
                media_type="application/octet-stream",
            ),
            byte_length=len(payload),
            declared_format=declared_format,
            declared_compression=declared_compression,
        ),
    )


def _required_entries() -> list[tuple[IdentificationRawSource, bytes, str]]:
    spectra = _bytes("mzml.valid.mzML")
    identifications = _bytes("mzidentml.valid.mzid")
    database = _bytes("proteins.valid.fasta")
    return [
        (
            _source(RawInputRole.SPECTRA, "spectra", spectra, RawFormat.MZML),
            spectra,
            "spectra.mzML",
        ),
        (
            _source(
                RawInputRole.PEPTIDE_IDENTIFICATIONS,
                "peptide-identifications",
                identifications,
                RawFormat.MZIDENTML,
            ),
            identifications,
            "identifications.mzid",
        ),
        (
            _source(
                RawInputRole.SEQUENCE_DATABASE,
                "sequence-database",
                database,
                RawFormat.FASTA,
            ),
            database,
            "database.fasta",
        ),
    ]


def _submission(
    entries: list[tuple[IdentificationRawSource, bytes, str]],
) -> ScenarioSubmission:
    policy = _policy()
    sources = tuple(entry[0] for entry in entries)
    return ScenarioSubmission(
        request=IngestIdentificationRawInputsRequest(
            context=_context(policy),
            policy=policy,
            sources=sources,
        ),
        sources={entry[0].source.source_id: entry[1] for entry in entries},
        filenames={entry[0].source.source_id: entry[2] for entry in entries},
    )


def build_scenario_submission(mutation: str = "none") -> ScenarioSubmission:
    """Build one deterministic scenario through the public M02-03 contract."""

    entries = _required_entries()
    if mutation == "gzip_sequence_database_with_generic_filename":
        payload = _bytes("proteins.valid.fasta.gz")
        entries[2] = (
            _source(
                RawInputRole.SEQUENCE_DATABASE,
                "sequence-database",
                payload,
                RawFormat.FASTA,
                declared_compression=Compression.GZIP,
            ),
            payload,
            "database.bin",
        )
    elif mutation == "mzml_named_as_fasta":
        item, payload, _ = entries[0]
        entries[0] = (item, payload, "spectra.fasta")
    elif mutation == "wrong_transport_digest":
        payload = entries[0][1]
        entries[0] = (
            _source(
                RawInputRole.SPECTRA,
                "spectra",
                payload,
                RawFormat.MZML,
                digest=sha256_digest({"m0203": "wrong-transport-digest"}),
            ),
            payload,
            "spectra.mzML",
        )
    elif mutation == "truncated_mzml":
        payload = _bytes("mzml.truncated.invalid.mzML")
        entries[0] = (
            _source(RawInputRole.SPECTRA, "spectra", payload, RawFormat.MZML),
            payload,
            "spectra.mzML",
        )
    elif mutation == "remove_peptide_identifications":
        entries = [
            entry
            for entry in entries
            if entry[0].role is not RawInputRole.PEPTIDE_IDENTIFICATIONS
        ]
    elif mutation == "assign_vcf_to_spectra_role":
        payload = _bytes("variants.valid.vcf")
        entries[0] = (
            _source(RawInputRole.SPECTRA, "spectra", payload, None),
            payload,
            "spectra.vcf",
        )
    elif mutation not in {"none", "withheld_consent_and_unreadable_sources"}:
        raise ValueError(mutation)
    return _submission(entries)


def build_representative_submission() -> ScenarioSubmission:
    """Build a six-role bundle for the broad public benchmark."""

    entries = _required_entries()
    optional = (
        (RawInputRole.GENOMIC_VARIANTS, "genomic-variants", "variants.valid.vcf", RawFormat.VCF),
        (
            RawInputRole.TRANSCRIPT_ANNOTATIONS,
            "transcript-annotations",
            "annotations.valid.gff3",
            RawFormat.GFF3,
        ),
        (RawInputRole.PTM_ANNOTATIONS, "ptm-annotations", "mztab_m.valid.mzTab", RawFormat.MZTAB_M),
    )
    for role, label, filename, raw_format in optional:
        payload = _bytes(filename)
        entries.append((_source(role, label, payload, raw_format), payload, filename))
    return _submission(entries)


def _diagnostic_codes(result: IdentificationRawIngestionResult) -> set[str]:
    return {
        *(item.code.value for item in result.bundle_diagnostics),
        *(
            diagnostic.code
            for item in result.raw_inputs
            for diagnostic in item.raw_input.diagnostics
        ),
    }


class _UnreadableSources(Mapping[str, bytes]):
    _MESSAGE = "source mapping was traversed"

    def __getitem__(self, key: str) -> bytes:
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        raise AssertionError(self._MESSAGE)

    def __len__(self) -> int:
        raise AssertionError(self._MESSAGE)


def _scenario_check(
    scenario: Scenario,
) -> tuple[EvalCheck, IdentificationRawIngestionResult | None]:
    submission = build_scenario_submission(scenario["mutation"])
    if scenario["mutation"] == "withheld_consent_and_unreadable_sources":
        request = submission.request.model_dump(mode="python")
        request["context"]["references"]["consent"]["state"] = "withheld"
        request["sources"] = object()
        try:
            evaluate_identification_raw_ingestion(request, _UnreadableSources())
        except IdentificationRawIngestionAuthorizationError:
            return (
                EvalCheck(
                    name=f"scenario.{scenario['id']}",
                    passed=(
                        scenario["expected_disposition"] == "boundary_rejected"
                        and scenario["expected_code"] == "authorization_denied"
                    ),
                    detail="disposition=boundary_rejected;diagnostics=authorization_denied",
                ),
                None,
            )
        return (
            EvalCheck(
                name=f"scenario.{scenario['id']}",
                passed=False,
                detail="authorization was not rejected",
            ),
            None,
        )
    result = evaluate_identification_raw_ingestion(
        submission.request,
        submission.sources,
        submission.filenames,
    )
    codes = _diagnostic_codes(result)
    expected_code = scenario["expected_code"]
    passed = result.disposition.value == scenario["expected_disposition"] and (
        (expected_code is None and not codes)
        or (expected_code is not None and expected_code in codes)
    )
    return (
        EvalCheck(
            name=f"scenario.{scenario['id']}",
            passed=passed,
            detail=(
                f"disposition={result.disposition.value};"
                f"diagnostics={','.join(sorted(codes)) or 'none'}"
            ),
        ),
        result,
    )


def _determinism_check() -> tuple[EvalCheck, IdentificationRawIngestionResult]:
    submission = build_scenario_submission()
    request = submission.request
    reversed_policy = request.policy.model_copy(
        update={
            "base_policy": request.policy.base_policy.model_copy(
                update={
                    "allowed_formats": tuple(reversed(request.policy.base_policy.allowed_formats)),
                    "allowed_compressions": tuple(
                        reversed(request.policy.base_policy.allowed_compressions)
                    ),
                }
            ),
            "role_requirements": tuple(
                item.model_copy(update={"allowed_formats": tuple(reversed(item.allowed_formats))})
                for item in reversed(request.policy.role_requirements)
            ),
        }
    )
    reversed_request = request.model_copy(
        update={
            "policy": reversed_policy,
            "sources": tuple(reversed(request.sources)),
        }
    )
    direct = evaluate_identification_raw_ingestion(
        request,
        submission.sources,
        submission.filenames,
    )
    replay = evaluate_identification_raw_ingestion(
        reversed_request,
        dict(reversed(tuple(submission.sources.items()))),
        dict(reversed(tuple(submission.filenames.items()))),
    )
    passed = direct == replay and direct.model_dump_json() == replay.model_dump_json()
    return (
        EvalCheck(
            name="determinism.full_output_semantic_order",
            passed=passed,
            detail=f"result_digest={direct.result_digest}",
        ),
        direct,
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _privacy_check(results: list[IdentificationRawIngestionResult]) -> EvalCheck:
    values = [item.model_dump(mode="json") for item in results]
    forbidden_keys = {
        "content",
        "file_path",
        "kinase_activity",
        "path",
        "patient_id",
        "proteotype",
        "raw_bytes",
        "raw_content",
        "scientific_interpretation",
        "sequence",
        "subject_id",
        "treatment_recommendation",
    }
    canaries = {
        "MPEPTIDE",
        "SYNTHETIC_SAMPLE",
        "synthetic-identification",
        "synthetic-run-1",
        "synthetic_protein_1",
    }
    leaked_keys = sorted(_all_keys(values) & forbidden_keys)
    rendered = canonical_json_bytes(values).decode("utf-8")
    leaked_values = sorted(canary for canary in canaries if canary in rendered)
    passed = not leaked_keys and not leaked_values
    return EvalCheck(
        name="boundary.closed_metadata_only_output",
        passed=passed,
        detail=(
            "no raw scientific payload or prohibited claim fields"
            if passed
            else (
                f"keys={','.join(leaked_keys) or 'none'};"
                f"values={','.join(leaked_values) or 'none'}"
            )
        ),
    )


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _corpus_lock_check(corpus: Corpus) -> EvalCheck:
    observed = tuple(
        (
            scenario["id"],
            scenario["mutation"],
            scenario["expected_disposition"],
            scenario["expected_code"],
        )
        for scenario in corpus["scenarios"]
    )
    passed = (
        corpus["module_id"] == MODULE_ID
        and corpus["contract_version"] == "1.0.0"
        and len(corpus["scenarios"]) == EXPECTED_SCENARIO_COUNT
        and observed == EXPECTED_SCENARIOS
    )
    return EvalCheck(
        name="corpus.locked_eight_scenarios",
        passed=passed,
        detail=f"scenario_count={len(corpus['scenarios'])}",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _corpus()
    checks = [_corpus_lock_check(corpus)]
    results: list[IdentificationRawIngestionResult] = []
    for scenario in corpus["scenarios"]:
        check, result = _scenario_check(scenario)
        checks.append(check)
        if result is not None:
            results.append(result)
    determinism, canonical_result = _determinism_check()
    checks.extend((determinism, _privacy_check([*results, canonical_result])))
    passed = all(check.passed for check in checks)
    report = {
        "module_id": MODULE_ID,
        "passed": passed,
        "scenario_count": len(corpus["scenarios"]),
        "corpus_digest": sha256_digest(corpus),
        "checks": [asdict(check) for check in checks],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
