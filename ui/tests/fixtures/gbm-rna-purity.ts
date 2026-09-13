import { createHash } from "node:crypto";

import modelArtifact from "../../../src/glio_proteogen/research/gbm_rna_purity/data/gbm_purity_mlp.v1.json";

const demoSeed = "synthetic-primary-idhwt-gbm-count-profile/1.0.0";
const profileDigest = "sha256:061fed60e48584fec346b2189f89058dcb89427bdac0eac520548c4a01713ef7";
const requestDigest = "sha256:2880f175bcded0fe30c9c1132acdfbbd0cf969cd1c6a226b8dc5479f503da3a7";
const resultDigest = "sha256:942567db5116bb1c31b5b7afff2822723a83b2a43165addbbc99af2a0d51b3a3";
const convertedArtifactDigest = "sha256:651fa1ea9100650d8b34cec3c980624e42bada1ec3ff9cfe23fdf13049585722";
const convertedArtifactFileDigest = "sha256:2999d845c602c7b8b44d45c37a7f43bea57ad6a930af12f9c7b56cc221ffccc2";
const featureOrderDigest = "sha256:8a2e26d736fb8e1eb2a0ddf5799e2368acb1b6798275d75ef9c60f0c49204112";
const weightTensorDigest = "sha256:2d9ceef433761d9b68419bce4c9c7ed4fb1009b9b195f1b1ea2d81f8913a30f4";

function roundHalfEven(value: number): number {
  const floor = Math.floor(value);
  return value - floor === 0.5 ? (floor % 2 === 0 ? floor : floor + 1) : Math.round(value);
}

function syntheticRawCount(geneSymbol: string, featureLength: number): number {
  const token = createHash("sha256")
    .update(`${demoSeed}:${geneSymbol}`)
    .digest()
    .readUInt32BE(0);
  const abundance = 8 + token % 4_093;
  const lengthModulation = 0.75 + ((token >>> 12) % 101) / 200;
  const lengthScale = Math.max(0.5, Math.min(2, featureLength / 8_000));
  return roundHalfEven(abundance * lengthModulation * lengthScale);
}

export const gbmRnaPurityDemo = {
  schema_version: "glio-proteogen.gbm-rna-purity-request/1.0.0",
  sample_id: "synthetic-primary-idhwt-gbm-rna-purity-v1",
  profile_id: "gbm-rna-tumor-purity/1.0.0",
  context: {
    schema_version: "glio-proteogen.gbm-rna-context-attestation/1.0.0",
    organism: "Homo sapiens",
    disease_context: "primary_IDH_wildtype_glioblastoma",
    specimen: "bulk_tumor_tissue",
    assay: "bulk_RNA_sequencing",
    value_semantics: "raw_nonnegative_gene_counts",
    batch_corrected: false,
    caller_authorizes_missing_gene_zero_fill: true,
    research_use_only: true,
  },
  counts_provenance_digest: "sha256:caf644473c7ce011aeb2c9bc5506babc78ea957294e87996fad3b5d28bdf20ed",
  counts: modelArtifact.input.feature_names.map((geneSymbol, index) => ({
    gene_symbol: geneSymbol,
    raw_count: syntheticRawCount(geneSymbol, modelArtifact.input.feature_lengths[index]),
  })),
};

export const gbmRnaPurityProfile = {
  schema_version: "glio-proteogen.gbm-rna-purity-profile/1.0.0",
  algorithm_id: "gbm-rna-tumor-purity",
  algorithm_version: "1.0.0",
  profile_id: gbmRnaPurityDemo.profile_id,
  model_id: "gbmpurity-primary-idhwt-rna/1.0.0",
  profile_digest: profileDigest,
  constants: {
    preprocessing_scale: 10_000,
    hidden_layer_sizes: [32, 16],
    input_dropout_probability_training_only: 0.4,
    inference_dropout_active: false,
    output_clipping_lower: 0,
    output_clipping_upper: 1,
    inference_dtype: "float32",
    quantization_decimals: 8,
    attribution_method: "exact_active_relu_path_decomposition",
  },
  limits: {
    model_feature_count: 5_829,
    maximum_input_genes: 40_000,
    minimum_model_gene_coverage: 0.8,
    supported_model_gene_coverage: 0.99,
    maximum_request_bytes: 4_194_304,
    maximum_result_bytes: 2_097_152,
    maximum_replay_bytes: 8_388_608,
    top_attribution_limit: 20,
  },
  numpy_version: "2.5.2",
  converted_artifact_digest: convertedArtifactDigest,
  converted_artifact_file_sha256: convertedArtifactFileDigest,
  feature_order_digest: featureOrderDigest,
  weight_tensor_digest: weightTensorDigest,
  computational_source_digest: "sha256:cf8378c387569cf152715fd574549ee590c022deeb7dc992c0d3afd98e13984c",
  demo_request_digest: requestDigest,
  source_repository: "https://github.com/scmpht/GBMPurity",
  source_commit: "af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950",
  source_model_sha256: "sha256:80abd8d8f4875799f839701bec655d2e4753c750e63e60b9119b8b66342025c7",
  source_gene_lengths_sha256: "sha256:de148837ab4d487b3fd86436f63e95b451fa4a305c5bf8d5eb094c117941884b",
  source_license: "MIT",
  source_article_doi: "10.1093/neuonc/noaf026",
  source_article_license: "CC-BY-4.0",
  intended_use: "research_estimation_of_malignant_cell_fraction_in_primary_IDH_wildtype_GBM_bulk_RNA",
  claim_ceiling: "published_model_estimate_only_not_cell_type_composition_or_clinical_truth",
  safety_class: "research_use_only",
};

const provenance = {
  source_repository: "https://github.com/scmpht/GBMPurity",
  source_commit: "af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950",
  source_model_sha256: "sha256:80abd8d8f4875799f839701bec655d2e4753c750e63e60b9119b8b66342025c7",
  source_gene_lengths_sha256: "sha256:de148837ab4d487b3fd86436f63e95b451fa4a305c5bf8d5eb094c117941884b",
  converted_artifact_digest: convertedArtifactDigest,
  converted_artifact_file_sha256: convertedArtifactFileDigest,
  feature_order_digest: featureOrderDigest,
  weight_tensor_digest: weightTensorDigest,
  source_license: "MIT",
  source_license_sha256: "sha256:3f0041f0cfe77a6f4153e1465b1590b744102d9e8948203bcb56d9b244367ef7",
  article_doi: "10.1093/neuonc/noaf026",
  article_license: "CC-BY-4.0",
  transformation_notice: "GLIO-PROTEOGEN converted the six exact pretrained PyTorch float32 storages and the ordered input-gene table into deterministic JSON. The converter does not execute the source pickle, retrain the model, or redistribute source single-cell/pseudobulk training records. This adaptation is not endorsed by the upstream authors.",
};

export const gbmRnaPurityAnalysis = {
  schema_version: "glio-proteogen.gbm-rna-purity-result/1.0.0",
  algorithm_id: "gbm-rna-tumor-purity",
  algorithm_version: "1.0.0",
  profile_id: gbmRnaPurityDemo.profile_id,
  model_id: "gbmpurity-primary-idhwt-rna/1.0.0",
  sample_id: gbmRnaPurityDemo.sample_id,
  request_digest: requestDigest,
  profile_digest: profileDigest,
  result_digest: resultDigest,
  support: "supported",
  coverage: {
    model_feature_count: 5_829,
    supplied_gene_count: 5_829,
    recognized_model_gene_count: 5_829,
    missing_model_gene_count: 0,
    ignored_non_model_gene_count: 0,
    nonzero_model_gene_count: 5_829,
    coverage_fraction: 1,
    recognized_raw_count_sum: 9_916_184,
    missing_gene_policy: "source_parity_zero_fill_after_80_percent_gate",
  },
  estimate: {
    malignant_cell_fraction: 0.1324209,
    raw_unclipped_output: 0.1324209,
    clipping_state: "none",
    model_output_semantics: "published_GBMPurity_estimated_malignant_cell_fraction",
  },
  diagnostics: {
    preprocessing: "source_order_zero_fill_then_RPK_share_times_1e4_then_log2_plus_1",
    network: "5829_to_32_relu_to_16_relu_to_1_linear_eval_mode",
    dropout_active: false,
    inference_dtype: "float32",
    finite_inference: true,
    transformed_input_sum: 7_578.01257993,
    transformed_input_maximum: 4.3257575,
    hidden_trace: {
      first_layer_active_nodes: 10,
      second_layer_active_nodes: 5,
      first_layer_activations: [4.02016401, 0, 11.32674026, ...Array<number>(29).fill(0)],
      second_layer_activations: [2.99080491, 9.84163857, 0, ...Array<number>(13).fill(0)],
      activation_pattern_digest: "sha256:0ebedcf5a9600780d2cec53a199b03dd2188119dbb2afd1c763c3b4a6a5a234e",
    },
  },
  explanation: {
    method: "exact_active_relu_path_decomposition",
    top_gene_attributions: [
      { rank: 1, gene_symbol: "NOSTRIN", transformed_expression: 1.69146812, local_gradient: -0.0056269, raw_output_contribution: -0.00951772, direction: "lowers_raw_estimate" },
      { rank: 2, gene_symbol: "GPR157", transformed_expression: 1.63651955, local_gradient: 0.00579154, raw_output_contribution: 0.00947797, direction: "raises_raw_estimate" },
      { rank: 3, gene_symbol: "CCDC120", transformed_expression: 1.94096982, local_gradient: 0.00434497, raw_output_contribution: 0.00843346, direction: "raises_raw_estimate" },
    ],
    all_gene_contribution_sum: 0.26437496,
    active_path_bias_contribution: -0.13195424,
    reconstructed_raw_output: 0.13242073,
    reconstruction_absolute_error: 0.00000017,
    clipping_changes_local_interpretation: false,
    interpretation: "local_piecewise_linear_attribution_not_causal_gene_importance",
  },
  uncertainty_status: "not_available_in_published_single_model",
  uncertainty_reason: "The published release contains one fitted MLP and no calibrated ensemble; GLIO-PROTEOGEN does not fabricate an interval.",
  provenance,
  abstention_reasons: [],
  limitations: [
    "Research-use-only estimate from a published single pretrained model; not clinical truth.",
    "The intended population is primary IDH-wildtype glioblastoma bulk RNA-seq; other tumors, modalities, and preprocessing are out of scope.",
    "The output is one estimated malignant-cell fraction, not immune/stromal composition, spatial context, cell state, diagnosis, prognosis, or treatment response.",
    "The published artifact is one MLP, so this lane does not invent a bootstrap interval or calibrated predictive uncertainty.",
  ],
  safety_class: "research_use_only_non_prescriptive",
};

export const gbmRnaPurityVerification = {
  schema_version: "glio-proteogen.gbm-rna-purity-replay-result/1.0.0",
  verified: true,
  request_digest_match: true,
  profile_digest_match: true,
  result_digest_match: true,
  semantic_match: true,
  recomputed_request_digest: requestDigest,
  provided_result_digest: resultDigest,
  recomputed_result_digest: resultDigest,
  message: "Replay exactly matches the deterministic GBMPurity NumPy receipt.",
};
