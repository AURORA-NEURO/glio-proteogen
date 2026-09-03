import {
  GBM_FACTOR_GRAPH_DEMO_ID,
  GBM_FACTOR_GRAPH_KINASE_PROFILE_ID,
  GBM_FACTOR_GRAPH_MODEL_ID,
  GBM_FACTOR_GRAPH_PROFILE_ID,
  GBM_FACTOR_GRAPH_RELATIONSHIP,
  GBM_FACTOR_GRAPH_TOPOLOGY_DIGEST,
  GBM_FACTOR_GRAPH_TOPOLOGY_ID,
  factorGraphChildResultDigest,
  factorGraphProfileDigest,
  factorGraphRequestDigest,
  factorGraphResultDigest,
} from "../../src/lib/gbm-factor-graph";
import { phosphoDemoRequest } from "./longitudinal-gbm-phospho";
import {
  reactomeTransitionAnalysisResult,
  reactomeTransitionDemoRequest,
} from "./longitudinal-gbm-reactome-transition";

const digest = (character: string) => `sha256:${character.repeat(64)}`;
const topologyDigest = GBM_FACTOR_GRAPH_TOPOLOGY_DIGEST;
const kinaseProfileDigest = digest("5");
const kinaseRequestDigest = digest("6");
const sourceInventoryDigest = digest("8");

const pathwayCatalog = [
  ["receptor_egfr", "R-HSA-177929", "Signaling by EGFR"],
  ["receptor_pdgf", "R-HSA-186797", "Signaling by PDGF"],
  ["second_messenger_pi3k_akt", "R-HSA-198203", "PI3K/AKT activation"],
  ["mtor_signaling", "R-HSA-165159", "MTOR signalling"],
  ["mapk_cascades", "R-HSA-5683057", "MAPK family signaling cascades"],
  ["cell_cycle", "R-HSA-1640170", "Cell Cycle"],
  ["dna_repair", "R-HSA-73894", "DNA Repair"],
  ["hypoxia_response", "R-HSA-1234174", "Cellular response to hypoxia"],
  ["extracellular_matrix", "R-HSA-1474244", "Extracellular matrix organization"],
  ["innate_immune_system", "R-HSA-168249", "Innate Immune System"],
] as const;

const kinaseCatalog = [
  ["BRAF", "NEU"],
  ["CDK1", "PPR"],
  ["CDK2", "PPR"],
  ["CDK6", "PPR"],
  ["CHEK2", "PPR"],
  ["CSNK2A1", "PPR"],
  ["GSK3B", "NEU"],
  ["IKBKB", "GPM"],
  ["MAPK10", "NEU"],
  ["MAPK13", "GPM"],
  ["MAPKAPK2", "GPM"],
  ["MKNK1", "GPM"],
  ["PAK1", "NEU"],
  ["PAK3", "NEU"],
  ["PHKG2", "MTC"],
  ["PRKAA1", "GPM"],
  ["PRKCD", "GPM"],
  ["PRKCE", "NEU"],
  ["PRKDC", "PPR"],
  ["RAF1", "PPR"],
  ["RPS6KB2", "GPM"],
  ["SYK", "GPM"],
  ["TTBK2", "NEU"],
  ["VRK2", "GPM"],
] as const;

const selectedKinases = new Set([
  "BRAF", "CDK1", "CDK2", "CHEK2", "CSNK2A1", "GSK3B",
  "MAPK10", "PAK1", "PAK3", "PRKCE", "PRKDC", "TTBK2",
]);

const reactomeProfileId = reactomeTransitionDemoRequest.profile_id;
const kinaseRequest = {
  ...phosphoDemoRequest,
  profile_id: GBM_FACTOR_GRAPH_KINASE_PROFILE_ID,
  series_id: "synthetic-kncc-sphinks-signature-transition-v1",
};

export const factorGraphDemoRequest = {
  profile_id: GBM_FACTOR_GRAPH_PROFILE_ID,
  analysis_id: "kncc-gbm-factor-graph-synthetic-model-derived-v1",
  relationship: GBM_FACTOR_GRAPH_RELATIONSHIP,
  reactome_request: reactomeTransitionDemoRequest,
  kinase_request: kinaseRequest,
};
const requestDigest = factorGraphRequestDigest(factorGraphDemoRequest);

const blockNodes = [
  {
    node_id: "block.protein_reactome",
    block: "protein_reactome",
    kind: "computation_block",
    biological_identifier: "PDC000514.ReactomeV97",
    label: "KNCC protein / fitted Reactome concordance block",
    child_profile_id: reactomeProfileId,
    learned_semantics: "child_result_container_only",
  },
  {
    node_id: "block.phosphosite_sphinks",
    block: "phosphosite_sphinks",
    kind: "computation_block",
    biological_identifier: "PDC000515.SPHINKS",
    label: "KNCC phosphosite / fitted SPHINKS concordance block",
    child_profile_id: GBM_FACTOR_GRAPH_KINASE_PROFILE_ID,
    learned_semantics: "child_result_container_only",
  },
];

const reactomeNodes = [
  {
    node_id: "reactome.global_recurrence",
    block: "protein_reactome",
    kind: "global_recurrence_factor",
    biological_identifier: "global_recurrence",
    label: "Fitted global recurrence concordance coordinate",
    child_profile_id: reactomeProfileId,
    learned_semantics: "child_source_cohort_fitted_coordinate",
  },
  ...pathwayCatalog.map(([domain, reactomeId, name], index) => ({
    node_id: `reactome.pathway.${String(index).padStart(2, "0")}`,
    block: "protein_reactome",
    kind: "reactome_pathway_factor",
    biological_identifier: reactomeId,
    label: `${domain}: ${name}`,
    child_profile_id: reactomeProfileId,
    learned_semantics: "child_source_cohort_fitted_coordinate",
  })),
];

const kinaseNodes = [
  ...kinaseCatalog.map(([kinase, subtype]) => ({
    node_id: `sphinks.kinase.${kinase}`,
    block: "phosphosite_sphinks",
    kind: "kinase_signature_factor",
    biological_identifier: kinase,
    label: `${kinase} fitted ${subtype} signature coordinate`,
    child_profile_id: GBM_FACTOR_GRAPH_KINASE_PROFILE_ID,
    learned_semantics: "child_source_cohort_fitted_coordinate",
  })),
  ...(["GPM", "MTC", "NEU", "PPR"] as const).map((subtype) => ({
    node_id: `sphinks.subtype.${subtype}`,
    block: "phosphosite_sphinks",
    kind: "subtype_signature_factor",
    biological_identifier: subtype,
    label: `${subtype} fitted equal-kinase subtype signature coordinate`,
    child_profile_id: GBM_FACTOR_GRAPH_KINASE_PROFILE_ID,
    learned_semantics: "child_source_cohort_fitted_coordinate",
  })),
];

const topologyNodes = [...blockNodes, ...reactomeNodes, ...kinaseNodes];
const containmentEdges = topologyNodes.flatMap((node, index) => node.kind === "computation_block" ? [] : [{
  edge_id: `containment.edge.${String(index).padStart(2, "0")}`,
  source_node_id: node.block === "protein_reactome" ? "block.protein_reactome" : "block.phosphosite_sphinks",
  target_node_id: node.node_id,
  relationship: "contains",
  computational_role: "annotation_only",
  numerical_weight: null,
}]);

export const factorGraphProfile = {
  algorithm_id: "glio-ecgi-kncc-gbm-transition",
  algorithm_version: "1.0.0",
  profile_id: GBM_FACTOR_GRAPH_PROFILE_ID,
  model_id: GBM_FACTOR_GRAPH_MODEL_ID,
  relationship: GBM_FACTOR_GRAPH_RELATIONSHIP,
  topology: {
    topology_id: GBM_FACTOR_GRAPH_TOPOLOGY_ID,
    nodes: topologyNodes,
    containment_edges: containmentEdges,
    cross_block_edges: [],
    numerical_cross_block_edge_count: 0,
    containment_edge_role: "annotation_only",
    topology_digest: topologyDigest,
  },
  topology_digest: topologyDigest,
  reactome_child: {
    block: "protein_reactome",
    child_profile_id: reactomeProfileId,
    child_profile_digest: reactomeTransitionAnalysisResult.profile_digest,
    source_digest: digest("a"),
    fitted_digest: digest("b"),
    bootstrap_digest: digest("c"),
    evaluation_digest: digest("d"),
  },
  kinase_child: {
    block: "phosphosite_sphinks",
    child_profile_id: GBM_FACTOR_GRAPH_KINASE_PROFILE_ID,
    child_profile_digest: kinaseProfileDigest,
    source_digest: digest("e"),
    fitted_digest: digest("f"),
    bootstrap_digest: digest("0"),
    evaluation_digest: digest("1"),
  },
  source_inventory_digest: sourceInventoryDigest,
  numpy_version: "2.5.2",
  composition_semantic_digest: digest("2"),
  counts: {
    computation_blocks: 2,
    reactome_global_factors: 1,
    reactome_pathway_factors: 10,
    kinase_signature_factors: 24,
    subtype_signature_factors: 4,
    nodes: 41,
    annotation_only_containment_edges: 39,
    numerical_cross_block_edges: 0,
  },
  limits: {
    minimum_time_points_per_child: 2,
    maximum_time_points_per_child: 5,
    maximum_request_bytes: 4 * 1024 * 1024,
    maximum_result_bytes: 8 * 1024 * 1024,
    maximum_replay_bytes: 16 * 1024 * 1024,
    maximum_numerical_cross_block_edges: 0,
  },
  demo_id: GBM_FACTOR_GRAPH_DEMO_ID,
  demo_request_digest: requestDigest,
  demo_semantic_oracle_digest: digest("9"),
  source_attestation_state: "verified_exact_child_snapshots",
  safety_class: "research_use_only",
  claim_ceiling: "independent_source_cohort_concordance_coordinates_only",
  research_use_only: true,
  non_prescriptive: true,
  independent_parallel_blocks: true,
  cross_modal_fusion_performed: false,
  no_numerical_cross_block_edges: true,
  profile_digest: "",
};
factorGraphProfile.profile_digest = factorGraphProfileDigest(factorGraphProfile);
const profileDigest = factorGraphProfile.profile_digest;

function estimatedUncertainty(score: number) {
  return {
    state: "estimated",
    lower_bound: score - 0.12,
    upper_bound: score + 0.12,
    standard_error: 0.07,
    bootstrap_replicates_used: 64,
    reason: null,
  };
}

const notEstimableUncertainty = {
  state: "not_estimable",
  lower_bound: null,
  upper_bound: null,
  standard_error: null,
  bootstrap_replicates_used: 0,
  reason: "not selected by the source-fitted hypothesis family",
};

function kinaseSignature(kinase: string, subtype: string, transitionIndex: number) {
  const selected = selectedKinases.has(kinase);
  const direction = subtype === "PPR" ? -1 : 1;
  const score = selected ? Number((direction * (0.31 + transitionIndex * 0.08)).toFixed(3)) : null;
  return {
    kinase,
    subtype,
    selection_state: selected ? "selected_core" : "not_selected",
    support: selected ? "limited" : "abstained",
    source_direction: selected ? (direction > 0 ? "source_recurrence_aligned" : "reverse_aligned") : "not_established",
    source_enrichment: selected ? direction * 0.72 : null,
    source_p_value: selected ? 0.002 : 1,
    source_q_value: selected ? 0.008 : 1,
    mapped_source_family_count: selected ? 22 : 4,
    observed_family_count: selected ? 18 : 2,
    source_weight_coverage: selected ? 0.86 : 0.12,
    outer_selection_frequency: selected ? 1 : 0,
    bootstrap_selection_frequency: selected ? 0.94 : 0,
    bootstrap_direction_consistency: selected ? 1 : null,
    score,
    classification: selected ? (direction > 0 ? "source_recurrence_aligned" : "reverse_aligned") : "not_estimable",
    uncertainty: selected && score !== null ? estimatedUncertainty(score) : notEstimableUncertainty,
    top_family_drivers: selected ? [{
      source_site_label: `${kinase}-S473s`,
      source_phosphosite_ids: ["ENSP00000354587.4:s473"],
      stratum: "S:1",
      contains_composite_source_group: false,
      standardized_rank: direction * 0.82,
      inverse_multiplicity: 1,
      adjusted_source_weight: 0.41,
      signed_contribution: direction * 0.16,
      paired_source_support: 83,
      paired_observation_ids: ["demo-p0-f0", "demo-p1-f0"],
      observation_provenance_digests: [digest("a"), digest("b")],
    }] : [],
    reasons: [selected
      ? "same-source patient bootstrap stability and interval calibration do not establish full support"
      : "not selected by the source-fitted hypothesis family"],
  };
}

function subtypeSignature(subtype: "GPM" | "MTC" | "NEU" | "PPR", transitionIndex: number) {
  const selected = subtype === "NEU" ? 7 : subtype === "PPR" ? 5 : 0;
  const score = selected ? (subtype === "PPR" ? -0.43 : 0.55) + transitionIndex * 0.03 : null;
  return {
    subtype,
    selected_kinase_count: selected,
    estimable_kinase_count: selected,
    support: selected ? "limited" : "abstained",
    score,
    classification: selected ? (score! > 0 ? "source_recurrence_aligned" : "reverse_aligned") : "not_estimable",
    uncertainty: score === null ? notEstimableUncertainty : estimatedUncertainty(score),
    reasons: [selected ? "same-source quality gates cap support" : "no source-selected kinase was estimable"],
  };
}

function kinaseTransition(index: number) {
  const score = Number((0.28 + index * 0.07).toFixed(3));
  return {
    transition_id: `kinase-transition-${index}`,
    transition_index: index,
    from_time_point_id: kinaseRequest.time_points[index].time_point_id,
    to_time_point_id: kinaseRequest.time_points[index + 1].time_point_id,
    support: "limited",
    classification: "source_recurrence_aligned",
    score,
    uncertainty: estimatedUncertainty(score),
    exact_source_row_count: 572,
    exact_family_count: 560,
    censored_family_count: index === 2 ? 1 : 0,
    selected_kinase_count: 12,
    estimable_kinase_count: 12,
    kinase_signatures: kinaseCatalog.map(([kinase, subtype]) => kinaseSignature(kinase, subtype, index)),
    subtype_signatures: (["GPM", "MTC", "NEU", "PPR"] as const).map((subtype) => subtypeSignature(subtype, index)),
    ablations: [
      "equal_kinase_instead_of_equal_subtype",
      "omit_composite_source_groups",
      "omit_inverse_multiplicity_correction",
    ].map((ablation, ablationIndex) => ({
      ablation,
      support: "limited",
      score: score - (ablationIndex + 1) * 0.03,
      score_delta: (ablationIndex + 1) * 0.03,
      classification: "source_recurrence_aligned",
      reason: "point sensitivity only; source quality gates cap support",
    })),
    reasons: ["all estimable outputs remain limited by same-source stability and calibration gates"],
  };
}

const kinaseResult = {
  algorithm_id: "kncc-gbm-longitudinal-kinase-transition",
  algorithm_version: "1.0.0",
  profile_id: GBM_FACTOR_GRAPH_KINASE_PROFILE_ID,
  profile_digest: kinaseProfileDigest,
  request_digest: kinaseRequestDigest,
  result_digest: "",
  series_id: kinaseRequest.series_id,
  assay_compatibility: kinaseRequest.assay_compatibility,
  normalization_reference: kinaseRequest.normalization_reference,
  time_point_ids: kinaseRequest.time_points.map((point) => point.time_point_id),
  transitions: kinaseRequest.time_points.slice(1).map((_, index) => kinaseTransition(index)),
  provenance: {
    engine: GBM_FACTOR_GRAPH_KINASE_PROFILE_ID,
    request_digest: kinaseRequestDigest,
    profile_digest: kinaseProfileDigest,
    fitted_artifact_content_digest: digest("9"),
    bootstrap_ensemble_digest: digest("a"),
    computational_digest: digest("b"),
    source_attestation_state: "verified_exact_snapshots",
    numpy_version: "2.5.2",
  },
  output_semantics: "SPHINKS_signature_transition_concordance_only",
  limitations: ["Same-source concordance only."],
  research_use_only: true,
  non_prescriptive: true,
  infers_kinase_activity: false,
  infers_biochemical_activity: false,
  makes_causal_claim: false,
  independent_evidence: false,
};
kinaseResult.result_digest = factorGraphChildResultDigest(kinaseResult);

const reactomeResult = structuredClone(reactomeTransitionAnalysisResult);
reactomeResult.limitations = [
  ...reactomeResult.limitations,
  "The child result is not an externally validated recurrence classifier.",
  "Caller-supplied evidence remains bound to the declared assay and normalization reference.",
  "Conditional coordinates must not be interpreted as treatment-response evidence.",
];
reactomeResult.result_digest = factorGraphChildResultDigest(reactomeResult);

export const factorGraphAnalysisResult = {
  algorithm_id: "glio-ecgi-kncc-gbm-transition",
  algorithm_version: "1.0.0",
  profile_id: GBM_FACTOR_GRAPH_PROFILE_ID,
  profile_digest: profileDigest,
  topology_digest: topologyDigest,
  request_digest: requestDigest,
  result_digest: "",
  analysis_id: factorGraphDemoRequest.analysis_id,
  relationship: GBM_FACTOR_GRAPH_RELATIONSHIP,
  provenance: {
    engine: GBM_FACTOR_GRAPH_PROFILE_ID,
    request_digest: requestDigest,
    profile_digest: profileDigest,
    topology_digest: topologyDigest,
    source_inventory_digest: sourceInventoryDigest,
    relationship: GBM_FACTOR_GRAPH_RELATIONSHIP,
    reactome_child: {
      block: "protein_reactome",
      child_profile_id: reactomeProfileId,
      child_profile_digest: reactomeResult.profile_digest,
      child_request_digest: reactomeResult.request_digest,
      child_result_digest: reactomeResult.result_digest,
      independently_computed: true,
    },
    kinase_child: {
      block: "phosphosite_sphinks",
      child_profile_id: GBM_FACTOR_GRAPH_KINASE_PROFILE_ID,
      child_profile_digest: kinaseProfileDigest,
      child_request_digest: kinaseRequestDigest,
      child_result_digest: kinaseResult.result_digest,
      independently_computed: true,
    },
    numpy_version: "2.5.2",
    independent_parallel_blocks: true,
    cross_modal_fusion_performed: false,
    no_numerical_cross_block_edges: true,
  },
  limitations: [
    "This outer surface is a composition, not an additional fitted inference model.",
    "The Reactome child is limited to PDC000514 source-cohort protein concordance.",
    "The SPHINKS child is limited to PDC000515 source-cohort phosphosite signature concordance.",
    "The child computations are semantically independent and execute deterministically in sequence.",
    "Annotation-only containment edges carry no numerical weight and imply no cross-modal coupling.",
    "No output is diagnostic, prognostic, prescriptive, or clinically validated.",
  ],
  research_use_only: true,
  non_prescriptive: true,
  independent_parallel_blocks: true,
  cross_modal_fusion_performed: false,
  numerical_cross_block_edge_count: 0,
  reactome_result: reactomeResult,
  kinase_result: kinaseResult,
};
factorGraphAnalysisResult.result_digest = factorGraphResultDigest(factorGraphAnalysisResult);
const resultDigest = factorGraphAnalysisResult.result_digest;

export const factorGraphVerification = {
  verified: true,
  request_digest_match: true,
  profile_digest_match: true,
  topology_digest_match: true,
  source_inventory_digest_match: true,
  result_digest_match: true,
  reactome_child_verified: true,
  kinase_child_verified: true,
  independent_parallel_blocks_match: true,
  no_cross_modal_fusion_match: true,
  no_numerical_cross_block_edges_match: true,
  provenance_match: true,
  document_semantic_match: true,
  semantic_match: true,
  recomputed_request_digest: requestDigest,
  recomputed_result_digest: resultDigest,
  message: "factor-graph replay verified",
};
