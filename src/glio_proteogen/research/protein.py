"""Ambiguity-preserving protein-group inference from peptide evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .search import Psm

from .search import _is_finite_real, _validate_target_decoy_psm

_GROUP_IDENTIFIABILITY = frozenset(
    {
        "target_decoy_collision",
        "shared_only_ambiguous",
        "partially_unique_ambiguous",
        "unique_peptide_supported",
    }
)


@dataclass(frozen=True, slots=True)
class ProteinGroup:
    accessions: tuple[str, ...]
    unique_peptides: tuple[str, ...]
    shared_peptides: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProteinGroupCandidate:
    """A target/decoy-aware protein-group candidate.

    This is deliberately an auditable research candidate, not a calibrated
    protein probability.  Collision groups are retained with a null q-value
    and can never be promoted to a reportable group.
    """

    accessions: tuple[str, ...]
    unique_peptides: tuple[str, ...]
    shared_peptides: tuple[str, ...]
    score: float
    supporting_psms: int
    status: str
    q_value: float | None
    acceptance: str
    identifiability: str = "unique_peptide_supported"
    unique_supported_accessions: tuple[str, ...] = ()
    ambiguous_accessions: tuple[str, ...] = ()
    evidence_digest: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "acceptance": self.acceptance,
            "accessions": list(self.accessions),
            "identifiability": self.identifiability,
            "q_value": self.q_value,
            "score": self.score,
            "shared_peptides": list(self.shared_peptides),
            "status": self.status,
            "supporting_psms": self.supporting_psms,
            "unique_supported_accessions": list(self.unique_supported_accessions),
            "ambiguous_accessions": list(self.ambiguous_accessions),
            "evidence_digest": self.evidence_digest,
            "unique_peptides": list(self.unique_peptides),
        }


@dataclass(frozen=True, slots=True)
class ProteinGroupFdrSummary:
    """Monotone target/decoy evidence at the protein-group level."""

    method: str
    candidates: int
    target_candidates: int
    decoy_candidates: int
    collision_candidates: int
    accepted_targets: int
    q_value_threshold: float
    max_accepted_q_value: float | None
    decoy_to_target_ratio: float | None
    input_psms: int = 0
    unique_spectra: int = 0
    duplicate_spectrum_psms: int = 0
    competition_digest: str = ""
    shared_peptide_candidates: int = 0
    shared_only_candidates: int = 0
    partially_unique_candidates: int = 0
    error_candidates: int = 0
    target_denominator: int = 0
    evidence_status: str = "not_evaluated"
    group_partition_digest: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "accepted_targets": self.accepted_targets,
            "candidates": self.candidates,
            "collision_candidates": self.collision_candidates,
            "decoy_candidates": self.decoy_candidates,
            "decoy_to_target_ratio": self.decoy_to_target_ratio,
            "duplicate_spectrum_psms": self.duplicate_spectrum_psms,
            "competition_digest": self.competition_digest,
            "input_psms": self.input_psms,
            "max_accepted_q_value": self.max_accepted_q_value,
            "method": self.method,
            "q_value_threshold": self.q_value_threshold,
            "target_candidates": self.target_candidates,
            "shared_only_candidates": self.shared_only_candidates,
            "shared_peptide_candidates": self.shared_peptide_candidates,
            "unique_spectra": self.unique_spectra,
            "partially_unique_candidates": self.partially_unique_candidates,
            "error_candidates": self.error_candidates,
            "target_denominator": self.target_denominator,
            "evidence_status": self.evidence_status,
            "group_partition_digest": self.group_partition_digest,
        }


def infer_protein_groups(
    peptide_to_proteins: dict[str, tuple[str, ...]],
) -> tuple[ProteinGroup, ...]:
    """Return disjoint bipartite components while retaining shared-peptide ambiguity.

    A greedy protein parsimony pass can emit overlapping groups when a shared
    peptide is consumed by one representative and a unique peptide later
    selects another protein.  Components give every protein and peptide exactly
    one deterministic group; shared peptides remain explicitly marked instead
    of being silently assigned to one protein.
    """
    remaining = {
        peptide: {protein for protein in proteins if protein}
        for peptide, proteins in peptide_to_proteins.items()
        if proteins and any(protein for protein in proteins)
    }
    groups: list[ProteinGroup] = []
    while remaining:
        seed = min(remaining)
        component_peptides = {seed}
        component_proteins: set[str] = set()
        frontier = [seed]
        while frontier:
            peptide = frontier.pop()
            for protein in remaining[peptide]:
                if protein in component_proteins:
                    continue
                component_proteins.add(protein)
                linked = [
                    linked_peptide
                    for linked_peptide, proteins in remaining.items()
                    if protein in proteins and linked_peptide not in component_peptides
                ]
                component_peptides.update(linked)
                frontier.extend(linked)
        accessions = tuple(sorted(component_proteins))
        unique = tuple(
            sorted(peptide for peptide in component_peptides if len(remaining[peptide]) == 1)
        )
        shared = tuple(
            sorted(peptide for peptide in component_peptides if len(remaining[peptide]) > 1)
        )
        groups.append(ProteinGroup(accessions, unique, shared))
        for peptide in component_peptides:
            remaining.pop(peptide, None)
    return tuple(groups)


def infer_protein_group_candidates(
    psms: tuple[Psm, ...], *, q_value_threshold: float, decoy_prefix: str = "DECOY_"
) -> tuple[tuple[ProteinGroupCandidate, ...], ProteinGroupFdrSummary]:
    """Build deterministic group candidates from *all* scored PSMs.

    Group score is the maximum supporting PSM score.  Target/decoy groups are
    counted separately and receive monotone q-values; mixed target/decoy
    groups are collision evidence and are conservatively abstained.  No group
    is accepted merely because its best peptide passed peptide-level FDR.
    """

    if not _is_finite_real(q_value_threshold) or not 0 <= q_value_threshold <= 1:
        raise ValueError("q_value_threshold must be finite and between zero and one")
    _validate_decoy_prefix(decoy_prefix)
    input_psms, psms, competition_digest = _prepare_group_psms(psms, decoy_prefix=decoy_prefix)
    peptide_to_proteins: dict[str, set[str]] = {}
    for psm in psms:
        if not isinstance(psm.peptide, str) or not psm.peptide:
            raise ValueError("PSM peptide must be a non-empty string")
        if not _is_finite_real(psm.score) or psm.score < 0:
            raise ValueError("PSM scores must be finite and non-negative")
        peptide_to_proteins.setdefault(psm.peptide, set()).update(psm.protein_accessions)
    groups = infer_protein_groups(
        {peptide: tuple(sorted(accessions)) for peptide, accessions in peptide_to_proteins.items()}
    )
    candidates: list[ProteinGroupCandidate] = []
    supporting_by_accessions: dict[tuple[str, ...], tuple[Psm, ...]] = {}
    for group in groups:
        supporting = tuple(
            psm for psm in psms if set(psm.protein_accessions).intersection(group.accessions)
        )
        if not supporting:
            continue
        has_decoy = any(accession.startswith(decoy_prefix) for accession in group.accessions)
        has_target = any(not accession.startswith(decoy_prefix) for accession in group.accessions)
        status = "collision" if has_decoy and has_target else "decoy" if has_decoy else "target"
        identifiability, unique_supported, ambiguous = _group_support_metadata(
            group, peptide_to_proteins, status
        )
        candidates.append(
            ProteinGroupCandidate(
                accessions=group.accessions,
                unique_peptides=group.unique_peptides,
                shared_peptides=group.shared_peptides,
                score=max(item.score for item in supporting),
                supporting_psms=len(supporting),
                status=status,
                q_value=None,
                acceptance="abstained" if status == "collision" else "pending",
                identifiability=identifiability,
                unique_supported_accessions=unique_supported,
                ambiguous_accessions=ambiguous,
            )
        )
        supporting_by_accessions[group.accessions] = supporting
    ordered = sorted(
        candidates,
        key=lambda item: (
            -item.score,
            # Equal-score decoy/collision evidence must be processed before a
            # target, otherwise the target receives an artificially low q-value.
            {"collision": 0, "decoy": 1, "target": 2}[item.status],
            item.accessions,
        ),
    )
    has_decoy_evidence = any(candidate.status in {"decoy", "collision"} for candidate in ordered)
    decoys = 0
    targets = 0
    raw: list[tuple[ProteinGroupCandidate, float | None]] = []
    for candidate in ordered:
        if candidate.status == "collision":
            # A mixed target/decoy group is never reportable, but it is still
            # decoy evidence for conservative group-level FDR estimation.
            decoys += 1
            raw.append((candidate, None))
            continue
        decoys += int(candidate.status == "decoy")
        targets += int(candidate.status == "target")
        raw.append((candidate, decoys / max(targets, 1)))
    running = 1.0
    by_accessions: dict[tuple[str, ...], ProteinGroupCandidate] = {}
    for candidate, value in reversed(raw):
        if value is not None:
            running = min(running, value)
        q_value = None if candidate.status != "target" or not has_decoy_evidence else running
        acceptance = (
            "accepted"
            if (
                candidate.status == "target"
                and candidate.identifiability == "unique_peptide_supported"
                and q_value is not None
                and q_value <= q_value_threshold
            )
            else "abstained"
            if candidate.identifiability in {"shared_only_ambiguous", "partially_unique_ambiguous"}
            else "rejected"
            if candidate.status != "collision"
            else "abstained"
        )
        finalized_candidate = ProteinGroupCandidate(
            accessions=candidate.accessions,
            unique_peptides=candidate.unique_peptides,
            shared_peptides=candidate.shared_peptides,
            score=candidate.score,
            supporting_psms=candidate.supporting_psms,
            status=candidate.status,
            q_value=q_value,
            acceptance=acceptance,
            identifiability=candidate.identifiability,
            unique_supported_accessions=candidate.unique_supported_accessions,
            ambiguous_accessions=candidate.ambiguous_accessions,
            evidence_digest="",
        )
        by_accessions[candidate.accessions] = _with_group_evidence_digest(
            finalized_candidate, supporting_by_accessions[candidate.accessions]
        )
    finalized = tuple(sorted(by_accessions.values(), key=lambda item: item.accessions))
    summary = _build_group_fdr_summary(
        finalized,
        q_value_threshold=q_value_threshold,
        input_psms=input_psms,
        unique_psms=psms,
        competition_digest=competition_digest,
    )
    verify_protein_group_fdr_summary(finalized, summary)
    return finalized, summary


def _group_support_metadata(
    group: ProteinGroup, peptide_to_proteins: dict[str, set[str]], status: str
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Classify group identifiability and retain the supporting accession sets.

    A connected component can contain one accession with a unique peptide and
    another accession linked only through shared peptides.  Keeping both sets
    in the receipt prevents downstream consumers from silently treating a
    partially supported component as a fully identified protein group.
    """

    if status == "collision":
        return "target_decoy_collision", (), tuple(sorted(group.accessions))
    uniquely_supported = {
        accession
        for peptide in group.unique_peptides
        for accession in peptide_to_proteins[peptide]
        if accession in group.accessions
    }
    unique_supported = tuple(sorted(uniquely_supported))
    ambiguous = tuple(sorted(set(group.accessions) - set(unique_supported)))
    if not group.unique_peptides:
        return "shared_only_ambiguous", unique_supported, ambiguous
    if ambiguous:
        return "partially_unique_ambiguous", unique_supported, ambiguous
    return "unique_peptide_supported", unique_supported, ambiguous


def _build_group_fdr_summary(
    candidates: tuple[ProteinGroupCandidate, ...],
    *,
    q_value_threshold: float,
    input_psms: tuple[Psm, ...],
    unique_psms: tuple[Psm, ...],
    competition_digest: str,
) -> ProteinGroupFdrSummary:
    accepted_q = tuple(
        item.q_value
        for item in candidates
        if item.acceptance == "accepted" and item.q_value is not None
    )
    target_candidates = sum(item.status == "target" for item in candidates)
    decoy_candidates = sum(item.status == "decoy" for item in candidates)
    collision_candidates = sum(item.status == "collision" for item in candidates)
    error_candidates = decoy_candidates + collision_candidates
    evidence_status = (
        "abstained_no_group_candidates"
        if not candidates
        else "abstained_no_decoy_evidence"
        if error_candidates == 0
        else "abstained_no_target_denominator"
        if target_candidates == 0
        else "empirical_target_decoy_evidence"
    )
    return ProteinGroupFdrSummary(
        method="max-psm-score-monotone-group-target-decoy-collision-abstain-ties-6-qvalue",
        candidates=len(candidates),
        target_candidates=target_candidates,
        decoy_candidates=decoy_candidates,
        collision_candidates=collision_candidates,
        accepted_targets=len(accepted_q),
        q_value_threshold=q_value_threshold,
        max_accepted_q_value=max(accepted_q) if accepted_q else None,
        decoy_to_target_ratio=(error_candidates / target_candidates if target_candidates else None),
        input_psms=len(input_psms),
        unique_spectra=len(unique_psms),
        duplicate_spectrum_psms=len(input_psms) - len(unique_psms),
        competition_digest=competition_digest,
        shared_peptide_candidates=sum(bool(item.shared_peptides) for item in candidates),
        shared_only_candidates=sum(
            item.identifiability == "shared_only_ambiguous" for item in candidates
        ),
        partially_unique_candidates=sum(
            item.identifiability == "partially_unique_ambiguous" for item in candidates
        ),
        error_candidates=error_candidates,
        target_denominator=target_candidates,
        evidence_status=evidence_status,
        group_partition_digest=_group_partition_digest(candidates),
    )


def verify_protein_group_fdr_summary(  # noqa: PLR0915
    candidates: tuple[ProteinGroupCandidate, ...], summary: ProteinGroupFdrSummary
) -> None:
    """Verify group partition, ambiguity, and FDR receipt invariants.

    This is descriptive research evidence, not a calibrated protein
    probability.  The verifier is deliberately public so callers cannot
    replace group semantics while retaining an apparently valid summary.
    """

    if not isinstance(summary, ProteinGroupFdrSummary):
        raise TypeError("summary must be a ProteinGroupFdrSummary")
    if tuple(sorted(candidates, key=lambda item: item.accessions)) != candidates:
        raise ValueError("protein-group candidates must be sorted by accession")
    if len({item.accessions for item in candidates}) != len(candidates):
        raise ValueError("protein-group accessions must be unique")
    if not _is_finite_real(summary.q_value_threshold) or not 0 <= summary.q_value_threshold <= 1:
        raise ValueError("group-FDR q-value threshold must be finite and between zero and one")
    for candidate in candidates:
        if not candidate.accessions or tuple(sorted(candidate.accessions)) != candidate.accessions:
            raise ValueError("protein-group accessions must be non-empty and sorted")
        if candidate.identifiability not in _GROUP_IDENTIFIABILITY:
            raise ValueError("protein-group identifiability is invalid")
        if (
            tuple(sorted(candidate.unique_peptides)) != candidate.unique_peptides
            or tuple(sorted(candidate.shared_peptides)) != candidate.shared_peptides
        ):
            raise ValueError("protein-group peptide memberships must be sorted")
        if set(candidate.unique_peptides).intersection(candidate.shared_peptides):
            raise ValueError("unique and shared peptide memberships must be disjoint")
        if candidate.status not in {"target", "decoy", "collision"}:
            raise ValueError("protein-group candidate status is invalid")
        if candidate.acceptance not in {"pending", "accepted", "rejected", "abstained"}:
            raise ValueError("protein-group candidate acceptance is invalid")
        if candidate.q_value is not None and (
            not _is_finite_real(candidate.q_value) or not 0 <= candidate.q_value <= 1
        ):
            raise ValueError("protein-group q-values must be finite and between zero and one")
        if len(candidate.evidence_digest) != 64 or not _is_hex_digest(candidate.evidence_digest):
            raise ValueError("protein-group evidence digest is invalid")
        support_accessions = set(candidate.unique_supported_accessions).union(
            candidate.ambiguous_accessions
        )
        if support_accessions != set(candidate.accessions):
            raise ValueError("protein-group support accessions do not cover the group")
        if candidate.status == "collision":
            if candidate.identifiability != "target_decoy_collision":
                raise ValueError("collision groups must declare collision identifiability")
        elif candidate.identifiability == "target_decoy_collision":
            raise ValueError("non-collision groups cannot declare collision identifiability")
        if candidate.status != "target":
            if candidate.q_value is not None:
                raise ValueError("decoy and collision groups must have null q-values")
            if candidate.acceptance == "accepted":
                raise ValueError("decoy and collision groups cannot be accepted")
        elif candidate.acceptance == "accepted" and (
            candidate.q_value is None or candidate.identifiability != "unique_peptide_supported"
        ):
            raise ValueError("accepted target groups require unique support and a q-value")
        elif candidate.acceptance == "accepted" and candidate.q_value > summary.q_value_threshold:
            raise ValueError("accepted target q-value exceeds the group-FDR threshold")
        if candidate.status == "collision" and (
            candidate.q_value is not None or candidate.acceptance != "abstained"
        ):
            raise ValueError("collision groups must remain null-q abstentions")
        if candidate.identifiability in {
            "shared_only_ambiguous",
            "partially_unique_ambiguous",
        } and (candidate.acceptance != "abstained"):
            raise ValueError("ambiguous groups must remain abstentions")
        if (
            tuple(sorted(candidate.unique_supported_accessions))
            != candidate.unique_supported_accessions
        ):
            raise ValueError("unique supported accessions must be sorted")
        if tuple(sorted(candidate.ambiguous_accessions)) != candidate.ambiguous_accessions:
            raise ValueError("ambiguous accessions must be sorted")
        if set(candidate.unique_supported_accessions).intersection(candidate.ambiguous_accessions):
            raise ValueError("support accession sets must be disjoint")
    if summary.candidates != len(candidates):
        raise ValueError("group-FDR candidate count does not match candidates")
    if summary.target_candidates != sum(item.status == "target" for item in candidates):
        raise ValueError("group-FDR target count does not match candidates")
    if summary.decoy_candidates != sum(item.status == "decoy" for item in candidates):
        raise ValueError("group-FDR decoy count does not match candidates")
    if summary.collision_candidates != sum(item.status == "collision" for item in candidates):
        raise ValueError("group-FDR collision count does not match candidates")
    if summary.accepted_targets != sum(item.acceptance == "accepted" for item in candidates):
        raise ValueError("group-FDR accepted count does not match candidates")
    accepted_q_values = tuple(
        item.q_value
        for item in candidates
        if item.acceptance == "accepted" and item.q_value is not None
    )
    expected_max_accepted_q = max(accepted_q_values) if accepted_q_values else None
    if summary.max_accepted_q_value != expected_max_accepted_q:
        raise ValueError("group-FDR maximum accepted q-value does not match candidates")
    expected_errors = summary.decoy_candidates + summary.collision_candidates
    if summary.error_candidates != expected_errors:
        raise ValueError("group-FDR error count does not match candidates")
    if summary.target_denominator != summary.target_candidates:
        raise ValueError("group-FDR target denominator does not match candidates")
    expected_status = (
        "abstained_no_group_candidates"
        if not candidates
        else "abstained_no_decoy_evidence"
        if expected_errors == 0
        else "abstained_no_target_denominator"
        if summary.target_denominator == 0
        else "empirical_target_decoy_evidence"
    )
    if summary.evidence_status != expected_status:
        raise ValueError("group-FDR evidence status does not match candidates")
    expected_ratio = (
        expected_errors / summary.target_denominator if summary.target_denominator else None
    )
    if summary.decoy_to_target_ratio != expected_ratio:
        raise ValueError("group-FDR ratio does not match candidates")
    if summary.group_partition_digest != _group_partition_digest(candidates):
        raise ValueError("group-FDR partition digest does not match candidates")


def _group_partition_digest(candidates: tuple[ProteinGroupCandidate, ...]) -> str:
    payload = [candidate.as_dict() for candidate in candidates]
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _with_group_evidence_digest(
    candidate: ProteinGroupCandidate, supporting: tuple[Psm, ...]
) -> ProteinGroupCandidate:
    payload = {
        "candidate": {
            key: value for key, value in candidate.as_dict().items() if key != "evidence_digest"
        },
        "supporting_psms": [
            _psm_payload(item)
            for item in sorted(
                supporting, key=lambda item: (item.spectrum_id, _psm_payload(item).__repr__())
            )
        ],
    }
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ProteinGroupCandidate(
        accessions=candidate.accessions,
        unique_peptides=candidate.unique_peptides,
        shared_peptides=candidate.shared_peptides,
        score=candidate.score,
        supporting_psms=candidate.supporting_psms,
        status=candidate.status,
        q_value=candidate.q_value,
        acceptance=candidate.acceptance,
        identifiability=candidate.identifiability,
        unique_supported_accessions=candidate.unique_supported_accessions,
        ambiguous_accessions=candidate.ambiguous_accessions,
        evidence_digest=digest,
    )


def _is_hex_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _group_competition_key(
    value: Psm,
) -> tuple[float, bool, bool, str, tuple[str, ...], float, str]:
    """Order group contenders conservatively on exact score ties.

    A collision is unresolved evidence and therefore outranks a pure target;
    a pure decoy outranks a target at equal score. This prevents group FDR
    from converting indistinguishable target/decoy evidence into acceptance.
    When all declared score/class/identity fields are tied, a lower existing
    peptide-level q-value is stricter evidence and wins; a missing q-value is
    treated as least informative. The complete PSM projection remains the
    final replay tie-break.
    """

    return (
        value.score,
        value.target_decoy_collision,
        value.decoy,
        value.peptide,
        value.protein_accessions,
        -(value.q_value if value.q_value is not None else 1.0),
        # Group-level replay has the same duplicate-contender hazard as
        # peptide-level FDR.  Canonicalize the complete projection only after
        # the declared class and identity tie policy above.
        json.dumps(_psm_payload(value), sort_keys=True, separators=(",", ":")),
    )


def _prepare_group_psms(
    psms: tuple[Psm, ...],
    *,
    decoy_prefix: str,
) -> tuple[tuple[Psm, ...], tuple[Psm, ...], str]:
    """Validate contenders, select one winner per spectrum, and digest all inputs."""

    input_psms = tuple(psms)
    winners_by_spectrum: dict[str, Psm] = {}
    contenders_by_spectrum: dict[str, list[Psm]] = {}
    for psm in input_psms:
        _validate_group_psm(psm, decoy_prefix=decoy_prefix)
        contenders_by_spectrum.setdefault(psm.spectrum_id, []).append(psm)
        current = winners_by_spectrum.get(psm.spectrum_id)
        if current is None or _group_competition_key(psm) > _group_competition_key(current):
            winners_by_spectrum[psm.spectrum_id] = psm
    winners = tuple(winners_by_spectrum[spectrum_id] for spectrum_id in sorted(winners_by_spectrum))
    digest_payload = [
        {
            "spectrum_id": spectrum_id,
            "candidates": [
                _psm_payload(item)
                for item in sorted(contenders, key=_group_competition_key, reverse=True)
            ],
        }
        for spectrum_id, contenders in sorted(contenders_by_spectrum.items())
    ]
    digest = sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return input_psms, winners, digest


def _validate_group_psm(psm: Psm, *, decoy_prefix: str) -> None:
    _validate_target_decoy_psm(psm, decoy_prefix=decoy_prefix)


def _validate_decoy_prefix(value: str) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 32
        or any(character.isspace() or ord(character) < 33 for character in value)
    ):
        raise ValueError("decoy_prefix must be a bounded non-whitespace token")


def _psm_payload(value: Psm) -> dict[str, object]:
    return {
        "decoy": value.decoy,
        "matched_intensity": value.matched_intensity,
        "matched_ions": value.matched_ions,
        "mean_fragment_error_da": value.mean_fragment_error_da,
        "peptide": value.peptide,
        "precursor_error_ppm": value.precursor_error_ppm,
        "protein_accessions": list(value.protein_accessions),
        "q_value": value.q_value,
        "score": value.score,
        "spectrum_id": value.spectrum_id,
        "target_decoy_collision": value.target_decoy_collision,
    }
