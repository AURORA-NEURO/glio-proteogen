"""Entirely fictitious aggregate summaries for exercising the workbench."""

from __future__ import annotations

from hashlib import sha256

from .contracts import CohortEffect, CohortReceipt, FeatureRequest, ReplicationRequest


def synthetic_demo_request() -> ReplicationRequest:
    cohorts = tuple(
        CohortReceipt(
            cohort_id=f"synthetic-{index}",
            label=f"Fictitious cohort {index}",
            source_sha256="sha256:"
            + sha256(f"fictitious-no-real-data-{index}".encode()).hexdigest(),
            independence_group=f"fictitious-disjoint-{index}",
            sample_size=40 + index * 10,
        )
        for index in range(1, 6)
    )
    rows = (
        ("hypoxia", "Hypoxia program (synthetic)", (0.8, 0.7, 0.9, 0.65, 0.75)),
        ("mesenchymal", "Mesenchymal program (synthetic)", (0.6, -0.5, 0.7, -0.4, 0.8)),
        ("cell-cycle", "Cell-cycle program (synthetic)", (0.02, -0.03, 0.0, 0.01, -0.01)),
        ("rtk", "RTK program (synthetic)", (0.6, 0.5, None, 0.4, None)),
        ("neuronal", "Neuronal program (synthetic)", (-0.7, -0.65, -0.8, -0.6, -0.75)),
        ("myeloid", "Myeloid program (synthetic)", (0.4, None, None, None, None)),
        ("angiogenesis", "Angiogenesis program (synthetic)", (None, None, None, None, None)),
        ("dna-repair", "DNA-repair program (synthetic)", (0.4, 0.45, 0.5, 0.42, 2.8)),
        ("metabolism", "Metabolism program (synthetic)", (0.2, 0.18, None, None, None)),
        ("proteostasis", "Proteostasis program (synthetic)", (-0.1, -0.2, -0.15, -0.08, -0.17)),
    )
    features = tuple(
        FeatureRequest(
            feature_id=identifier,
            label=label,
            effects=tuple(
                CohortEffect(
                    cohort_id=cohort.cohort_id,
                    state="observed"
                    if value is not None
                    else ("missing" if index % 2 else "unsupported"),
                    estimate=value,
                    standard_error=(0.12 + index * 0.015) if value is not None else None,
                )
                for index, (cohort, value) in enumerate(zip(cohorts, values, strict=True))
            ),
        )
        for identifier, label, values in rows
    )
    return ReplicationRequest(
        analysis_id="synthetic-replication-demo",
        disease_context="glioblastoma_idh_wildtype",
        estimand_id="synthetic-program-contrast",
        effect_scale="standardized_mean_difference",
        contrast="Entirely fictitious group A minus group B; no real source or patient data",
        cohorts=cohorts,
        features=features,
    )
