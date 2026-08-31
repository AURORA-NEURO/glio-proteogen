"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  arrayAt,
  formatNumber,
  formatSigned,
  isJsonObject,
  normalizeAblations,
  normalizeStates,
  numberAt,
  objectAt,
  parseJsonObject,
  requestStats,
  shortDigest,
  textAt,
  validateResearchRequest,
  type JsonObject,
  type JsonValue,
  type NormalizedState,
  type StateKind,
} from "@/lib/research-state";
import {
  validateEcgiDemo,
  validateEcgiProfile,
  validateEcgiProfileHeaders,
  validateEcgiResult,
  validateEcgiResultHeaders,
  validateEcgiResultProfileBinding,
  validateEcgiResultRequestBinding,
  validateEcgiVerification,
  validateEcgiVerificationHeaders,
} from "@/lib/evidence-graph-admission";
import {
  buildEvidenceGraph,
  describeGraphEdge,
  GRAPH_KIND_ORDER,
  GRAPH_NODE_HEIGHT,
  GRAPH_NODE_WIDTH,
} from "@/lib/evidence-graph";
import {
  isAbortError,
  readBoundedJsonObject,
  readBoundedResponseText,
} from "@/lib/http";
import {
  GBM_PROFILE_ID,
  gbmRequestStats,
  normalizeGbmSignatures,
  validateGbmRequest,
  type GbmSignature,
} from "@/lib/gbm-proteomic-axes";
import {
  NEFTEL_PROFILE_ID,
  neftelRequestStats,
  normalizeNeftelPrograms,
  validateNeftelRequest,
  type NeftelProgram,
} from "@/lib/neftel-programs";
import {
  MASTER_KINASE_PROFILE_ID,
  MASTER_KINASE_SUBTYPES,
  masterKinaseRequestStats,
  normalizeMasterKinases,
  normalizeMasterKinaseSubtypes,
  validateMasterKinaseRequest,
  type MasterKinaseEvidence,
  type MasterKinaseSubtypeEvidence,
} from "@/lib/gbm-master-kinases";
import {
  FUNCTIONAL_PROTEOTYPE_PROFILE_ID,
  functionalProteotypeRequestStats,
  normalizeFunctionalProteotypeAxes,
  validateFunctionalProteotypeRequest,
} from "@/lib/gbm-functional-proteotype";
import {
  FunctionalProteotypeAxisTable,
  FunctionalProteotypeExplanationPanels,
  FunctionalProteotypePathwayContextPanel,
} from "@/components/gbm-functional-proteotype-panels";
import {
  GBM_RNA_PURITY_PROFILE_ID,
  gbmRnaPurityRequestStats,
  normalizeGbmRnaPurityResult,
  validateGbmRnaPurityRequest,
} from "@/lib/gbm-rna-purity";
import {
  GbmRnaPurityEvidencePanel,
  GbmRnaPurityResultPanels,
} from "@/components/gbm-rna-purity-panels";
import {
  LONGITUDINAL_GBM_PROFILE_ID,
  longitudinalRequestStats,
  normalizeLongitudinalTransitions,
  normalizePeltAnalysis,
  validateLongitudinalRequest,
} from "@/lib/longitudinal-gbm";
import {
  LongitudinalEvidencePanel,
  LongitudinalExplanationPanels,
  LongitudinalTimeline,
  LongitudinalTransitionTable,
  LongitudinalUncertaintyInteractionPanel,
  PeltPanel,
} from "@/components/longitudinal-gbm-panels";
import {
  LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID,
  longitudinalPhosphoRequestStats,
  normalizeLongitudinalPhosphoTransitions,
  validateLongitudinalPhosphoRequest,
} from "@/lib/longitudinal-gbm-phospho";
import {
  PhosphoEvidencePanel,
  PhosphoExplanationPanels,
  PhosphoTimeline,
  PhosphoTransitionTable,
  PhosphoUncertaintyPanel,
} from "@/components/longitudinal-gbm-phospho-panels";
import {
  LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
  normalizeReactomeEvaluation,
  normalizeReactomeTransitions,
  reactomeEstimatedPathwayCount,
  reactomePathwayCount,
  reactomeSupportedPathwayCount,
  reactomeTransitionRequestStats,
  validateReactomeTransitionDemo,
  validateReactomeTransitionProfile,
  validateReactomeTransitionProfileHeaders,
  validateReactomeTransitionRequest,
  validateReactomeTransitionResult,
  validateReactomeTransitionResultHeaders,
  validateReactomeTransitionResultProfileBinding,
  validateReactomeTransitionResultRequestBinding,
  validateReactomeTransitionVerification,
  validateReactomeTransitionVerificationHeaders,
} from "@/lib/longitudinal-gbm-reactome-transition";
import {
  ReactomeLockedEvaluationPanel,
  ReactomeTransitionEvidencePanel,
  ReactomeTransitionResultPanels,
} from "@/components/longitudinal-gbm-reactome-transition-panels";
import {
  LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID,
  kinaseTransitionEstimatedCount,
  kinaseTransitionRequestStats,
  kinaseTransitionSignatureCount,
  normalizeKinaseTransitions,
  validateKinaseTransitionDemo,
  validateKinaseTransitionProfile,
  validateKinaseTransitionProfileHeaders,
  validateKinaseTransitionRequest,
  validateKinaseTransitionResult,
  validateKinaseTransitionResultHeaders,
  validateKinaseTransitionResultProfileBinding,
  validateKinaseTransitionResultRequestBinding,
  validateKinaseTransitionVerification,
  validateKinaseTransitionVerificationHeaders,
} from "@/lib/longitudinal-gbm-kinase-transition";
import {
  KinaseTransitionEvidencePanel,
  KinaseTransitionResultPanels,
} from "@/components/longitudinal-gbm-kinase-transition-panels";
import {
  LONGITUDINAL_GBM_NEFTEL_TRANSITION_PROFILE_ID,
  neftelEstimatedProgramCount as neftelTransitionEstimatedProgramCount,
  neftelProgramCount as neftelTransitionProgramCount,
  neftelSupportedProgramCount as neftelTransitionSupportedProgramCount,
  neftelTransitionRequestDigest,
  neftelTransitionRequestStats,
  normalizeNeftelEvaluation as normalizeNeftelTransitionEvaluation,
  normalizeNeftelTransitions,
  validateNeftelTransitionProfile,
  validateNeftelTransitionProfileHeaders,
  validateNeftelTransitionRequest,
  validateNeftelTransitionResult,
  validateNeftelTransitionResultHeaders,
  validateNeftelTransitionResultProfileBinding,
  validateNeftelTransitionResultRequestBinding,
  validateNeftelTransitionVerification,
  validateNeftelTransitionVerificationHeaders,
} from "@/lib/longitudinal-gbm-neftel-transition";
import {
  NeftelLockedEvaluationPanel,
  NeftelTransitionEvidencePanel,
  NeftelTransitionResultPanels,
} from "@/components/longitudinal-gbm-neftel-transition-panels";
import {
  LONGITUDINAL_GBM_COMPLEX_TRANSITION_PROFILE_ID,
  complexEstimatedCount,
  complexResultCount,
  complexSupportedCount,
  complexTransitionRequestStats,
  normalizeComplexEvaluation,
  normalizeComplexTransitions,
  validateComplexTransitionProfile,
  validateComplexTransitionProfileHeaders,
  validateComplexTransitionRequest,
  validateComplexTransitionResult,
  validateComplexTransitionResultHeaders,
  validateComplexTransitionResultProfileBinding,
  validateComplexTransitionResultRequestBinding,
  validateComplexTransitionVerification,
  validateComplexTransitionVerificationHeaders,
} from "@/lib/longitudinal-gbm-complex-transition";
import {
  ComplexLockedEvaluationPanel,
  ComplexTransitionEvidencePanel,
  ComplexTransitionResultPanels,
} from "@/components/longitudinal-gbm-complex-transition-panels";
import {
  GBM_FACTOR_GRAPH_PROFILE_ID,
  factorGraphRequestStats,
  normalizeFactorGraphResult,
  normalizeFactorGraphTopology,
  validateFactorGraphDemo,
  validateFactorGraphProfile,
  validateFactorGraphProfileHeaders,
  validateFactorGraphRequest,
  validateFactorGraphResult,
  validateFactorGraphResultHeaders,
  validateFactorGraphResultProfileBinding,
  validateFactorGraphResultRequestBinding,
  validateFactorGraphVerification,
  validateFactorGraphVerificationHeaders,
} from "@/lib/gbm-factor-graph";
import {
  FactorGraphBoundary,
  FactorGraphEvidencePanels,
  FactorGraphResultPanels,
  FactorGraphTopologyPanel,
} from "@/components/gbm-factor-graph-panels";

const MIB = 1024 * 1024;
const HEALTH_RESPONSE_LIMIT_BYTES = 16 * 1024;
const ANALYSIS_TIMEOUT_MS = 30_000;
const VERIFICATION_TIMEOUT_MS = 30_000;
const LONGITUDINAL_TIMEOUT_MS = 130_000;
const PROBE_TIMEOUT_MS = 5_000;

type ProbeState = "checking" | "online" | "degraded" | "offline";
type Probe = { state: ProbeState; detail: string; latency: number | null };
type View = "results" | "network" | "evidence" | "audit";
type WorkbenchMode = "evidence-graph" | "gbm-proteomic-axes" | "neftel-programs" | "gbm-master-kinases" | "gbm-functional-proteotype" | "gbm-rna-purity" | "longitudinal-gbm" | "longitudinal-gbm-phospho" | "longitudinal-gbm-kinase-transition" | "longitudinal-gbm-reactome-transition" | "longitudinal-gbm-neftel-transition" | "longitudinal-gbm-complex-transition" | "gbm-factor-graph";
type ComplexBottleneck = { complex: NormalizedState; member: NormalizedState | null; essential: boolean; memberCount: number; gap: number | null };

type LaneConfig = {
  apiBase: string;
  requestLimitBytes: number;
  resultLimitBytes: number;
  replayLimitBytes: number;
  requestLabel: string;
  defaultProfileId: string;
};

type LaneCopy = {
  demoLoaded: string;
  running: string;
  complete: string;
  replayVerified: string;
  reset: string;
  heroEyebrow: string;
  heroLead: string;
  heroBoundary: string;
  heroIntro: string;
  inputTitle: string;
  emptyMark: string;
  emptyTitle: string;
  emptyBody: string;
  emptyTags: string[];
  receiptLabel: "Sample" | "Series" | "Analysis";
  receiptKey: "sample_id" | "series_id" | "analysis_id";
};

const LANES: Record<WorkbenchMode, LaneConfig> = {
  "evidence-graph": {
    apiBase: "/backend/v1/research/proteogenomic-state",
    requestLimitBytes: 2 * MIB,
    resultLimitBytes: 4 * MIB,
    replayLimitBytes: 7 * MIB,
    requestLabel: "Proteogenomic state request JSON",
    defaultProfileId: "glio-ecgi/1.0.0",
  },
  "gbm-proteomic-axes": {
    apiBase: "/backend/v1/research/gbm-proteomic-axes",
    requestLimitBytes: 2 * MIB,
    resultLimitBytes: 1 * MIB,
    replayLimitBytes: 4 * MIB,
    requestLabel: "GBM proteomic axes request JSON",
    defaultProfileId: GBM_PROFILE_ID,
  },
  "neftel-programs": {
    apiBase: "/backend/v1/research/neftel-protein-programs",
    requestLimitBytes: 2 * MIB,
    resultLimitBytes: 1 * MIB,
    replayLimitBytes: 4 * MIB,
    requestLabel: "Neftel protein program request JSON",
    defaultProfileId: NEFTEL_PROFILE_ID,
  },
  "gbm-master-kinases": {
    apiBase: "/backend/v1/research/gbm-master-kinases",
    requestLimitBytes: 2 * MIB,
    resultLimitBytes: 2 * MIB,
    replayLimitBytes: 4 * MIB,
    requestLabel: "GBM master kinase request JSON",
    defaultProfileId: MASTER_KINASE_PROFILE_ID,
  },
  "gbm-functional-proteotype": {
    apiBase: "/backend/v1/research/gbm-functional-proteotype",
    requestLimitBytes: 2 * MIB,
    resultLimitBytes: 2 * MIB,
    replayLimitBytes: 4 * MIB,
    requestLabel: "GBM functional proteotype request JSON",
    defaultProfileId: FUNCTIONAL_PROTEOTYPE_PROFILE_ID,
  },
  "gbm-rna-purity": {
    apiBase: "/backend/v1/research/gbm-rna-purity",
    requestLimitBytes: 4 * MIB,
    resultLimitBytes: 2 * MIB,
    replayLimitBytes: 8 * MIB,
    requestLabel: "GBM RNA purity request JSON",
    defaultProfileId: GBM_RNA_PURITY_PROFILE_ID,
  },
  "longitudinal-gbm": {
    apiBase: "/backend/v1/research/longitudinal-gbm",
    requestLimitBytes: 2 * MIB,
    resultLimitBytes: 4 * MIB,
    replayLimitBytes: 8 * MIB,
    requestLabel: "Longitudinal GBM request JSON",
    defaultProfileId: LONGITUDINAL_GBM_PROFILE_ID,
  },
  "longitudinal-gbm-phospho": {
    apiBase: "/backend/v1/research/longitudinal-gbm-phospho",
    requestLimitBytes: 2 * MIB,
    resultLimitBytes: 4 * MIB,
    replayLimitBytes: 8 * MIB,
    requestLabel: "Longitudinal GBM phosphosite request JSON",
    defaultProfileId: LONGITUDINAL_GBM_PHOSPHO_PROFILE_ID,
  },
  "longitudinal-gbm-kinase-transition": {
    apiBase: "/backend/v1/research/longitudinal-gbm-kinase-transition",
    requestLimitBytes: 2 * MIB,
    resultLimitBytes: 4 * MIB,
    replayLimitBytes: 8 * MIB,
    requestLabel: "Longitudinal GBM SPHINKS signature-transition request JSON",
    defaultProfileId: LONGITUDINAL_GBM_KINASE_TRANSITION_PROFILE_ID,
  },
  "longitudinal-gbm-reactome-transition": {
    apiBase: "/backend/v1/research/longitudinal-gbm-reactome-transition",
    requestLimitBytes: 2 * MIB,
    resultLimitBytes: 4 * MIB,
    replayLimitBytes: 8 * MIB,
    requestLabel: "Longitudinal GBM Reactome transition request JSON",
    defaultProfileId: LONGITUDINAL_GBM_REACTOME_TRANSITION_PROFILE_ID,
  },
  "longitudinal-gbm-neftel-transition": {
    apiBase: "/backend/v1/research/longitudinal-gbm-neftel-transition",
    requestLimitBytes: 2 * MIB,
    resultLimitBytes: 4 * MIB,
    replayLimitBytes: 8 * MIB,
    requestLabel: "Longitudinal GBM Neftel program transition request JSON",
    defaultProfileId: LONGITUDINAL_GBM_NEFTEL_TRANSITION_PROFILE_ID,
  },
  "longitudinal-gbm-complex-transition": {
    apiBase: "/backend/v1/research/longitudinal-gbm-complex-transition",
    requestLimitBytes: 2 * MIB,
    resultLimitBytes: 4 * MIB,
    replayLimitBytes: 8 * MIB,
    requestLabel: "Longitudinal GBM complex transition request JSON",
    defaultProfileId: LONGITUDINAL_GBM_COMPLEX_TRANSITION_PROFILE_ID,
  },
  "gbm-factor-graph": {
    apiBase: "/backend/v1/research/gbm-factor-graph",
    requestLimitBytes: 4 * MIB,
    resultLimitBytes: 8 * MIB,
    replayLimitBytes: 16 * MIB,
    requestLabel: "KNCC GBM factor graph request JSON",
    defaultProfileId: GBM_FACTOR_GRAPH_PROFILE_ID,
  },
};

const LANE_COPY: Record<WorkbenchMode, LaneCopy> = {
  "evidence-graph": {
    demoLoaded: "Synthetic demo loaded. Validate or run the evidence graph.",
    running: "Running deterministic graph inference and uncertainty analysis…",
    complete: "Analysis complete. The result remains research-use-only and non-prescriptive.",
    replayVerified: "Replay verified: digests, profile, solver trace, and semantics match.",
    reset: "Synthetic demo reset to its versioned source.",
    heroEyebrow: "GLIO-ECGI / EVIDENCE-CONSERVING GRAPH INFERENCE",
    heroLead: "Follow the evidence.",
    heroBoundary: "Preserve the uncertainty.",
    heroIntro: "A deterministic research surface for protein, proteoform, complex, pathway, and experimental kinase-state inference. Missing evidence stays missing; every estimate carries its support, interval, and sensitivity trail.",
    inputTitle: "Graph request",
    emptyMark: "ECGI",
    emptyTitle: "The graph is ready for evidence.",
    emptyBody: "Run the synthetic demonstration or edit the request to inspect latent activities, uncertainty, kinase enrichment, and source-aware ablations.",
    emptyTags: ["IRLS", "bootstrap", "rank enrichment", "ablation"],
    receiptLabel: "Sample",
    receiptKey: "sample_id",
  },
  "gbm-proteomic-axes": {
    demoLoaded: "Synthetic GBM LFQ demo loaded. Validate or run the published model family.",
    running: "Running seven published GBM proteomic ensembles and measurement-error bootstrap…",
    complete: "GBM signature analysis complete. Scores describe bulk-tissue research programs, not patient subtypes or clinical states.",
    replayVerified: "Replay verified: request, profile, published model source, result digest, and semantics match.",
    reset: "Synthetic GBM LFQ demo reset to its content-bound source.",
    heroEyebrow: "GLIO / PUBLISHED GBM PROTEOMIC MODELS",
    heroLead: "Resolve glioblastoma programs.",
    heroBoundary: "Expose every assumption.",
    heroIntro: "A content-bound NumPy port of seven published glioblastoma proteomic XGBoost ensembles: KRAS-like, MYC-like, hypoxia, three Verhaak reference programs, and EGFR-up. Coverage and numeric zero-fill are visible, never passed off as biological absence.",
    inputTitle: "LFQ protein request",
    emptyMark: "GBM",
    emptyTitle: "The published model family is ready for LFQ evidence.",
    emptyBody: "Run the synthetic glioblastoma demonstration or edit the measurements to inspect seven scores, uncertainty, coverage, zero-fill burden, and exact model provenance.",
    emptyTags: ["7 ensembles", "4,200 stumps", "bootstrap", "replay"],
    receiptLabel: "Sample",
    receiptKey: "sample_id",
  },
  "neftel-programs": {
    demoLoaded: "Synthetic Neftel AC-like protein demo loaded. Validate or run both inference methods.",
    running: "Running robust one-sided location inference, rank permutations, bootstrap, and family ablations…",
    complete: "Neftel bulk-protein program analysis complete. Evidence is program-level—not a cell fraction, tumor-cell origin, or subtype call.",
    replayVerified: "Replay verified: request, profile, pinned marker catalog, result digest, and semantics match.",
    reset: "Synthetic Neftel protein-program demo reset to its content-bound source.",
    heroEyebrow: "GLIO / NEFTEL BULK-PROTEIN PROGRAM EVIDENCE",
    heroLead: "Map glioblastoma programs.",
    heroBoundary: "Keep methods accountable.",
    heroIntro: "Exact Neftel Table S2 modules translated to protein-eligible markers with pinned HGNC aliases. One-sided robust location and reliability-weighted rank enrichment are reported separately, with bootstrap intervals, empirical q-values, coverage-aware abstention, and marker-family ablations.",
    inputTitle: "Protein contrast request",
    emptyMark: "S2",
    emptyTitle: "The Neftel program catalog is ready for protein evidence.",
    emptyBody: "Run the synthetic AC-like demonstration or edit standardized protein contrasts to inspect eight exact modules, five pooled families, uncertainty, q-values, and ablations.",
    emptyTags: ["Huber location", "permutations", "BH q-values", "ablation"],
    receiptLabel: "Sample",
    receiptKey: "sample_id",
  },
  "gbm-master-kinases": {
    demoLoaded: "Synthetic glioma-like phosphosite contrast loaded. Validate or run the 24 pinned master-kinase signatures.",
    running: "Running independent SPHINKS-signature concordance, stratified permutations, bootstrap, and residue ablations…",
    complete: "Master-kinase signature concordance complete. Results are independent research evidence—not calibrated kinase activity or a patient subtype call.",
    replayVerified: "Replay verified: request, profile, SPHINKS signature catalog, result digest, and semantics match.",
    reset: "Synthetic master-kinase phosphosite demo reset to its content-bound source.",
    heroEyebrow: "GLIO / SPHINKS MASTER-KINASE SIGNATURE CONCORDANCE",
    heroLead: "Interrogate GBM kinase signatures.",
    heroBoundary: "Keep the source boundary explicit.",
    heroIntro: "Independent evidence concordance against 24 frozen SPHINKS/MK master-kinase signatures across GPM, MTC, NEU, and PPR. Robust site-level location and residue-stratified rank enrichment remain separate, with deterministic uncertainty, q-values, coverage-aware abstention, and ablations.",
    inputTitle: "Phosphosite contrast request",
    emptyMark: "MK",
    emptyTitle: "The 24 master-kinase signatures are ready for phosphosite evidence.",
    emptyBody: "Run the synthetic glioma-like phosphosite contrast or edit the evidence to inspect 24 kinase signatures, four source-subtype aggregates, uncertainty, q-values, discordance, drivers, and ablations.",
    emptyTags: ["24 signatures", "stratified null", "BH q-values", "replay"],
    receiptLabel: "Sample",
    receiptKey: "sample_id",
  },
  "gbm-functional-proteotype": {
    demoLoaded: "Synthetic Migliozzi GBM functional-proteotype demo loaded. Validate or run the four constrained source axes.",
    running: "Running constrained robust four-axis inference, bootstrap intervals, stratified rank permutations, and source-aware ablations…",
    complete: "Functional-proteotype concordance complete. Four jointly constrained source axes were reported without a patient subtype classification.",
    replayVerified: "Replay verified: request, profile, constrained solver trace, source catalogs, result digest, and semantics match.",
    reset: "Synthetic Migliozzi functional-proteotype demo reset to its content-bound source.",
    heroEyebrow: "GLIO / MIGLIOZZI GBM FUNCTIONAL PROTEOTYPE CONCORDANCE",
    heroLead: "Resolve four GBM source axes.",
    heroBoundary: "Never force a subtype.",
    heroIntro: "Bulk-protein concordance with 600 source-selected Migliozzi Table 2d proteins, jointly fitted as GPM, MTC, NEU, and PPR coordinates under an exact sum-to-zero constraint. Robust one-sided inference, bootstrap intervals, independent competitive-rank q-values, and ablations stay visible; no winner, probability, clinical subtype, or sample pathway activity is emitted.",
    inputTitle: "Protein contrast request",
    emptyMark: "FPT",
    emptyTitle: "The four constrained source axes are ready for protein evidence.",
    emptyBody: "Run the synthetic bulk-protein contrast or edit exact Table 2d genes to inspect four constrained coordinates, intervals, independent q-values, protein drivers, ablations, and source-only pathway context—without a patient subtype call.",
    emptyTags: ["Σ z = 0", "Huber IRLS", "independent q-values", "ablation"],
    receiptLabel: "Sample",
    receiptKey: "sample_id",
  },
  "gbm-rna-purity": {
    demoLoaded: "Synthetic primary IDH-wildtype GBM raw-count demo loaded. Validate or run the exact published GBMPurity network.",
    running: "Running the exact published 5,829→32→16→1 GBMPurity forward pass and active-ReLU decomposition…",
    complete: "GBMPurity inference complete. The published model estimate is research-only and carries no fabricated calibrated interval.",
    replayVerified: "Replay verified: raw-count request, exact published model artifact, profile, result digest, and semantics match.",
    reset: "Synthetic primary IDH-wildtype GBM raw-count demo reset to its content-bound GBMPurity source.",
    heroEyebrow: "GLIO / PUBLISHED GBMPURITY RNA MODEL",
    heroLead: "Estimate malignant-cell fraction.",
    heroBoundary: "Keep the model boundary visible.",
    heroIntro: "An exact deterministic NumPy forward pass through the released GBMPurity 5,829→32→16→1 network for primary IDH-wildtype glioblastoma bulk RNA-seq raw counts. Exact feature coverage, source-parity preprocessing, clipping, hidden activations, and local active-ReLU contributions remain visible; no immune composition, diagnosis, prognosis, treatment claim, or invented uncertainty interval is emitted.",
    inputTitle: "Raw RNA count request",
    emptyMark: "RNA",
    emptyTitle: "The published GBMPurity network is ready for raw RNA counts.",
    emptyBody: "Run the synthetic raw-count demonstration or submit an in-scope bulk RNA count table to inspect the one published malignant-cell-fraction estimate, exact feature coverage, hidden activations, active-ReLU attribution, and pinned source receipt.",
    emptyTags: ["5,829 genes", "exact MLP", "local decomposition", "replay"],
    receiptLabel: "Sample",
    receiptKey: "sample_id",
  },
  "longitudinal-gbm": {
    demoLoaded: "Synthetic ordered GBM protein series loaded. Validate or run paired transitions and change-point sensitivity.",
    running: "Running paired protein-transition concordance, covariance-aware uncertainty, frozen-model ablations, and duration-normalized rate PELT…",
    complete: "Longitudinal protein concordance complete. Results describe source-cohort direction—not patient evolution, recurrence risk, or a clinical trajectory.",
    replayVerified: "Replay verified: request, frozen transition model, transition semantics, PELT semantics, and result digest match.",
    reset: "Synthetic longitudinal GBM protein series reset to its content-bound source.",
    heroEyebrow: "GLIO / KNCC LONGITUDINAL GBM PROTEIN CONCORDANCE",
    heroLead: "Trace protein transitions.",
    heroBoundary: "Keep evolution claims bounded.",
    heroIntro: "A de-identified paired-transition axis fitted to the PDC000514 longitudinal GBM source cohort. Robust concordance, paired-bootstrap covariance-aware uncertainty, source-processing and top-driver ablations, and duration-normalized transition-rate PELT stay visible without claiming patient evolution or recurrence prediction.",
    inputTitle: "Ordered protein series",
    emptyMark: "LGBM",
    emptyTitle: "The paired longitudinal protein model is ready for an ordered series.",
    emptyBody: "Run the synthetic ordered protein series or edit its time points to inspect paired-transition intervals, covariance, support, drivers, source-processing sensitivity, and duration-normalized rate regimes.",
    emptyTags: ["paired axis", "covariance", "ablations", "rate PELT"],
    receiptLabel: "Series",
    receiptKey: "series_id",
  },
  "longitudinal-gbm-phospho": {
    demoLoaded: "Synthetic ordered PDC000515 phosphosite series loaded. Validate or run the fitted raw phosphosite transition axis.",
    running: "Running the source-fitted phosphosite transition axis, exact sparse bootstrap projections, three-way uncertainty closure, bounds, and ablations…",
    complete: "Longitudinal phosphosite concordance complete. Results remain limited research evidence—not occupancy, kinase activity, recurrence prediction, or clinical guidance.",
    replayVerified: "Replay verified: request, PDC000515 source artifact, phosphosite transition semantics, model-view boundaries, and result digest match.",
    reset: "Synthetic longitudinal GBM phosphosite series reset to its PDC000515-bound source.",
    heroEyebrow: "GLIO / PDC000515 LONGITUDINAL PHOSPHOSITE CONCORDANCE",
    heroLead: "Trace phosphosite transitions.",
    heroBoundary: "Do not invent occupancy.",
    heroIntro: "A source-fitted raw phosphosite axis learned from 88 strict paired GBM transitions and 24,015 exact ENSP-versioned site groups. Twenty partition audits, 64 exact Huber/bootstrap refits, one-sided censoring, covariance closure, SPHINKS identity annotations, and ablations remain visible; unstable selection and uncalibrated intervals force limited support.",
    inputTitle: "Ordered phosphosite series",
    emptyMark: "P515",
    emptyTitle: "The PDC000515 phosphosite transition model is ready for an ordered series.",
    emptyBody: "Run the synthetic ordered phosphosite series or edit exact source groups to inspect source-aligned intervals, direct uncertainty closure, censored bounds, SPHINKS annotations, and model-view abstentions.",
    emptyTags: ["20 partitions", "64 refits", "3-way variance", "ablation"],
    receiptLabel: "Series",
    receiptKey: "series_id",
  },
  "longitudinal-gbm-kinase-transition": {
    demoLoaded: "Synthetic ordered PDC000515 phosphosite series loaded. Validate or run the fixed 24-kinase SPHINKS signature-transition model.",
    running: "Running residue-stratified SPHINKS family projection, deterministic measurement perturbation, patient-refit bootstrap, and three source-policy ablations…",
    complete: "SPHINKS signature-transition concordance complete. Outputs remain LIMITED same-assay evidence—not kinase activity, biochemical activity, causality, or clinical guidance.",
    replayVerified: "Replay verified: request, exact 24-kinase family, LIMITED semantics, transition receipt, provenance, and digests match.",
    reset: "Synthetic SPHINKS signature-transition series reset to its content-bound PDC000515 source.",
    heroEyebrow: "GLIO / KNCC SPHINKS SIGNATURE-TRANSITION CONCORDANCE",
    heroLead: "Trace kinase signatures.",
    heroBoundary: "Never call them activity.",
    heroIntro: "Twenty-four frozen SPHINKS master-kinase hypotheses projected through exact PDC000515 phosphosite families across ordered GBM time points. Residue-stratified rank concordance, inverse multiplicity, indivisible composite sites, deterministic uncertainty, patient-refit stability, drivers, and ablations remain visible. Every estimable output is LIMITED; this lane does not infer kinase activity, biochemical activity, causality, independent validation, recurrence, or clinical action.",
    inputTitle: "Ordered phosphosite series",
    emptyMark: "K24",
    emptyTitle: "The fixed SPHINKS signature family is ready for an ordered series.",
    emptyBody: "Run the synthetic PDC000515 series or edit exact source groups to inspect 24 locked signatures, four subtype aggregates, uncertainty, drivers, selection stability, and policy ablations.",
    emptyTags: ["24 hypotheses", "BH family", "64 patient refits", "LIMITED only"],
    receiptLabel: "Series",
    receiptKey: "series_id",
  },
  "longitudinal-gbm-reactome-transition": {
    demoLoaded: "Synthetic ordered KNCC protein series loaded. Validate or run the fixed 10-pathway Reactome conditional-concordance model.",
    running: "Running robust global-adjusted Reactome conditional coordinates, deterministic measurement and fitted-model bootstrap, reconstruction checks, and structural ablations…",
    complete: "Reactome conditional concordance complete. Results are source-cohort coordinates—not pathway activity, pathway flux, patient evolution, recurrence prediction, or clinical guidance.",
    replayVerified: "Replay verified: request, fixed Reactome panel, fitted conditional model, transition semantics, uncertainty, ablations, provenance, and result digest match.",
    reset: "Synthetic KNCC Reactome transition series reset to its content-bound source and fixed panel.",
    heroEyebrow: "GLIO / KNCC REACTOME CONDITIONAL TRANSITION CONCORDANCE",
    heroLead: "Condition GBM transitions.",
    heroBoundary: "Keep pathway claims honest.",
    heroIntro: "A robust global-adjusted dictionary fitted to 104 strict PDC000514 paired-patient protein transitions and ten outcome-blind Reactome V97 pathways. Unadjusted, global, and conditional coordinates; one-sided censoring; measurement and fitted-model uncertainty; held-gene reconstruction; contributions; and structural ablations remain visible. Outputs are not pathway activity, flux, causal biology, patient evolution, recurrence prediction, or clinical guidance.",
    inputTitle: "Ordered protein series",
    emptyMark: "R97",
    emptyTitle: "The fixed Reactome conditional dictionary is ready for an ordered protein series.",
    emptyBody: "Run the synthetic ordered KNCC protein series or edit its time points to inspect one global and ten conditional coordinates, intervals, censoring, reconstruction evidence, contributions, ablations, and exact source provenance.",
    emptyTags: ["10 pathways", "robust ridge", "held-gene audit", "structural ablations"],
    receiptLabel: "Series",
    receiptKey: "series_id",
  },
  "longitudinal-gbm-neftel-transition": {
    demoLoaded: "Synthetic ordered KNCC protein series loaded. Validate or run the exact 8-program Neftel conditional-concordance model.",
    running: "Running global-adjusted Neftel program coordinates, deterministic measurement and fitted-model bootstrap, held-marker reconstruction, and structural ablations…",
    complete: "Neftel program transition concordance complete. The fitted dictionary remains LIMITED because it did not beat equal membership; outputs are not cell states, fractions, activation, evolution, or clinical predictions.",
    replayVerified: "Replay verified: request, eight exact Neftel programs, fitted model, LIMITED release gate, transition semantics, uncertainty, provenance, and result digest match.",
    reset: "Synthetic KNCC Neftel transition series reset to its content-bound source and exact eight-program panel.",
    heroEyebrow: "GLIO / KNCC NEFTEL PROGRAM TRANSITION CONCORDANCE",
    heroLead: "Track bulk-protein program coordinates.",
    heroBoundary: "Keep the failed baseline gate visible.",
    heroIntro: "Eight exact Neftel Table S2 program identities projected through pinned HGNC mappings onto 104 strict PDC000514 paired-patient protein transitions. Robust global-adjusted coordinates, one-sided censoring, deterministic uncertainty, held-marker reconstruction, contributions, and structural ablations remain visible. The fitted dictionary loses to the prespecified equal-membership baseline, every leave-program interval crosses zero, and the lane is LIMITED—not cell-state deconvolution, activation, recurrence prediction, or clinical guidance.",
    inputTitle: "Ordered protein series",
    emptyMark: "N8",
    emptyTitle: "The eight fitted Neftel program coordinates are ready for an ordered series.",
    emptyBody: "Run the synthetic KNCC series or edit its time points to inspect global and conditional coordinates, uncertainty, censoring, exact program identities, the failed equal-membership comparison, and source-bound provenance.",
    emptyTags: ["8 exact programs", "Huber ridge", "held-marker audit", "LIMITED gate"],
    receiptLabel: "Series",
    receiptKey: "series_id",
  },
  "longitudinal-gbm-complex-transition": {
    demoLoaded: "Synthetic ordered KNCC protein series loaded. Validate or run the 28-complex Reactome participant-transition model.",
    running: "Running robust complex-member factor coordinates, deterministic measurement and fitted-source bootstrap, and member/topology ablations…",
    complete: "Complex-member transition concordance complete. Results do not claim physical assembly, activity, stoichiometry, essentiality, or causality.",
    replayVerified: "Replay verified: request, exact Reactome participant sets, fitted factor model, uncertainty, ablations, provenance, and result digest match.",
    reset: "Synthetic KNCC complex-transition series reset to its content-bound PDC000514 and Reactome V97 source.",
    heroEyebrow: "GLIO / KNCC REACTOME COMPLEX-MEMBER TRANSITION CONCORDANCE",
    heroLead: "Resolve GBM participant sets.",
    heroBoundary: "Do not invent complex activity.",
    heroIntro: "Twenty-eight repository-authored Reactome V97 participant sets across eleven glioblastoma-relevant signaling and stress domains, fitted from 104 strict PDC000514 paired-patient protein transitions. Panel choices were informed by the same source paper; the importer did not read abundance arrays while selecting them, but outcome independence is not established. Missing-aware rank-one Huber factors, one-sided censoring, patient-grouped held-member evaluation, deterministic uncertainty, drivers, and ablations stay visible. Outputs are participant-set concordance only—not assembly, activity, stoichiometry, essentiality, causality, prognosis, or treatment guidance.",
    inputTitle: "Ordered protein series",
    emptyMark: "C28",
    emptyTitle: "The 28 fitted Reactome participant sets are ready for an ordered series.",
    emptyBody: "Run the synthetic KNCC demonstration or edit its time points to inspect robust complex-member coordinates, intervals, censoring, source evaluation, local contributions, and topology/source ablations.",
    emptyTags: ["28 participant sets", "Huber factor", "held-member audit", "four ablations"],
    receiptLabel: "Series",
    receiptKey: "series_id",
  },
  "gbm-factor-graph": {
    demoLoaded: "Synthetic KNCC factor-graph composition loaded. Validate or run both independently fitted child blocks in deterministic sequence.",
    running: "Running the independent protein/Reactome child, then the phosphosite/SPHINKS child, and binding both exact receipts into the annotation-only composition…",
    complete: "Factor-graph composition complete. The two source-cohort child results remain independent; no cross-modal fusion or additional fitted inference was performed.",
    replayVerified: "Replay verified: outer composition, topology, both exact child receipts, independent-block semantics, no-fusion boundary, provenance, and digests match.",
    reset: "Synthetic KNCC factor-graph composition reset to its two content-bound child requests.",
    heroEyebrow: "GLIO-ECGI / KNCC GBM INDEPENDENT FACTOR-GRAPH COMPOSITION",
    heroLead: "Place both result families.",
    heroBoundary: "Never fuse their evidence.",
    heroIntro: "A composition and presentation surface for the fitted PDC000514 Reactome protein-transition model and fitted PDC000515 SPHINKS phosphosite signature-transition model. The children run deterministically in sequence and retain separate requests, scores, uncertainty, limitations, and receipts. The 41-node / 39-edge topology is annotation-only: there are no cross-block numerical edges, no cross-modal fusion, and no additional fitted inference model.",
    inputTitle: "Independent child requests",
    emptyMark: "2×",
    emptyTitle: "The two independent KNCC child models are ready.",
    emptyBody: "Run the synthetic composition or edit either nested child request to inspect the locked annotation topology, the full Reactome and SPHINKS result families, source-cohort limitations, and exact replay bindings without cross-modal coupling.",
    emptyTags: ["41 nodes", "39 annotations", "2 child receipts", "0 fusion edges"],
    receiptLabel: "Analysis",
    receiptKey: "analysis_id",
  },
};

function assertNever(value: never): never {
  throw new Error(`Unsupported workbench mode: ${String(value)}`);
}

function validateModeRequest(mode: WorkbenchMode, request: JsonObject): string[] {
  switch (mode) {
    case "evidence-graph": return validateResearchRequest(request);
    case "gbm-proteomic-axes": return validateGbmRequest(request);
    case "neftel-programs": return validateNeftelRequest(request);
    case "gbm-master-kinases": return validateMasterKinaseRequest(request);
    case "gbm-functional-proteotype": return validateFunctionalProteotypeRequest(request);
    case "gbm-rna-purity": return validateGbmRnaPurityRequest(request);
    case "longitudinal-gbm": return validateLongitudinalRequest(request);
    case "longitudinal-gbm-phospho": return validateLongitudinalPhosphoRequest(request);
    case "longitudinal-gbm-kinase-transition": return validateKinaseTransitionRequest(request);
    case "longitudinal-gbm-reactome-transition": return validateReactomeTransitionRequest(request);
    case "longitudinal-gbm-neftel-transition": return validateNeftelTransitionRequest(request);
    case "longitudinal-gbm-complex-transition": return validateComplexTransitionRequest(request);
    case "gbm-factor-graph": return validateFactorGraphRequest(request);
    default: return assertNever(mode);
  }
}

function neftelTransitionDemoAdmissionErrors(
  request: JsonObject,
  headers: Pick<Headers, "get">,
  admittedProfile: JsonObject | null,
): string[] {
  const errors = validateNeftelTransitionRequest(request);
  const requestDigest = neftelTransitionRequestDigest(request);
  const headerDigest = headers.get("X-GLIO-Request-Digest");
  if (headerDigest !== requestDigest) {
    errors.push(
      "X-GLIO-Request-Digest response header must match the canonical demo request digest.",
    );
  }
  if (admittedProfile === null) {
    errors.push("The admitted Neftel-transition profile is unavailable for demo binding.");
  } else if (admittedProfile.demo_request_digest !== requestDigest) {
    errors.push(
      "The canonical demo request digest must match the loaded profile.demo_request_digest.",
    );
  }
  return errors;
}

function usesSeriesTimeout(mode: WorkbenchMode): boolean {
  switch (mode) {
    case "longitudinal-gbm":
    case "longitudinal-gbm-phospho":
    case "longitudinal-gbm-kinase-transition":
    case "longitudinal-gbm-reactome-transition":
    case "longitudinal-gbm-neftel-transition":
    case "longitudinal-gbm-complex-transition":
    case "gbm-factor-graph":
      return true;
    case "evidence-graph":
    case "gbm-proteomic-axes":
    case "neftel-programs":
    case "gbm-master-kinases":
    case "gbm-functional-proteotype":
    case "gbm-rna-purity":
      return false;
    default:
      return assertNever(mode);
  }
}

const EMPTY_PROBE: Probe = { state: "checking", detail: "checking", latency: null };
const KIND_ORDER: StateKind[] = GRAPH_KIND_ORDER;

function safeJson(value: unknown): JsonValue {
  return JSON.parse(JSON.stringify(value)) as JsonValue;
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([pretty(payload)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function statusClass(classification: string): string {
  const value = classification.toLowerCase();
  if (value.includes("activ") || value.includes("increase") || value === "up") return "activated";
  if (value.includes("suppress") || value.includes("decrease") || value === "down") return "suppressed";
  if (value.includes("neutral") || value.includes("stable")) return "neutral";
  return "indeterminate";
}

function StateBadge({ value }: { value: string }) {
  return <span className={`state-badge ${statusClass(value)}`}>{value.replaceAll("_", " ")}</span>;
}

function ProbeBadge({ label, probe }: { label: string; probe: Probe }) {
  return (
    <span className={`probe-badge ${probe.state}`} title={probe.detail}>
      <i />
      <b>{label}</b>
      <span>{probe.state}{probe.latency === null ? "" : ` · ${probe.latency} ms`}</span>
    </span>
  );
}

function ActivityMark({ state }: { state: NormalizedState }) {
  const estimate = state.estimate ?? 0;
  const bounded = Math.max(-2, Math.min(2, estimate));
  return (
    <div className="activity-mark" aria-label={`Activity ${formatSigned(state.estimate)}`}>
      <span className="activity-zero" />
      <span
        className={`activity-fill ${bounded < 0 ? "negative" : "positive"}`}
        style={{ left: bounded < 0 ? `${50 + bounded * 25}%` : "50%", width: `${Math.abs(bounded) * 25}%` }}
      />
      <i style={{ left: `${50 + bounded * 25}%` }} />
    </div>
  );
}

function StateTable({ title, states, empty }: { title: string; states: NormalizedState[]; empty: string }) {
  return (
    <section className="result-panel state-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">INFERRED STATE</p><h3>{title}</h3></div>
        <span className="count-chip">{states.length}</span>
      </div>
      {states.length === 0 ? <p className="panel-empty">{empty}</p> : (
        <div className="state-table-wrap">
          <table className="state-table">
            <thead><tr><th>Entity</th><th>Activity</th><th>90% interval</th><th>State</th><th>Evidence</th><th>Stability</th><th>Drivers</th></tr></thead>
            <tbody>
              {states.map((state) => (
                <tr key={`${state.kind}-${state.id}`}>
                  <td><b>{state.label}</b><small>{state.id !== state.label ? state.id : state.kind}</small></td>
                  <td><span className="activity-value">{formatSigned(state.estimate)}</span><ActivityMark state={state} /></td>
                  <td className="mono-cell">[{formatNumber(state.lower)}, {formatNumber(state.upper)}]</td>
                  <td><StateBadge value={state.classification} />{state.abstentionReason && <small className="warning-copy">{state.abstentionReason}</small>}</td>
                  <td className="mono-cell">{state.evidenceCount ?? "—"}</td>
                  <td className="mono-cell">{formatNumber(state.stability)}</td>
                  <td><span className="driver-copy">{state.drivers.slice(0, 2).join(" · ") || "—"}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function NetworkColumns({ request, states }: { request: JsonObject; states: NormalizedState[] }) {
  const graph = useMemo(() => buildEvidenceGraph(request, states), [request, states]);
  return (
    <section className="result-panel network-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">SIGNED EVIDENCE GRAPH</p><h3 id="evidence-graph-heading">Type-column network</h3></div>
        <span className="panel-note">{graph.edges.length} executed relations · arrowheads show source → target</span>
      </div>
      {graph.nodes.length === 0 ? <p className="panel-empty">The executed request contained no graph nodes.</p> : (
        <>
          <div className="network-key" aria-label="Relation encoding">
            <span className="positive"><i />+1 positive relation</span>
            <span className="negative"><i />−1 negative relation</span>
            <span><i className="essential" />essential membership</span>
          </div>
          <figure className="network-figure" aria-labelledby="evidence-graph-heading">
            <div className="network-viewport" tabIndex={0} aria-label="Scrollable evidence graph">
              <div className="network-canvas" style={{ width: graph.width, height: graph.height }}>
                <svg
                  className="network-svg"
                  width={graph.width}
                  height={graph.height}
                  viewBox={`0 0 ${graph.width} ${graph.height}`}
                  role="img"
                  aria-label={`${graph.nodes.length} typed nodes and ${graph.edges.length} directed signed relations from the executed request`}
                >
                  <title>Executed signed evidence graph</title>
                  <desc>Nodes are grouped into deterministic type columns. Every connector is an executed request relation; its arrowhead points from source to target, and color and dash encode sign.</desc>
                  <defs>
                    <marker id="network-arrow-positive" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
                      <path d="M 0 0 L 8 4 L 0 8 z" />
                    </marker>
                    <marker id="network-arrow-negative" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
                      <path d="M 0 0 L 8 4 L 0 8 z" />
                    </marker>
                  </defs>
                  <g className="network-column-guides" aria-hidden="true">
                    {graph.columns.map((column) => (
                      <line
                        key={column.kind}
                        x1={column.x + GRAPH_NODE_WIDTH / 2}
                        x2={column.x + GRAPH_NODE_WIDTH / 2}
                        y1={45}
                        y2={graph.height - 12}
                      />
                    ))}
                  </g>
                  <g className="network-edge-layer" role="list" aria-label="Executed request relations">
                    {graph.edges.map((edge) => {
                      const description = describeGraphEdge(edge);
                      return (
                        <g
                          key={edge.id}
                          className={`network-edge ${edge.sign > 0 ? "positive" : "negative"}${edge.essential ? " essential" : ""}`}
                          role="listitem"
                          aria-label={description}
                          data-edge-id={edge.id}
                          data-source-id={edge.sourceId}
                          data-target-id={edge.targetId}
                          data-edge-kind={edge.kind}
                          data-edge-sign={edge.sign}
                          data-edge-weight={edge.weight}
                        >
                          <title>{description}</title>
                          <path
                            d={edge.path}
                            markerEnd={`url(#network-arrow-${edge.sign > 0 ? "positive" : "negative"})`}
                            vectorEffect="non-scaling-stroke"
                          />
                          <g className="network-edge-label" transform={`translate(${edge.labelX} ${edge.labelY})`} aria-hidden="true">
                            <rect x="-61" y="-9" width="122" height="18" rx="3" />
                            <text textAnchor="middle" dominantBaseline="central">{edge.sign > 0 ? "+" : "−"} {edge.kind} · {formatNumber(edge.weight, 2)}</text>
                          </g>
                        </g>
                      );
                    })}
                  </g>
                </svg>
                {graph.columns.map((column) => (
                  <div
                    className="network-column-label"
                    key={column.kind}
                    style={{ left: column.x, width: GRAPH_NODE_WIDTH }}
                    data-node-kind-column={column.kind}
                  >
                    <span>{String(column.index + 1).padStart(2, "0")}</span>{column.kind}<em>{column.nodeCount}</em>
                  </div>
                ))}
                {graph.nodes.map((node) => {
                  const state = node.state;
                  return (
                    <article
                      className={`network-node ${statusClass(state?.classification ?? "indeterminate")}`}
                      key={`${node.kind}-${node.id}`}
                      style={{ left: node.x, top: node.y, width: GRAPH_NODE_WIDTH, height: GRAPH_NODE_HEIGHT }}
                      aria-label={`${node.label}, ${node.kind} node, activity ${formatSigned(state?.estimate ?? null)}`}
                      data-node-id={node.id}
                      data-node-kind={node.kind}
                    >
                      <div><b>{node.label}</b><small>{node.kind} · {state?.evidenceCount ?? 0} evidence</small></div>
                      <strong>{formatSigned(state?.estimate ?? null)}</strong>
                      <code>{node.id}</code>
                      <span className="network-interval">{formatNumber(state?.lower ?? null)} ↔ {formatNumber(state?.upper ?? null)}</span>
                    </article>
                  );
                })}
              </div>
            </div>
            <figcaption>The canvas and relation ledger are generated from the request that produced this receipt, not from unexecuted editor changes.</figcaption>
          </figure>
          <section className="network-relation-ledger" aria-labelledby="relation-ledger-heading">
            <div className="panel-title-row"><div><p className="eyebrow">EXECUTED REQUEST</p><h4 id="relation-ledger-heading">Relation ledger</h4></div><span className="count-chip">{graph.edges.length}</span></div>
            {graph.edges.length === 0 ? <p className="panel-empty">The executed graph has no relations.</p> : (
              <div className="network-relation-table-wrap">
                <table className="network-relation-table">
                  <thead><tr><th>Edge</th><th>Direction</th><th>Kind</th><th>Sign</th><th>Weight</th><th>Constraint</th></tr></thead>
                  <tbody>{graph.edges.map((edge) => (
                    <tr key={edge.id} data-relation-id={edge.id}>
                      <td><code>{edge.id}</code></td>
                      <td><code>{edge.sourceId} <span aria-hidden="true">→</span><span className="sr-only">to</span> {edge.targetId}</code></td>
                      <td>{edge.kind}</td>
                      <td><span className={`relation-sign ${edge.sign > 0 ? "positive" : "negative"}`}>{edge.sign > 0 ? "+1 positive" : "−1 negative"}</span></td>
                      <td className="mono-cell">{formatNumber(edge.weight, 2)}</td>
                      <td>{edge.essential ? "essential" : "—"}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </section>
  );
}

function safeHttpsUrl(value: string): string | null {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

function TopologyProvenancePanel({ topology }: { topology: JsonObject | null }) {
  const sources = topology ? arrayAt(topology, ["sources"]).filter(isJsonObject) : [];
  const derivation = topology ? textAt(topology, ["derivation"]) : "";
  return (
    <section className="result-panel topology-panel" aria-labelledby="topology-provenance-heading">
      <div className="panel-title-row">
        <div><p className="eyebrow">PUBLIC TOPOLOGY CONTEXT</p><h3 id="topology-provenance-heading">Topology provenance</h3></div>
        {topology && <span className="boundary-chip">{derivation.replaceAll("_", " ")}</span>}
      </div>
      {!topology ? <p className="panel-empty">No topology provenance was declared. Omission does not imply public support for this graph.</p> : (
        <>
          <div className="topology-declaration">
            <div><span>CANONICAL GRAPH DIGEST</span><code>{textAt(topology, ["topology_digest"], "—")}</code></div>
            <p><b>{derivation === "synthetic_abstraction" ? "Synthetic abstraction declaration" : "Caller-curated declaration"}</b>{textAt(topology, ["curation_note"], "No curation note supplied.")}</p>
          </div>
          <div className="topology-source-list">
            {sources.map((source, index) => {
              const sourceId = textAt(source, ["source_id"], `source-${index + 1}`);
              const sourceUri = safeHttpsUrl(textAt(source, ["source_uri"]));
              const licenseUri = safeHttpsUrl(textAt(source, ["license_uri"]));
              const scopes = arrayAt(source, ["scope_node_ids"]).filter((value): value is string => typeof value === "string");
              return (
                <article key={sourceId} data-topology-source-id={sourceId}>
                  <header>
                    <div><span>{textAt(source, ["resource_name"], "Public resource")} · release {textAt(source, ["resource_release"], "—")}</span><b>{textAt(source, ["record_title"], sourceId)}</b><small>{textAt(source, ["record_id"], sourceId)}</small></div>
                    <code>{textAt(source, ["source_format"], "—")}</code>
                  </header>
                  <div className="topology-scope"><span>Scoped nodes</span>{scopes.map((nodeId) => <code key={nodeId}>{nodeId}</code>)}</div>
                  <dl>
                    <div><dt>Retrieved</dt><dd>{textAt(source, ["retrieved_on"], "—")}</dd></div>
                    <div><dt>Artifact bytes</dt><dd>{formatNumber(numberAt(source, ["source_size_bytes"]), 0)}</dd></div>
                    <div><dt>Role</dt><dd>{textAt(source, ["role"], "biological_context")}</dd></div>
                    <div><dt>License</dt><dd>{licenseUri ? <a href={licenseUri} target="_blank" rel="noopener noreferrer">{textAt(source, ["license_id"], "license")} ↗</a> : textAt(source, ["license_id"], "—")}</dd></div>
                  </dl>
                  <div className="topology-link-row">
                    <span>Source URI</span>{sourceUri ? <a href={sourceUri} target="_blank" rel="noopener noreferrer"><code>{textAt(source, ["source_uri"])}</code></a> : <code>invalid or unavailable</code>}
                  </div>
                  <div className="topology-link-row"><span>Artifact digest</span><code>{textAt(source, ["source_digest"], "—")}</code></div>
                </article>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}

function JsonPanel({ title, eyebrow, value, empty }: { title: string; eyebrow: string; value: JsonValue | null; empty: string }) {
  return (
    <section className="result-panel json-panel">
      <div className="panel-title-row"><div><p className="eyebrow">{eyebrow}</p><h3>{title}</h3></div></div>
      {value === null ? <p className="panel-empty">{empty}</p> : <pre>{pretty(value)}</pre>}
    </section>
  );
}

function GbmScoreMark({ signature }: { signature: GbmSignature }) {
  const score = signature.score ?? 0;
  const boundedScore = Math.max(-2, Math.min(2, score));
  const boundedLower = Math.max(-2, Math.min(2, signature.lower ?? score));
  const boundedUpper = Math.max(-2, Math.min(2, signature.upper ?? score));
  return (
    <div className="gbm-score-mark" aria-label={`Published score ${formatSigned(signature.score)}`}>
      <span className="gbm-score-zero" />
      {signature.lower !== null && signature.upper !== null && (
        <span
          className="gbm-score-interval"
          style={{ left: `${50 + boundedLower * 25}%`, width: `${Math.max(0, boundedUpper - boundedLower) * 25}%` }}
        />
      )}
      <i style={{ left: `${50 + boundedScore * 25}%` }} />
    </div>
  );
}

function GbmSignatureTable({ signatures }: { signatures: GbmSignature[] }) {
  return (
    <section className="result-panel state-panel gbm-signature-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">PUBLISHED GBM MODEL FAMILY</p><h3>Seven proteomic signature scores</h3></div>
        <span className="boundary-chip">bulk-tissue activation · not subtype calls</span>
      </div>
      <div className="zero-fill-notice">
        <b>Missing-feature convention</b>
        <span>The source models set unmeasured model features to numeric zero. The UI reports that fraction explicitly; zero-filled inputs are not biological absence or suppression.</span>
      </div>
      <div className="state-table-wrap">
        <table className="state-table gbm-signature-table">
          <thead><tr><th>Signature</th><th>Published score</th><th>90% interval</th><th>Support</th><th>Observed coverage</th><th>Numeric zero-fill</th><th>Top tree-path driver</th></tr></thead>
          <tbody>{signatures.map((signature) => (
            <tr key={signature.id} data-signature-id={signature.id}>
              <td><b>{signature.displayName}</b><small>{signature.id}</small></td>
              <td><span className="activity-value">{formatSigned(signature.score, 4)}</span><GbmScoreMark signature={signature} /></td>
              <td className="mono-cell">{signature.lower === null || signature.upper === null ? "not estimated" : `[${formatNumber(signature.lower, 4)}, ${formatNumber(signature.upper, 4)}]`}</td>
              <td><span className={`support-badge ${signature.support}`}>{signature.support}</span>{signature.abstentionReason && <small className="warning-copy">{signature.abstentionReason}</small>}</td>
              <td className="mono-cell">{signature.observedFeatureCount} / {signature.modelFeatureCount}<small>{formatNumber(signature.observedFeatureFraction * 100, 1)}%</small></td>
              <td className="mono-cell">{signature.missingFeatureCount}<small>{formatNumber(signature.missingFeatureRatio * 100, 1)}%</small></td>
              <td>{signature.drivers[0] ? <><b>{signature.drivers[0].geneSymbol}</b><small>{formatSigned(signature.drivers[0].signedContribution, 4)} · {signature.drivers[0].inputSource.replaceAll("_", " ")}</small></> : <span className="panel-note">No driver claim</span>}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  );
}

function GbmDriverPanels({ signatures }: { signatures: GbmSignature[] }) {
  return (
    <section className="result-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">MODEL EXPLANATION</p><h3>Top summed tree-path drivers</h3></div>
        <span className="boundary-chip">not SHAP · not causal effects</span>
      </div>
      <div className="gbm-driver-grid">{signatures.map((signature) => (
        <article key={signature.id}>
          <header><div><b>{signature.displayName}</b><small>{signature.id}</small></div><strong>{formatSigned(signature.score, 4)}</strong></header>
          {signature.drivers.length === 0 ? <p>No ranked driver is available for this signature.</p> : (
            <ol>{signature.drivers.map((driver) => (
              <li key={driver.geneSymbol}>
                <div><b>{driver.geneSymbol}</b><span className={driver.inputSource === "observed_lfq" ? "observed" : "zero-filled"}>{driver.inputSource === "observed_lfq" ? "observed LFQ" : "zero-filled"}</span></div>
                <strong>{formatSigned(driver.signedContribution, 4)}</strong>
                <small>{driver.declaredState ?? "not declared"}</small>
              </li>
            ))}</ol>
          )}
        </article>
      ))}</div>
    </section>
  );
}

function NeftelProgramTable({ programs }: { programs: NeftelProgram[] }) {
  return (
    <section className="result-panel state-panel">
      <div className="panel-title-row"><div><p className="eyebrow">NEFTEL TABLE S2 / BULK PROTEIN EVIDENCE</p><h3>Exact modules and derived program families</h3></div><span className="boundary-chip">program evidence · not cell fractions</span></div>
      <div className="state-table-wrap"><table className="state-table neftel-program-table"><thead><tr><th>Program</th><th>Robust location</th><th>90% interval</th><th>Rank enrichment</th><th>p / q</th><th>Coverage</th><th>Support / agreement</th><th>Top marker</th></tr></thead><tbody>
        {programs.map((program) => <tr key={program.id} data-program-id={program.id}>
          <td><b>{program.id.replaceAll("_", " ")}</b><small>{program.kind.replaceAll("_", " ")} · {program.sourcePrograms.join(" + ")}</small></td>
          <td className="mono-cell">{formatSigned(program.locationScore)}</td>
          <td className="mono-cell">{program.locationLower === null || program.locationUpper === null ? "not estimable" : `[${formatNumber(program.locationLower)}, ${formatNumber(program.locationUpper)}]`}</td>
          <td className="mono-cell">{formatSigned(program.rankScore)}</td>
          <td className="mono-cell">{formatNumber(program.pValue, 4)} / {formatNumber(program.qValue, 4)}</td>
          <td className="mono-cell">{program.observedMarkers} / {program.eligibleMarkers}<small>{formatNumber(program.activeCoverage * 100, 1)}% active</small></td>
          <td><StateBadge value={program.classification} /><small><span className={`support-badge ${program.support}`}>{program.support}</span> · {program.agreement.replaceAll("_", " ")}</small>{program.reasons[0] && <small className="warning-copy">{program.reasons[0]}</small>}</td>
          <td>{program.drivers[0] ? <><b>{program.drivers[0].symbol}</b><small>{formatSigned(program.drivers[0].effect)} · {program.drivers[0].state.replaceAll("_", " ")}</small></> : "—"}</td>
        </tr>)}
      </tbody></table></div>
    </section>
  );
}

function NeftelExplanationPanels({ programs }: { programs: NeftelProgram[] }) {
  return (
    <section className="result-panel">
      <div className="panel-title-row"><div><p className="eyebrow">MARKER-LEVEL EXPLANATION</p><h3>Drivers and marker-family ablations</h3></div><span className="boundary-chip">location + rank methods remain separate</span></div>
      <div className="neftel-explanation-grid">{programs.map((program) => <article key={program.id}>
        <header><div><b>{program.id.replaceAll("_", " ")}</b><small>{program.classification.replaceAll("_", " ")} · {program.agreement.replaceAll("_", " ")}</small></div><strong>{formatSigned(program.locationScore)}</strong></header>
        <div className="neftel-driver-list">{program.drivers.length ? program.drivers.map((driver) => <div key={driver.symbol}><b>{driver.symbol}</b><span>{formatSigned(driver.effect)}</span><small>location {formatSigned(driver.locationInfluence)} · rank {formatSigned(driver.rankInfluence)}</small></div>) : <p>No marker driver claim; the program abstained.</p>}</div>
        <div className="neftel-ablation-list">{program.ablations.map((ablation) => <div key={ablation.family}><b>omit {ablation.family}</b><span>{ablation.removed} markers</span><small>Δ location {formatSigned(ablation.locationDelta)} · Δ rank {formatSigned(ablation.rankDelta)}</small></div>)}</div>
      </article>)}</div>
    </section>
  );
}

function MasterKinaseScoreMark({ kinase }: { kinase: MasterKinaseEvidence }) {
  const score = kinase.locationScore ?? 0;
  const lower = kinase.lower ?? score;
  const upper = kinase.upper ?? score;
  const bounded = (value: number) => Math.max(-3, Math.min(3, value));
  return (
    <div className="master-kinase-score-mark" aria-label={`Kinase concordance score ${formatSigned(kinase.locationScore)}`}>
      <span className="master-kinase-score-zero" />
      {kinase.lower !== null && kinase.upper !== null && (
        <span
          className="master-kinase-score-interval"
          style={{ left: `${50 + bounded(lower) * (50 / 3)}%`, width: `${Math.max(0, bounded(upper) - bounded(lower)) * (50 / 3)}%` }}
        />
      )}
      <i style={{ left: `${50 + bounded(score) * (50 / 3)}%` }} />
    </div>
  );
}

function MasterKinaseTable({ kinases }: { kinases: MasterKinaseEvidence[] }) {
  return (
    <section className="result-panel state-panel master-kinase-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">SPHINKS TABLES 5D / 5E · INDEPENDENT CONCORDANCE</p><h3>Twenty-four GBM master-kinase signatures</h3></div>
        <span className="boundary-chip">published signatures · not an exact SPHINKS port</span>
      </div>
      <div className="master-kinase-groups">
        {MASTER_KINASE_SUBTYPES.map((subtype) => {
          const members = kinases.filter((kinase) => kinase.subtype === subtype);
          return (
            <section className={`master-kinase-group subtype-${subtype.toLowerCase()}`} key={subtype} data-master-kinase-subtype={subtype}>
              <header><div><b>{subtype}</b><span>{members.length} signatures</span></div><small>{subtype === "GPM" ? "glycolytic / plurimetabolic" : subtype === "MTC" ? "mitochondrial" : subtype === "NEU" ? "neuronal" : "proliferative / progenitor"}</small></header>
              <div className="state-table-wrap">
                <table className="state-table master-kinase-table">
                  <thead><tr><th>Kinase</th><th>Score / 90% interval</th><th>Rank enrichment</th><th>p / q</th><th>Support</th><th>Coverage / ESS</th><th>Discordance / stability</th><th>Top driver</th></tr></thead>
                  <tbody>{members.map((kinase) => (
                    <tr key={kinase.id} data-master-kinase-id={kinase.id}>
                      <td><b>{kinase.id}</b><small>source {kinase.sourceLabel}</small></td>
                      <td><span className="activity-value">{formatSigned(kinase.locationScore)}</span><MasterKinaseScoreMark kinase={kinase} /><small>{kinase.lower === null || kinase.upper === null ? "interval not estimable" : `[${formatNumber(kinase.lower)}, ${formatNumber(kinase.upper)}]`} · bootstrap {kinase.bootstrapReplicatesSuccessful}/{kinase.bootstrapReplicatesRequested}</small></td>
                      <td className="mono-cell">{formatSigned(kinase.rankScore)}<small>bootstrap {kinase.rankBootstrapReplicatesSuccessful}/{kinase.rankBootstrapReplicatesRequested} · {kinase.permutationReplicates} null</small></td>
                      <td className="mono-cell">{formatNumber(kinase.pValue, 4)} / {formatNumber(kinase.qValue, 4)}</td>
                      <td><StateBadge value={kinase.classification} /><small><span className={`support-badge ${kinase.support}`}>{kinase.support}</span> · {kinase.agreement.replaceAll("_", " ")}</small>{kinase.reasons[0] && <small className="warning-copy">{kinase.reasons[0]}</small>}</td>
                      <td className="mono-cell">{kinase.activeSites} / {kinase.mappedSites}<small>{formatNumber(kinase.coverage * 100, 1)}% · ESS {formatNumber(kinase.effectiveSampleSize, 1)}</small></td>
                      <td className="mono-cell">{formatNumber(kinase.discordance)} / {formatNumber(kinase.stability)}</td>
                      <td>{kinase.drivers[0] ? <><b>{kinase.drivers[0].phosphositeId}</b><small>{formatSigned(kinase.drivers[0].effect)} · weight {formatNumber(kinase.drivers[0].weight)}</small></> : "—"}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </section>
          );
        })}
      </div>
    </section>
  );
}

function MasterKinaseSubtypePanel({ subtypes }: { subtypes: MasterKinaseSubtypeEvidence[] }) {
  return (
    <section className="result-panel">
      <div className="panel-title-row"><div><p className="eyebrow">SUBTYPE-LEVEL SYNTHESIS</p><h3>Four published GBM program aggregates</h3></div><span className="boundary-chip">aggregate evidence · not a patient subtype call</span></div>
      <div className="master-subtype-grid">{MASTER_KINASE_SUBTYPES.map((subtype) => {
        const evidence = subtypes.find((item) => item.id === subtype);
        return <article className={`subtype-${subtype.toLowerCase()}`} key={subtype} data-master-subtype-id={subtype}>
          <header><div><b>{subtype}</b><small>{evidence?.supportedMembers ?? 0} supported · {evidence?.estimatedMembers ?? 0} estimated / {evidence?.memberKinases.length ?? 0} members</small></div>{evidence ? <StateBadge value={evidence.classification} /> : <StateBadge value="not_estimable" />}</header>
          <strong>{formatSigned(evidence?.score ?? null)}</strong>
          <span>{!evidence || evidence.lower === null || evidence.upper === null ? "interval not estimable" : `[${formatNumber(evidence.lower)}, ${formatNumber(evidence.upper)}]`}</span>
          <dl><div><dt>support</dt><dd>{evidence?.support ?? "abstained"}</dd></div><div><dt>ESS / bootstrap</dt><dd>{formatNumber(evidence?.effectiveSampleSize ?? null, 1)} / {evidence?.bootstrapReplicatesSuccessful ?? 0}/{evidence?.bootstrapReplicatesRequested ?? 0}</dd></div><div><dt>discordance / stability</dt><dd>{formatNumber(evidence?.discordance ?? null)} / {formatNumber(evidence?.stability ?? null)}</dd></div></dl>
          <p>{evidence?.drivers.slice(0, 3).map((driver) => `${driver.kinaseId} ${formatSigned(driver.contribution)} (w ${formatNumber(driver.weight)})`).join(" · ") || evidence?.reasons[0] || "No supported aggregate drivers."}</p>
          {evidence && evidence.ablations.length > 0 && <div className="master-subtype-ablations">{evidence.ablations.slice(0, 4).map((ablation) => <small key={ablation.kinaseId}>omit {ablation.kinaseId}: Δ {formatSigned(ablation.scoreDelta)}</small>)}</div>}
        </article>;
      })}</div>
    </section>
  );
}

function MasterKinaseExplanationPanels({ kinases }: { kinases: MasterKinaseEvidence[] }) {
  return (
    <section className="result-panel">
      <div className="panel-title-row"><div><p className="eyebrow">SITE-LEVEL EXPLANATION / SENSITIVITY</p><h3>Phosphosite drivers and edge-family ablations</h3></div><span className="boundary-chip">location and rank evidence remain separate</span></div>
      <div className="master-explanation-grid">{kinases.map((kinase) => <article key={kinase.id} data-master-explanation-id={kinase.id}>
        <header><div><b>{kinase.id}</b><small>{kinase.subtype} · {kinase.classification.replaceAll("_", " ")} · {kinase.agreement.replaceAll("_", " ")}</small></div><strong>{formatSigned(kinase.locationScore)}</strong></header>
        <div className="master-driver-list">{kinase.drivers.length ? kinase.drivers.slice(0, 5).map((driver) => <div key={driver.observationId}><b>{driver.phosphositeId}</b><span>{formatSigned(driver.effect)}</span><small>{driver.state.replaceAll("_", " ")} · observation {driver.observationId} · provenance {shortDigest(driver.provenanceDigest)} · weight {formatNumber(driver.weight)} · location {formatSigned(driver.locationInfluence)} · rank {formatSigned(driver.rankInfluence)}</small></div>) : <p>No driver claim; this kinase abstained or had insufficient mapped support.</p>}</div>
        <div className="master-ablation-list">{kinase.ablations.map((ablation) => <div key={ablation.family}><b>omit {ablation.family.replaceAll("_", " ")}</b><span>{ablation.removed} edges</span><small>Δ location {formatSigned(ablation.locationDelta)} · Δ rank {formatSigned(ablation.rankDelta)}</small></div>)}</div>
      </article>)}</div>
    </section>
  );
}

export default function ResearchWorkbench() {
  const [mode, setMode] = useState<WorkbenchMode>("evidence-graph");
  const [profile, setProfile] = useState<JsonObject | null>(null);
  const [editor, setEditor] = useState("{}");
  const [request, setRequest] = useState<JsonObject | null>(null);
  const [result, setResult] = useState<JsonObject | null>(null);
  const [verification, setVerification] = useState<JsonObject | null>(null);
  const [live, setLive] = useState<Probe>(EMPTY_PROBE);
  const [ready, setReady] = useState<Probe>(EMPTY_PROBE);
  const [loadingDemo, setLoadingDemo] = useState(true);
  const [running, setRunning] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [message, setMessage] = useState("Loading the versioned synthetic demonstration…");
  const [error, setError] = useState("");
  const [view, setView] = useState<View>("results");
  const runController = useRef<AbortController | null>(null);
  const verifyController = useRef<AbortController | null>(null);
  const analysisGeneration = useRef(0);
  const verificationGeneration = useRef(0);
  const receiptGeneration = useRef(0);
  const probeControllers = useRef<Record<"/livez" | "/readyz", AbortController | null>>({
    "/livez": null,
    "/readyz": null,
  });
  const probeGenerations = useRef<Record<"/livez" | "/readyz", number>>({
    "/livez": 0,
    "/readyz": 0,
  });
  const lane = LANES[mode];
  const copy = LANE_COPY[mode];

  const probeService = useCallback(async (path: "/livez" | "/readyz", setter: (value: Probe) => void) => {
    probeControllers.current[path]?.abort();
    const controller = new AbortController();
    const generation = probeGenerations.current[path] + 1;
    probeControllers.current[path] = controller;
    probeGenerations.current[path] = generation;
    const started = performance.now();
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, PROBE_TIMEOUT_MS);
    try {
      const response = await fetch(`/backend${path}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      const latency = Math.round(performance.now() - started);
      const text = await readBoundedResponseText(response, HEALTH_RESPONSE_LIMIT_BYTES);
      let detail = response.ok ? "probe succeeded" : `HTTP ${response.status}`;
      try {
        const payload: unknown = JSON.parse(text);
        detail = isJsonObject(payload) ? textAt(payload, ["status", "detail", "message"], detail) : detail;
      } catch {
        // Probe bodies are diagnostics only; never surface arbitrary non-JSON text.
      }
      if (generation !== probeGenerations.current[path]) return;
      setter({ state: response.ok ? "online" : path === "/readyz" ? "degraded" : "offline", detail, latency });
    } catch (probeError) {
      if (generation !== probeGenerations.current[path]) return;
      setter({
        state: "offline",
        detail: timedOut ? "probe timed out" : isAbortError(probeError) ? "probe cancelled" : "probe failed",
        latency: null,
      });
    } finally {
      window.clearTimeout(timeout);
      if (generation === probeGenerations.current[path]) probeControllers.current[path] = null;
    }
  }, []);

  useEffect(() => {
    let active = true;
    setLoadingDemo(true);
    setError("");
    async function initialize() {
      const [profileResponse, demoResponse] = await Promise.allSettled([
        fetch(`${lane.apiBase}/profile`, { cache: "no-store" }).then(async (response) => {
          const payload = await readBoundedJsonObject(response, lane.resultLimitBytes);
          if (mode === "evidence-graph") {
            const profileErrors = [
              ...validateEcgiProfile(payload),
              ...validateEcgiProfileHeaders(response.headers, payload),
            ];
            if (profileErrors.length) throw new Error(`The evidence-graph profile failed closed:\n${profileErrors.join("\n")}`);
          } else if (mode === "longitudinal-gbm-kinase-transition") {
            const profileErrors = [
              ...validateKinaseTransitionProfile(payload),
              ...validateKinaseTransitionProfileHeaders(response.headers, payload),
            ];
            if (profileErrors.length) throw new Error(`The kinase-transition profile failed closed:\n${profileErrors.join("\n")}`);
          } else if (mode === "longitudinal-gbm-reactome-transition") {
            const profileErrors = [
              ...validateReactomeTransitionProfile(payload),
              ...validateReactomeTransitionProfileHeaders(response.headers, payload),
            ];
            if (profileErrors.length) throw new Error(`The Reactome-transition profile failed closed:\n${profileErrors.join("\n")}`);
          } else if (mode === "longitudinal-gbm-complex-transition") {
            const profileErrors = [
              ...validateComplexTransitionProfile(payload),
              ...validateComplexTransitionProfileHeaders(response.headers, payload),
            ];
            if (profileErrors.length) throw new Error(`The complex-transition profile failed closed:\n${profileErrors.join("\n")}`);
          } else if (mode === "longitudinal-gbm-neftel-transition") {
            const profileErrors = [
              ...validateNeftelTransitionProfile(payload),
              ...validateNeftelTransitionProfileHeaders(response.headers, payload),
            ];
            if (profileErrors.length) throw new Error(`The Neftel-transition profile failed closed:\n${profileErrors.join("\n")}`);
          } else if (mode === "gbm-factor-graph") {
            const profileErrors = [
              ...validateFactorGraphProfile(payload),
              ...validateFactorGraphProfileHeaders(response.headers, payload),
            ];
            if (profileErrors.length) throw new Error(`The factor-graph profile failed closed:\n${profileErrors.join("\n")}`);
          }
          return payload;
        }),
        fetch(`${lane.apiBase}/demo`, { cache: "no-store" }).then(async (response) => ({
          headers: response.headers,
          payload: await readBoundedJsonObject(response, lane.requestLimitBytes),
        })),
      ]);
      if (!active) return;
      const admittedProfile = profileResponse.status === "fulfilled"
        ? profileResponse.value
        : null;
      setProfile(admittedProfile);
      if (demoResponse.status === "fulfilled") {
        try {
          if (mode === "evidence-graph") {
            const demoErrors = admittedProfile
              ? validateEcgiDemo(
                demoResponse.value.payload,
                demoResponse.value.headers,
                admittedProfile,
              )
              : ["The admitted evidence-graph profile is unavailable for demo binding."];
            if (demoErrors.length) {
              throw new Error(
                `The evidence-graph demo failed closed:\n${demoErrors.join("\n")}`,
              );
            }
          } else if (mode === "longitudinal-gbm-kinase-transition") {
            const demoErrors = admittedProfile
              ? validateKinaseTransitionDemo(
                demoResponse.value.payload,
                demoResponse.value.headers,
                admittedProfile,
              )
              : ["The admitted kinase-transition profile is unavailable for demo binding."];
            if (demoErrors.length) throw new Error(`The kinase-transition demo failed closed:\n${demoErrors.join("\n")}`);
          } else if (mode === "longitudinal-gbm-reactome-transition") {
            const demoErrors = validateReactomeTransitionDemo(
              demoResponse.value.payload,
              demoResponse.value.headers,
              admittedProfile,
            );
            if (demoErrors.length) {
              throw new Error(
                `The Reactome-transition demo failed closed:\n${demoErrors.join("\n")}`,
              );
            }
          } else if (mode === "longitudinal-gbm-neftel-transition") {
            const demoErrors = neftelTransitionDemoAdmissionErrors(
              demoResponse.value.payload,
              demoResponse.value.headers,
              admittedProfile,
            );
            if (demoErrors.length) {
              throw new Error(
                `The Neftel-transition demo failed closed:\n${demoErrors.join("\n")}`,
              );
            }
          } else if (mode === "gbm-factor-graph") {
            const demoErrors = admittedProfile
              ? validateFactorGraphDemo(
                demoResponse.value.payload,
                demoResponse.value.headers,
                admittedProfile,
              )
              : ["The admitted factor-graph profile is unavailable for demo binding."];
            if (demoErrors.length) {
              throw new Error(
                `The factor-graph demo failed closed:\n${demoErrors.join("\n")}`,
              );
            }
          }
          setEditor(pretty(demoResponse.value.payload));
          setMessage(LANE_COPY[mode].demoLoaded);
        } catch (demoError) {
          setError(
            demoError instanceof Error
              ? demoError.message
              : "The demo could not be loaded.",
          );
          setMessage("Paste a research request or retry when the backend is ready.");
        }
      } else {
        setError(demoResponse.reason instanceof Error ? demoResponse.reason.message : "The demo could not be loaded.");
        setMessage("Paste a research request or retry when the backend is ready.");
      }
      setLoadingDemo(false);
    }
    void initialize();
    return () => {
      active = false;
      runController.current?.abort();
      verifyController.current?.abort();
      analysisGeneration.current += 1;
      verificationGeneration.current += 1;
      receiptGeneration.current += 1;
    };
  }, [lane.apiBase, lane.requestLimitBytes, lane.resultLimitBytes, mode]);

  useEffect(() => {
    void probeService("/livez", setLive);
    void probeService("/readyz", setReady);
    const timer = window.setInterval(() => {
      void probeService("/livez", setLive);
      void probeService("/readyz", setReady);
    }, 30_000);
    return () => {
      window.clearInterval(timer);
      probeControllers.current["/livez"]?.abort();
      probeControllers.current["/readyz"]?.abort();
      probeGenerations.current["/livez"] += 1;
      probeGenerations.current["/readyz"] += 1;
    };
  }, [probeService]);

  const parsedEditor = useMemo(() => {
    try { return parseJsonObject(editor); } catch { return null; }
  }, [editor]);
  const graphStats = parsedEditor ? requestStats(parsedEditor) : { nodes: 0, edges: 0, observations: 0 };
  const gbmStats = parsedEditor ? gbmRequestStats(parsedEditor) : { measurements: 0, observed: 0, signatures: 7 };
  const neftelStats = parsedEditor ? neftelRequestStats(parsedEditor) : { observations: 0, active: 0, programs: 13 };
  const masterKinaseStats = parsedEditor ? masterKinaseRequestStats(parsedEditor) : { observations: 0, active: 0, phosphosites: 0, signatures: 24 };
  const functionalProteotypeStats = parsedEditor ? functionalProteotypeRequestStats(parsedEditor) : { observations: 0, active: 0, observed: 0, leftCensored: 0, genes: 0, axes: 4 };
  const gbmRnaPurityStats = parsedEditor ? gbmRnaPurityRequestStats(parsedEditor) : { suppliedGenes: 0, uniqueGenes: 0, nonzeroGenes: 0, totalRawCount: 0 };
  const longitudinalStats = parsedEditor ? longitudinalRequestStats(parsedEditor) : { timePoints: 0, observations: 0, active: 0, genes: 0 };
  const longitudinalPhosphoStats = parsedEditor ? longitudinalPhosphoRequestStats(parsedEditor) : { timePoints: 0, observations: 0, active: 0, phosphosites: 0 };
  const kinaseTransitionStats = parsedEditor ? kinaseTransitionRequestStats(parsedEditor) : { timePoints: 0, transitions: 0, observations: 0, active: 0, phosphosites: 0 };
  const reactomeTransitionStats = parsedEditor ? reactomeTransitionRequestStats(parsedEditor) : { timePoints: 0, transitions: 0, observations: 0, active: 0, genes: 0 };
  const neftelTransitionStats = parsedEditor ? neftelTransitionRequestStats(parsedEditor) : { timePoints: 0, transitions: 0, observations: 0, active: 0, genes: 0 };
  const complexTransitionStats = parsedEditor ? complexTransitionRequestStats(parsedEditor) : { timePoints: 0, transitions: 0, observations: 0, active: 0, genes: 0 };
  const factorGraphStats = parsedEditor ? factorGraphRequestStats(parsedEditor) : { reactomeTimePoints: 0, reactomeActive: 0, kinaseTimePoints: 0, kinaseActive: 0, childTransitions: 0 };
  const states = useMemo(() => mode === "evidence-graph" && result ? normalizeStates(result) : [], [mode, result]);
  const ablations = useMemo(() => result ? normalizeAblations(result, states) : [], [result, states]);
  const stateGroups = useMemo(() => Object.fromEntries(KIND_ORDER.map((kind) => [kind, states.filter((state) => state.kind === kind)])) as Record<StateKind, NormalizedState[]>, [states]);
  const gbmSignatures = useMemo(() => mode === "gbm-proteomic-axes" && result ? normalizeGbmSignatures(result) : [], [mode, result]);
  const neftelPrograms = useMemo(() => mode === "neftel-programs" && result ? normalizeNeftelPrograms(result) : [], [mode, result]);
  const masterKinases = useMemo(() => mode === "gbm-master-kinases" && result ? normalizeMasterKinases(result) : [], [mode, result]);
  const masterKinaseSubtypes = useMemo(() => mode === "gbm-master-kinases" && result ? normalizeMasterKinaseSubtypes(result) : [], [mode, result]);
  const functionalProteotypeAxes = useMemo(() => mode === "gbm-functional-proteotype" && result ? normalizeFunctionalProteotypeAxes(result) : [], [mode, result]);
  const gbmRnaPurityEvidence = useMemo(() => mode === "gbm-rna-purity" && result ? normalizeGbmRnaPurityResult(result) : null, [mode, result]);
  const longitudinalTransitions = useMemo(() => mode === "longitudinal-gbm" && result ? normalizeLongitudinalTransitions(result) : [], [mode, result]);
  const peltAnalysis = useMemo(() => mode === "longitudinal-gbm" && result ? normalizePeltAnalysis(result) : null, [mode, result]);
  const longitudinalPhosphoTransitions = useMemo(() => mode === "longitudinal-gbm-phospho" && result ? normalizeLongitudinalPhosphoTransitions(result) : [], [mode, result]);
  const kinaseTransitions = useMemo(() => mode === "longitudinal-gbm-kinase-transition" && result ? normalizeKinaseTransitions(result) : [], [mode, result]);
  const reactomeTransitions = useMemo(() => mode === "longitudinal-gbm-reactome-transition" && result ? normalizeReactomeTransitions(result) : [], [mode, result]);
  const reactomeEvaluation = useMemo(() => mode === "longitudinal-gbm-reactome-transition" ? normalizeReactomeEvaluation(profile) : null, [mode, profile]);
  const neftelTransitions = useMemo(() => mode === "longitudinal-gbm-neftel-transition" && result ? normalizeNeftelTransitions(result) : [], [mode, result]);
  const neftelTransitionEvaluation = useMemo(() => mode === "longitudinal-gbm-neftel-transition" ? normalizeNeftelTransitionEvaluation(profile) : null, [mode, profile]);
  const complexTransitions = useMemo(() => mode === "longitudinal-gbm-complex-transition" && result ? normalizeComplexTransitions(result) : [], [mode, result]);
  const complexEvaluation = useMemo(() => mode === "longitudinal-gbm-complex-transition" ? normalizeComplexEvaluation(profile) : null, [mode, profile]);
  const factorGraphResult = useMemo(() => mode === "gbm-factor-graph" && result ? normalizeFactorGraphResult(result) : null, [mode, result]);
  const factorGraphTopology = useMemo(() => mode === "gbm-factor-graph" ? normalizeFactorGraphTopology(profile) : null, [mode, profile]);

  const profileId = profile ? textAt(profile, ["profile_id", "algorithm_id"], lane.defaultProfileId) : lane.defaultProfileId;
  const profileDigest = profile ? textAt(profile, ["profile_digest", "digest"]) : "";
  const profileConstants = profile ? objectAt(profile, ["constants"]) : null;
  const profileLimits = profile ? objectAt(profile, ["limits"]) : null;
  const profileCounts = profile ? objectAt(profile, ["counts"]) : null;
  const maximumBootstrapReplicates = mode === "longitudinal-gbm-phospho"
    ? (profileConstants ? numberAt(profileConstants, ["maximum_bootstrap_replicates"]) ?? 64 : 64)
    : (profileLimits ? numberAt(profileLimits, ["max_bootstrap_replicates"]) ?? 256 : 256);
  const requestDigest = result ? textAt(result, ["request_digest"]) : "";
  const resultDigest = result ? textAt(result, ["result_digest"]) : "";
  const solver = result ? objectAt(result, ["solver", "convergence_diagnostics", "diagnostics"]) : null;
  const secondPass = solver ? objectAt(solver, ["second_pass", "final_pass"]) : null;
  const converged = secondPass?.converged ?? solver?.converged;
  const kinophos = result ? (result.external_kinase_comparison ?? result.kinophos_comparison ?? null) : null;
  const provenance = result ? (result.provenance ?? null) : null;
  const limitations = result ? arrayAt(result, ["limitations"]) : [];
  const gbmEvidence = result ? objectAt(result, ["evidence"]) : null;
  const gbmNormalization = result ? objectAt(result, ["normalization"]) : null;
  const visualizedRequest = result && request ? request : parsedEditor;
  const observedEvidence = visualizedRequest ? arrayAt(visualizedRequest, ["observations", "evidence"]) : [];
  const topologyProvenance = visualizedRequest ? objectAt(visualizedRequest, ["topology_provenance"]) : null;
  const supportedCount = states.filter((state) => state.estimate !== null && state.support.toLowerCase() === "supported" && !state.abstentionReason).length;
  const estimatedStateCount = states.filter((state) => state.estimate !== null && !["abstained", "unsupported"].includes(state.support.toLowerCase()) && !state.abstentionReason).length;
  const limitedStateCount = states.filter((state) => state.estimate !== null && state.support.toLowerCase() === "limited" && !state.abstentionReason).length;
  const supportedSignatureCount = gbmSignatures.filter((signature) => signature.support === "supported").length;
  const estimatedSignatureCount = gbmSignatures.filter((signature) => signature.score !== null).length;
  const supportedProgramCount = neftelPrograms.filter((program) => program.support === "supported").length;
  const estimatedProgramCount = neftelPrograms.filter((program) => program.locationScore !== null || program.rankScore !== null).length;
  const supportedMasterKinaseCount = masterKinases.filter((kinase) => kinase.support === "supported").length;
  const estimatedMasterKinaseCount = masterKinases.filter((kinase) => kinase.locationScore !== null || kinase.rankScore !== null).length;
  const supportedFunctionalProteotypeCount = functionalProteotypeAxes.filter((axis) => axis.support === "supported").length;
  const estimatedFunctionalProteotypeCount = functionalProteotypeAxes.filter((axis) => axis.estimate !== null).length;
  const supportedTransitionCount = longitudinalTransitions.filter((transition) => transition.support === "supported").length;
  const estimatedTransitionCount = longitudinalTransitions.filter((transition) => transition.score !== null).length;
  const supportedPhosphoTransitionCount = longitudinalPhosphoTransitions.filter((transition) => transition.support === "supported").length;
  const estimatedPhosphoTransitionCount = longitudinalPhosphoTransitions.filter((transition) => transition.score !== null).length;
  const estimatedKinaseTransitionCount = kinaseTransitionEstimatedCount(kinaseTransitions);
  const totalKinaseTransitionSignatureCount = kinaseTransitionSignatureCount(kinaseTransitions);
  const supportedReactomePathwayCount = reactomeSupportedPathwayCount(reactomeTransitions);
  const estimatedReactomePathwayCount = reactomeEstimatedPathwayCount(reactomeTransitions);
  const totalReactomePathwayCount = reactomePathwayCount(reactomeTransitions);
  const supportedNeftelTransitionProgramCount = neftelTransitionSupportedProgramCount(neftelTransitions);
  const estimatedNeftelTransitionProgramCount = neftelTransitionEstimatedProgramCount(neftelTransitions);
  const totalNeftelTransitionProgramCount = neftelTransitionProgramCount(neftelTransitions);
  const supportedComplexCount = complexSupportedCount(complexTransitions);
  const estimatedComplexCount = complexEstimatedCount(complexTransitions);
  const totalComplexCount = complexResultCount(complexTransitions);
  const longTimeout = usesSeriesTimeout(mode);
  const requestReceiptId = request
    ? textAt(request, [copy.receiptKey], "request")
    : "request";
  const resultReceiptId = result
    ? textAt(result, [copy.receiptKey], "result")
    : "result";
  const complexBottlenecks = useMemo<ComplexBottleneck[]>(() => {
    if (!visualizedRequest) return [];
    const stateById = new Map(states.map((state) => [state.id, state]));
    const edges = arrayAt(visualizedRequest, ["edges", "relations"]);
    return stateGroups.complex.map((complex) => {
      const members = edges.flatMap((edge) => {
        if (!isJsonObject(edge) || textAt(edge, ["kind", "relation_type", "type"]) !== "member_of" || textAt(edge, ["target_id", "target"]) !== complex.id) return [];
        const member = stateById.get(textAt(edge, ["source_id", "source"]));
        return member ? [{ member, essential: edge.essential === true }] : [];
      });
      const constrained = members.some((item) => item.essential) ? members.filter((item) => item.essential) : members;
      const bottleneck = [...constrained].sort((left, right) => (left.member.estimate ?? Number.POSITIVE_INFINITY) - (right.member.estimate ?? Number.POSITIVE_INFINITY))[0];
      return {
        complex,
        member: bottleneck?.member ?? null,
        essential: bottleneck?.essential ?? false,
        memberCount: members.length,
        gap: bottleneck?.member.estimate !== null && complex.estimate !== null ? bottleneck.member.estimate - complex.estimate : null,
      };
    });
  }, [stateGroups.complex, states, visualizedRequest]);

  function switchMode(nextMode: WorkbenchMode): void {
    if (nextMode === mode) return;
    runController.current?.abort();
    verifyController.current?.abort();
    analysisGeneration.current += 1;
    verificationGeneration.current += 1;
    receiptGeneration.current += 1;
    setRunning(false);
    setVerifying(false);
    setRequest(null);
    setResult(null);
    setVerification(null);
    setProfile(null);
    setLoadingDemo(true);
    setEditor("{}");
    setError("");
    setMessage("Loading the selected research lane…");
    setView("results");
    setMode(nextMode);
  }

  function validate(): JsonObject | null {
    setError("");
    try {
      if (new Blob([editor]).size > lane.requestLimitBytes) throw new Error(`The request exceeds the ${lane.requestLimitBytes / MIB} MiB transport limit.`);
      const parsed = parseJsonObject(editor);
      const errors = validateModeRequest(mode, parsed);
      if (errors.length) throw new Error(errors.join("\n"));
      if (mode === "evidence-graph") {
        const currentStats = requestStats(parsed);
        setMessage(`Valid research request · ${currentStats.nodes} nodes · ${currentStats.observations} observations.`);
      } else if (mode === "gbm-proteomic-axes") {
        const currentStats = gbmRequestStats(parsed);
        setMessage(`Valid GBM model request · ${currentStats.observed} observed LFQ proteins · ${currentStats.signatures} signatures.`);
      } else if (mode === "neftel-programs") {
        const currentStats = neftelRequestStats(parsed);
        setMessage(`Valid Neftel program request · ${currentStats.active} active protein observations · ${currentStats.programs} program outputs.`);
      } else if (mode === "gbm-master-kinases") {
        const currentStats = masterKinaseRequestStats(parsed);
        setMessage(`Valid master-kinase request · ${currentStats.active} active phosphosites · ${currentStats.signatures} pinned signatures.`);
      } else if (mode === "gbm-functional-proteotype") {
        const currentStats = functionalProteotypeRequestStats(parsed);
        setMessage(`Valid functional-proteotype request · ${currentStats.active} active proteins · ${currentStats.axes} constrained source axes.`);
      } else if (mode === "gbm-rna-purity") {
        const currentStats = gbmRnaPurityRequestStats(parsed);
        setMessage(`Valid GBMPurity request · ${currentStats.suppliedGenes.toLocaleString("en-US")} unique raw-count genes · ${currentStats.nonzeroGenes.toLocaleString("en-US")} nonzero.`);
      } else if (mode === "longitudinal-gbm") {
        const currentStats = longitudinalRequestStats(parsed);
        setMessage(`Valid longitudinal GBM request · ${currentStats.timePoints} ordered time points · ${currentStats.active} active protein observations.`);
      } else if (mode === "longitudinal-gbm-phospho") {
        const currentStats = longitudinalPhosphoRequestStats(parsed);
        setMessage(`Valid longitudinal phosphosite request · ${currentStats.timePoints} ordered time points · ${currentStats.active} active phosphosite observations.`);
      } else if (mode === "longitudinal-gbm-kinase-transition") {
        const currentStats = kinaseTransitionRequestStats(parsed);
        setMessage(`Valid SPHINKS signature-transition request · ${currentStats.timePoints} ordered time points · ${currentStats.active} active phosphosite observations · 24 fixed hypotheses.`);
      } else if (mode === "longitudinal-gbm-reactome-transition") {
        const currentStats = reactomeTransitionRequestStats(parsed);
        setMessage(`Valid Reactome transition request · ${currentStats.timePoints} ordered time points · ${currentStats.active} active protein observations · 10 fixed pathways.`);
      } else if (mode === "longitudinal-gbm-neftel-transition") {
        const currentStats = neftelTransitionRequestStats(parsed);
        setMessage(`Valid Neftel program-transition request · ${currentStats.timePoints} ordered time points · ${currentStats.active} active protein observations · 8 exact programs · LIMITED fitted dictionary.`);
      } else if (mode === "longitudinal-gbm-complex-transition") {
        const currentStats = complexTransitionRequestStats(parsed);
        setMessage(`Valid Reactome complex-transition request · ${currentStats.timePoints} ordered time points · ${currentStats.active} active protein observations · 28 fixed participant sets.`);
      } else if (mode === "gbm-factor-graph") {
        const currentStats = factorGraphRequestStats(parsed);
        setMessage(`Valid factor-graph composition · ${currentStats.reactomeTimePoints} protein points · ${currentStats.kinaseTimePoints} phosphosite points · ${currentStats.childTransitions} independent child transitions · 0 fusion edges.`);
      } else {
        assertNever(mode);
      }
      return parsed;
    } catch (validationError) {
      setError(validationError instanceof Error ? validationError.message : "The request is invalid.");
      setMessage("Resolve validation issues before analysis.");
      return null;
    }
  }

  async function analyze() {
    const parsed = validate();
    if (!parsed) return;
    verifyController.current?.abort();
    verificationGeneration.current += 1;
    setVerifying(false);
    runController.current?.abort();
    const controller = new AbortController();
    const generation = analysisGeneration.current + 1;
    const timeoutMs = longTimeout ? LONGITUDINAL_TIMEOUT_MS : ANALYSIS_TIMEOUT_MS;
    analysisGeneration.current = generation;
    receiptGeneration.current += 1;
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    runController.current = controller;
    setRunning(true);
    setResult(null);
    setVerification(null);
    setRequest(parsed);
    setMessage(copy.running);
    try {
      const response = await fetch(`${lane.apiBase}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed),
        cache: "no-store",
        signal: controller.signal,
      });
      const payload = await readBoundedJsonObject(response, lane.resultLimitBytes);
      if (generation !== analysisGeneration.current || controller.signal.aborted) return;
      if (mode === "evidence-graph") {
        const resultErrors = [
          ...validateEcgiResult(payload),
          ...validateEcgiResultRequestBinding(payload, parsed),
          ...validateEcgiResultHeaders(response.headers, payload),
          ...(profile
            ? validateEcgiResultProfileBinding(payload, profile)
            : ["The admitted evidence-graph profile is unavailable."]),
        ];
        if (resultErrors.length) throw new Error(`The evidence-graph result failed closed:\n${resultErrors.join("\n")}`);
      } else if (mode === "longitudinal-gbm-kinase-transition") {
        const resultErrors = [
          ...validateKinaseTransitionResult(payload),
          ...validateKinaseTransitionResultRequestBinding(payload, parsed),
          ...validateKinaseTransitionResultHeaders(response.headers, payload, parsed, profile ?? {}),
          ...(profile
            ? validateKinaseTransitionResultProfileBinding(payload, profile)
            : ["The admitted kinase-transition profile is unavailable."]),
        ];
        if (resultErrors.length) throw new Error(`The kinase-transition result failed closed:\n${resultErrors.join("\n")}`);
      } else if (mode === "longitudinal-gbm-reactome-transition") {
        const resultErrors = [
          ...validateReactomeTransitionResult(payload),
          ...validateReactomeTransitionResultRequestBinding(payload, parsed),
          ...validateReactomeTransitionResultHeaders(response.headers, payload, parsed),
          ...(profile
            ? validateReactomeTransitionResultProfileBinding(payload, profile)
            : ["The admitted Reactome-transition profile is unavailable."]),
        ];
        if (resultErrors.length) throw new Error(`The Reactome-transition result failed closed:\n${resultErrors.join("\n")}`);
      } else if (mode === "gbm-factor-graph") {
        const resultErrors = [
          ...validateFactorGraphResult(payload),
          ...validateFactorGraphResultRequestBinding(payload, parsed),
          ...validateFactorGraphResultHeaders(response.headers, payload, parsed, profile ?? {}),
          ...(profile
            ? validateFactorGraphResultProfileBinding(payload, profile)
            : ["The admitted factor-graph profile is unavailable."]),
        ];
        if (resultErrors.length) throw new Error(`The factor-graph result failed closed:\n${resultErrors.join("\n")}`);
      } else if (mode === "longitudinal-gbm-neftel-transition") {
        const resultErrors = [
          ...validateNeftelTransitionResult(payload),
          ...validateNeftelTransitionResultRequestBinding(payload, parsed),
          ...validateNeftelTransitionResultHeaders(response.headers, payload),
          ...(profile
            ? validateNeftelTransitionResultProfileBinding(payload, profile)
            : ["The admitted Neftel-transition profile is unavailable."]),
        ];
        if (resultErrors.length) throw new Error(`The Neftel-transition result failed closed:\n${resultErrors.join("\n")}`);
      } else if (mode === "longitudinal-gbm-complex-transition") {
        const resultErrors = [
          ...validateComplexTransitionResult(payload),
          ...validateComplexTransitionResultRequestBinding(payload, parsed),
          ...validateComplexTransitionResultHeaders(response.headers, payload),
          ...(profile
            ? validateComplexTransitionResultProfileBinding(payload, profile)
            : ["The admitted complex-transition profile is unavailable."]),
        ];
        if (resultErrors.length) throw new Error(`The complex-transition result failed closed:\n${resultErrors.join("\n")}`);
      }
      setResult(payload);
      setMessage(copy.complete);
      setView("results");
    } catch (runError) {
      if (generation !== analysisGeneration.current) return;
      if (isAbortError(runError)) {
        setMessage(timedOut
          ? `Analysis timed out after ${timeoutMs / 1_000} seconds. No request or result was persisted.`
          : "Analysis cancelled. No request or result was persisted.");
      } else {
        setError(runError instanceof Error ? runError.message : "Analysis failed.");
        setMessage("The backend rejected or could not complete this analysis.");
      }
    } finally {
      window.clearTimeout(timeout);
      if (generation === analysisGeneration.current) {
        if (runController.current === controller) runController.current = null;
        setRunning(false);
      }
    }
  }

  async function verifyReplay() {
    if (!request || !result) return;
    const envelope = { request, result };
    const body = JSON.stringify(envelope);
    if (new Blob([body]).size > lane.replayLimitBytes) {
      setError(`The replay envelope exceeds the ${lane.replayLimitBytes / MIB} MiB transport limit.`);
      return;
    }
    verifyController.current?.abort();
    const controller = new AbortController();
    const generation = verificationGeneration.current + 1;
    const boundReceiptGeneration = receiptGeneration.current;
    const timeoutMs = longTimeout ? LONGITUDINAL_TIMEOUT_MS : VERIFICATION_TIMEOUT_MS;
    verificationGeneration.current = generation;
    verifyController.current = controller;
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    setVerifying(true);
    setError("");
    try {
      const response = await fetch(`${lane.apiBase}/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        cache: "no-store",
        signal: controller.signal,
      });
      const payload = await readBoundedJsonObject(response, lane.resultLimitBytes);
      if (
        generation !== verificationGeneration.current ||
        boundReceiptGeneration !== receiptGeneration.current ||
        controller.signal.aborted
      ) return;
      if (mode === "evidence-graph") {
        const verificationErrors = profile
          ? [
            ...validateEcgiVerification(payload, result, request, profile),
            ...validateEcgiVerificationHeaders(response.headers, payload, profile),
          ]
          : ["The admitted evidence-graph profile is unavailable."];
        if (verificationErrors.length) throw new Error(`The evidence-graph replay response failed closed:\n${verificationErrors.join("\n")}`);
      } else if (mode === "longitudinal-gbm-kinase-transition") {
        const verificationErrors = profile
          ? [
            ...validateKinaseTransitionVerification(payload, result, profile),
            ...validateKinaseTransitionVerificationHeaders(response.headers, payload, profile),
          ]
          : ["The admitted kinase-transition profile is unavailable."];
        if (verificationErrors.length) throw new Error(`The kinase-transition replay response failed closed:\n${verificationErrors.join("\n")}`);
      } else if (mode === "longitudinal-gbm-reactome-transition") {
        const verificationErrors = profile
          ? [
            ...validateReactomeTransitionVerification(payload, result, profile),
            ...validateReactomeTransitionVerificationHeaders(response.headers, payload, profile),
          ]
          : ["The admitted Reactome-transition profile is unavailable."];
        if (verificationErrors.length) throw new Error(`The Reactome-transition replay response failed closed:\n${verificationErrors.join("\n")}`);
      } else if (mode === "longitudinal-gbm-complex-transition") {
        const verificationErrors = profile
          ? [
            ...validateComplexTransitionVerification(payload, result, profile),
            ...validateComplexTransitionVerificationHeaders(response.headers, payload),
          ]
          : ["The admitted complex-transition profile is unavailable."];
        if (verificationErrors.length) throw new Error(`The complex-transition replay response failed closed:\n${verificationErrors.join("\n")}`);
      } else if (mode === "longitudinal-gbm-neftel-transition") {
        const verificationErrors = profile
          ? [
            ...validateNeftelTransitionVerification(payload, result),
            ...validateNeftelTransitionVerificationHeaders(response.headers, payload, profile),
          ]
          : ["The admitted Neftel-transition profile is unavailable."];
        if (verificationErrors.length) throw new Error(`The Neftel-transition replay response failed closed:\n${verificationErrors.join("\n")}`);
      } else if (mode === "gbm-factor-graph") {
        const verificationErrors = profile
          ? [
            ...validateFactorGraphVerification(payload, result, profile),
            ...validateFactorGraphVerificationHeaders(response.headers, payload, profile),
          ]
          : ["The admitted factor-graph profile is unavailable."];
        if (verificationErrors.length) throw new Error(`The factor-graph replay response failed closed:\n${verificationErrors.join("\n")}`);
      }
      setVerification(payload);
      setMessage(payload.verified === true ? copy.replayVerified : "Replay completed with one or more mismatches.");
      setView("audit");
    } catch (verifyError) {
      if (
        generation !== verificationGeneration.current ||
        boundReceiptGeneration !== receiptGeneration.current
      ) return;
      if (isAbortError(verifyError)) {
        setMessage(timedOut ? `Replay verification timed out after ${timeoutMs / 1_000} seconds.` : "Replay verification cancelled.");
      } else {
        setError(verifyError instanceof Error ? verifyError.message : "Replay verification failed.");
      }
    } finally {
      window.clearTimeout(timeout);
      if (generation === verificationGeneration.current) {
        if (verifyController.current === controller) verifyController.current = null;
        setVerifying(false);
      }
    }
  }

  function cancelVerification() {
    verifyController.current?.abort();
  }

  async function reloadDemo() {
    runController.current?.abort();
    verifyController.current?.abort();
    analysisGeneration.current += 1;
    verificationGeneration.current += 1;
    receiptGeneration.current += 1;
    setRunning(false);
    setVerifying(false);
    setLoadingDemo(true);
    setError("");
    try {
      const response = await fetch(`${lane.apiBase}/demo`, { cache: "no-store" });
      const payload = await readBoundedJsonObject(response, lane.requestLimitBytes);
      if (mode === "evidence-graph") {
        const demoErrors = profile
          ? validateEcgiDemo(payload, response.headers, profile)
          : ["The admitted evidence-graph profile is unavailable for demo binding."];
        if (demoErrors.length) {
          throw new Error(
            `The evidence-graph demo failed closed:\n${demoErrors.join("\n")}`,
          );
        }
      } else if (mode === "longitudinal-gbm-kinase-transition") {
        const demoErrors = profile
          ? validateKinaseTransitionDemo(payload, response.headers, profile)
          : ["The admitted kinase-transition profile is unavailable for demo binding."];
        if (demoErrors.length) throw new Error(`The kinase-transition demo failed closed:\n${demoErrors.join("\n")}`);
      } else if (mode === "longitudinal-gbm-reactome-transition") {
        const demoErrors = validateReactomeTransitionDemo(
          payload,
          response.headers,
          profile,
        );
        if (demoErrors.length) {
          throw new Error(
            `The Reactome-transition demo failed closed:\n${demoErrors.join("\n")}`,
          );
        }
      } else if (mode === "longitudinal-gbm-neftel-transition") {
        const demoErrors = neftelTransitionDemoAdmissionErrors(
          payload,
          response.headers,
          profile,
        );
        if (demoErrors.length) {
          throw new Error(
            `The Neftel-transition demo failed closed:\n${demoErrors.join("\n")}`,
          );
        }
      } else if (mode === "gbm-factor-graph") {
        const demoErrors = profile
          ? validateFactorGraphDemo(payload, response.headers, profile)
          : ["The admitted factor-graph profile is unavailable for demo binding."];
        if (demoErrors.length) {
          throw new Error(
            `The factor-graph demo failed closed:\n${demoErrors.join("\n")}`,
          );
        }
      }
      setEditor(pretty(payload));
      setRequest(null);
      setResult(null);
      setVerification(null);
      setMessage(copy.reset);
    } catch (demoError) {
      setError(demoError instanceof Error ? demoError.message : "The demo could not be loaded.");
    } finally {
      setLoadingDemo(false);
    }
  }

  return (
    <main className="workbench-shell">
      <header className="workbench-nav">
        <a className="brand-lockup" href="/" aria-label="GLIO Proteogen research workbench">
          <div className="brand-mark">G</div>
          <div><p className="eyebrow">AURORA / RESEARCH SYSTEMS</p><h1>GLIO Proteogen</h1></div>
        </a>
        <nav className="workbench-links" aria-label="Primary navigation">
          <a className="active" href="/">Scientific workbench</a>
          <a href="/api-console">API console</a>
          <a href="/backend/docs" target="_blank" rel="noreferrer">OpenAPI ↗</a>
        </nav>
        <div className="probe-cluster">
          <ProbeBadge label="LIVE" probe={live} />
          <ProbeBadge label="READY" probe={ready} />
        </div>
      </header>

      <div className="lane-switcher" role="group" aria-label="Research model lane">
        <button
          aria-pressed={mode === "evidence-graph"}
          className={mode === "evidence-graph" ? "active" : ""}
          onClick={() => switchMode("evidence-graph")}
        >
          <span>01</span><b>Evidence graph</b><small>ECGI latent activity · kinase enrichment · ablations</small>
        </button>
        <button
          aria-pressed={mode === "gbm-proteomic-axes"}
          className={mode === "gbm-proteomic-axes" ? "active" : ""}
          onClick={() => switchMode("gbm-proteomic-axes")}
        >
          <span>02</span><b>GBM proteomic axes</b><small>Published XGBoost ensembles · seven glioblastoma signatures</small>
        </button>
        <button
          aria-pressed={mode === "neftel-programs"}
          className={mode === "neftel-programs" ? "active" : ""}
          onClick={() => switchMode("neftel-programs")}
        >
          <span>03</span><b>Neftel protein programs</b><small>Table S2 modules · robust location · rank enrichment</small>
        </button>
        <button
          aria-pressed={mode === "gbm-master-kinases"}
          className={mode === "gbm-master-kinases" ? "active" : ""}
          onClick={() => switchMode("gbm-master-kinases")}
        >
          <span>04</span><b>GBM master kinases</b><small>SPHINKS signatures · independent concordance · 24 kinases</small>
        </button>
        <button
          aria-pressed={mode === "gbm-functional-proteotype"}
          className={mode === "gbm-functional-proteotype" ? "active" : ""}
          onClick={() => switchMode("gbm-functional-proteotype")}
        >
          <span>05</span><b>GBM functional proteotype</b><small>Migliozzi Table 2d · constrained four-axis concordance</small>
        </button>
        <button
          aria-pressed={mode === "longitudinal-gbm"}
          className={mode === "longitudinal-gbm" ? "active" : ""}
          onClick={() => switchMode("longitudinal-gbm")}
        >
          <span>06</span><b>Longitudinal GBM</b><small>KNCC paired protein axis · covariance · rate PELT</small>
        </button>
        <button
          aria-pressed={mode === "longitudinal-gbm-phospho"}
          className={mode === "longitudinal-gbm-phospho" ? "active" : ""}
          onClick={() => switchMode("longitudinal-gbm-phospho")}
        >
          <span>07</span><b>Longitudinal phosphosites</b><small>PDC000515 fitted axis · exact refits · SPHINKS annotations</small>
        </button>
        <button
          aria-pressed={mode === "longitudinal-gbm-kinase-transition"}
          className={mode === "longitudinal-gbm-kinase-transition" ? "active" : ""}
          onClick={() => switchMode("longitudinal-gbm-kinase-transition")}
        >
          <span>08</span><b>GBM kinase transitions</b><small>24 SPHINKS hypotheses · patient refits · LIMITED concordance</small>
        </button>
        <button
          aria-pressed={mode === "gbm-rna-purity"}
          className={mode === "gbm-rna-purity" ? "active" : ""}
          onClick={() => switchMode("gbm-rna-purity")}
        >
          <span>08</span><b>GBM RNA purity</b><small>Published GBMPurity MLP · exact 5,829-gene forward pass</small>
        </button>
        <button
          aria-pressed={mode === "longitudinal-gbm-reactome-transition"}
          className={mode === "longitudinal-gbm-reactome-transition" ? "active" : ""}
          onClick={() => switchMode("longitudinal-gbm-reactome-transition")}
        >
          <span>09</span><b>GBM Reactome transitions</b><small>KNCC global-adjusted coordinates · 10 fixed Reactome pathways</small>
        </button>
        <button
          aria-pressed={mode === "longitudinal-gbm-neftel-transition"}
          className={mode === "longitudinal-gbm-neftel-transition" ? "active" : ""}
          onClick={() => switchMode("longitudinal-gbm-neftel-transition")}
        >
          <span>10</span><b>GBM Neftel transitions</b><small>8 exact Table S2 programs · fitted dictionary LIMITED vs equal membership</small>
        </button>
        <button
          aria-pressed={mode === "longitudinal-gbm-complex-transition"}
          className={mode === "longitudinal-gbm-complex-transition" ? "active" : ""}
          onClick={() => switchMode("longitudinal-gbm-complex-transition")}
        >
          <span>11</span><b>GBM complex transitions</b><small>104 paired patients · 28 Reactome participant sets · robust factors</small>
        </button>
        <button
          aria-pressed={mode === "gbm-factor-graph"}
          className={mode === "gbm-factor-graph" ? "active" : ""}
          onClick={() => switchMode("gbm-factor-graph")}
        >
          <span>12</span><b>KNCC factor graph</b><small>Two independent child blocks · 41 nodes · 39 annotation edges · no fusion</small>
        </button>
      </div>

      <section className="workbench-hero">
        <div>
          <p className="eyebrow accent">{copy.heroEyebrow}</p>
          <h2>{copy.heroLead}<br /><span>{copy.heroBoundary}</span></h2>
          <p className="workbench-intro">{copy.heroIntro}</p>
        </div>
        <aside className="profile-card">
          <div><span>ALGORITHM PROFILE</span><b>{profileId}</b></div>
          <dl>
            <div><dt>Profile digest</dt><dd>{shortDigest(profileDigest)}</dd></div>
            {mode === "gbm-rna-purity"
              ? <div><dt>Uncertainty</dt><dd>not available · single fitted model</dd></div>
              : mode === "gbm-factor-graph"
                ? <div><dt>Execution</dt><dd>2 independent children · deterministic sequence</dd></div>
                : <div><dt>Bootstrap</dt><dd>{parsedEditor ? numberAt(parsedEditor, ["bootstrap_replicates"]) ?? 64 : 64} / {maximumBootstrapReplicates} max</dd></div>}
            {mode === "evidence-graph" ? <>
              <div><dt>State threshold</dt><dd>±{formatNumber(profileConstants ? numberAt(profileConstants, ["activation_threshold"]) ?? 0.25 : 0.25, 2)}</dd></div>
              <div><dt>Graph cap</dt><dd>{profileLimits ? numberAt(profileLimits, ["max_nodes"]) ?? 256 : 256} nodes</dd></div>
            </> : mode === "gbm-proteomic-axes" ? <>
              <div><dt>Model family</dt><dd>{arrayAt(profile ?? {}, ["signatures"]).length || 7} × 600 trees</dd></div>
              <div><dt>Feature universe</dt><dd>3,025 proteins</dd></div>
            </> : mode === "neftel-programs" ? <>
              <div><dt>Program outputs</dt><dd>8 exact · 5 derived</dd></div>
              <div><dt>Rank threshold</dt><dd>q ≤ {formatNumber(profileConstants ? numberAt(profileConstants, ["rank_q_threshold"]) ?? 0.1 : 0.1, 2)}</dd></div>
            </> : mode === "gbm-master-kinases" ? <>
              <div><dt>Signature catalog</dt><dd>24 kinases · 4 source subtypes</dd></div>
              <div><dt>Rank threshold</dt><dd>q ≤ {formatNumber(profileConstants ? numberAt(profileConstants, ["rank_q_threshold"]) ?? 0.1 : 0.1, 2)}</dd></div>
            </> : mode === "gbm-functional-proteotype" ? <>
              <div><dt>Constraint</dt><dd>Σ z = 0 across four axes</dd></div>
              <div><dt>Source signatures</dt><dd>4 × 150 Table 2d proteins</dd></div>
              <div><dt>Rank threshold</dt><dd>q ≤ {formatNumber(profileConstants ? numberAt(profileConstants, ["rank_q_threshold"]) ?? 0.1 : 0.1, 2)}</dd></div>
            </> : mode === "gbm-rna-purity" ? <>
              <div><dt>Released network</dt><dd>5,829 → 32 → 16 → 1</dd></div>
              <div><dt>Coverage gate</dt><dd>80% minimum · 99% full support</dd></div>
              <div><dt>Intended context</dt><dd>primary IDH-wildtype GBM bulk RNA</dd></div>
            </> : mode === "longitudinal-gbm" ? <>
              <div><dt>Source transitions</dt><dd>{profileCounts ? numberAt(profileCounts, ["strict_paired_transition_count"]) ?? 104 : 104} strict pairs</dd></div>
              <div><dt>Frozen feature axis</dt><dd>{profileCounts ? numberAt(profileCounts, ["fitted_feature_count"]) ?? 0 : "—"} proteins</dd></div>
              <div><dt>Full-support floor</dt><dd>≥ {profileConstants ? numberAt(profileConstants, ["supported_minimum_bootstrap_replicates"]) ?? 64 : 64} bootstrap</dd></div>
              <div><dt>PELT time axis</dt><dd>rates / {profileConstants ? numberAt(profileConstants, ["pelt_rate_reference_days"]) ?? 90 : 90} days</dd></div>
            </> : mode === "longitudinal-gbm-phospho" ? <>
              <div><dt>Source transitions</dt><dd>{profileCounts ? numberAt(profileCounts, ["strict_pair_count"]) ?? 88 : 88} strict pairs</dd></div>
              <div><dt>Source inventory</dt><dd>{profileCounts ? numberAt(profileCounts, ["source_feature_count"]) ?? 24_015 : 24_015} site groups</dd></div>
              <div><dt>Release axis</dt><dd>{profileCounts ? numberAt(profileCounts, ["selected_feature_count"]) ?? 32 : 32} / {profileCounts ? numberAt(profileCounts, ["eligible_feature_count"]) ?? 4_225 : 4_225}</dd></div>
              <div><dt>Support ceiling</dt><dd>limited · source gates</dd></div>
            </> : mode === "longitudinal-gbm-kinase-transition" ? <>
              <div><dt>Source cohort</dt><dd>{profileCounts ? numberAt(profileCounts, ["strict_patient_pairs"]) ?? 88 : 88} strict pairs</dd></div>
              <div><dt>Hypothesis family</dt><dd>24 fixed kinases · 4 subtypes</dd></div>
              <div><dt>Selection stability</dt><dd>11 core · CHEK2 unstable</dd></div>
              <div><dt>Claim ceiling</dt><dd className="warn">LIMITED signature concordance only</dd></div>
            </> : mode === "longitudinal-gbm-reactome-transition" ? <>
              <div><dt>Source cohort</dt><dd>{profileCounts ? numberAt(profileCounts, ["source_patient_count"]) ?? 104 : 104} strict paired patients</dd></div>
              <div><dt>Fixed panel</dt><dd>{profileCounts ? numberAt(profileCounts, ["pathway_count"]) ?? 10 : 10} Reactome V97 pathways</dd></div>
              <div><dt>Conditional dictionary</dt><dd>1 global + 10 pathway coordinates</dd></div>
              <div><dt>Claim ceiling</dt><dd>same-cohort conditional concordance</dd></div>
            </> : mode === "longitudinal-gbm-neftel-transition" ? <>
              <div><dt>Source cohort</dt><dd>{profileCounts ? numberAt(profileCounts, ["source_patient_count"]) ?? 104 : 104} strict paired patients</dd></div>
              <div><dt>Exact programs</dt><dd>MES2 · MES1 · AC · OPC · NPC1 · NPC2 · G1/S · G2/M</dd></div>
              <div><dt>Fitted union</dt><dd>{profileCounts ? numberAt(profileCounts, ["fitted_union_feature_count"]) ?? 256 : 256} proteins</dd></div>
              <div><dt>Claim ceiling</dt><dd className="warn">LIMITED · loses to equal membership</dd></div>
            </> : mode === "longitudinal-gbm-complex-transition" ? <>
              <div><dt>Source cohort</dt><dd>{profileCounts ? numberAt(profileCounts, ["strict_patient_pair_count"]) ?? 104 : 104} strict paired patients</dd></div>
              <div><dt>Fixed panel</dt><dd>{profileCounts ? numberAt(profileCounts, ["complex_count"]) ?? 28 : 28} Reactome V97 participant sets</dd></div>
              <div><dt>Pilot domains</dt><dd>11 GBM signaling and stress families</dd></div>
              <div><dt>Claim ceiling</dt><dd>member-transition concordance only</dd></div>
            </> : mode === "gbm-factor-graph" ? <>
              <div><dt>Composition</dt><dd>{profileCounts ? numberAt(profileCounts, ["computation_blocks"]) ?? 2 : 2} independent blocks</dd></div>
              <div><dt>Factor inventory</dt><dd>{profileCounts ? numberAt(profileCounts, ["nodes"]) ?? 41 : 41} nodes · {profileCounts ? numberAt(profileCounts, ["annotation_only_containment_edges"]) ?? 39 : 39} annotations</dd></div>
              <div><dt>Cross-block numerics</dt><dd>0 edges · no fusion</dd></div>
              <div><dt>Claim ceiling</dt><dd>independent source-cohort coordinates only</dd></div>
            </> : null}
          </dl>
          <span className="research-boundary">RESEARCH USE ONLY · NON-PRESCRIPTIVE</span>
        </aside>
      </section>

      <section className="workbench-grid">
        <aside className="request-studio">
          <div className="studio-heading">
            <div><p className="eyebrow">01 / INPUT</p><h3>{copy.inputTitle}</h3></div>
            <button className="quiet-action" onClick={() => void reloadDemo()} disabled={loadingDemo || running || verifying}>{loadingDemo ? "Loading…" : "Reset demo"}</button>
          </div>
          <div className="request-stats">
            {mode === "evidence-graph" ? <>
              <span><b>{graphStats.nodes}</b> nodes</span><span><b>{graphStats.edges}</b> edges</span><span><b>{graphStats.observations}</b> observations</span>
            </> : mode === "gbm-proteomic-axes" ? <>
              <span><b>{gbmStats.measurements}</b> proteins</span><span><b>{gbmStats.observed}</b> observed</span><span><b>{gbmStats.signatures}</b> signatures</span>
            </> : mode === "neftel-programs" ? <>
              <span><b>{neftelStats.observations}</b> proteins</span><span><b>{neftelStats.active}</b> active</span><span><b>{neftelStats.programs}</b> programs</span>
            </> : mode === "gbm-master-kinases" ? <>
              <span><b>{masterKinaseStats.phosphosites}</b> phosphosites</span><span><b>{masterKinaseStats.active}</b> active</span><span><b>{masterKinaseStats.signatures}</b> signatures</span>
            </> : mode === "gbm-functional-proteotype" ? <>
              <span><b>{functionalProteotypeStats.genes}</b> proteins</span><span><b>{functionalProteotypeStats.active}</b> active</span><span><b>{functionalProteotypeStats.axes}</b> constrained axes</span>
            </> : mode === "gbm-rna-purity" ? <>
              <span><b>{gbmRnaPurityStats.suppliedGenes.toLocaleString("en-US")}</b> genes</span><span><b>{gbmRnaPurityStats.nonzeroGenes.toLocaleString("en-US")}</b> nonzero</span><span><b>5,829</b> model features</span>
            </> : mode === "longitudinal-gbm" ? <>
              <span><b>{longitudinalStats.timePoints}</b> time points</span><span><b>{longitudinalStats.genes}</b> genes</span><span><b>{longitudinalStats.active}</b> active</span>
            </> : mode === "longitudinal-gbm-phospho" ? <>
              <span><b>{longitudinalPhosphoStats.timePoints}</b> time points</span><span><b>{longitudinalPhosphoStats.phosphosites}</b> site groups</span><span><b>{longitudinalPhosphoStats.active}</b> active</span>
            </> : mode === "longitudinal-gbm-kinase-transition" ? <>
              <span><b>{kinaseTransitionStats.timePoints}</b> time points</span><span><b>{kinaseTransitionStats.phosphosites}</b> site groups</span><span><b>24</b> fixed hypotheses</span>
            </> : mode === "longitudinal-gbm-reactome-transition" ? <>
              <span><b>{reactomeTransitionStats.timePoints}</b> time points</span><span><b>{reactomeTransitionStats.genes}</b> genes</span><span><b>10</b> fixed pathways</span>
            </> : mode === "longitudinal-gbm-neftel-transition" ? <>
              <span><b>{neftelTransitionStats.timePoints}</b> time points</span><span><b>{neftelTransitionStats.genes}</b> genes</span><span><b>8</b> exact programs</span>
            </> : mode === "longitudinal-gbm-complex-transition" ? <>
              <span><b>{complexTransitionStats.timePoints}</b> time points</span><span><b>{complexTransitionStats.genes}</b> genes</span><span><b>28</b> participant sets</span>
            </> : mode === "gbm-factor-graph" ? <>
              <span><b>{factorGraphStats.reactomeTimePoints} + {factorGraphStats.kinaseTimePoints}</b> child points</span><span><b>{factorGraphStats.childTransitions}</b> transitions</span><span><b>0</b> fusion edges</span>
            </> : null}
          </div>
          <label className="json-editor">
            <span>STRUCTURED JSON · MAX {lane.requestLimitBytes / MIB} MiB</span>
            <textarea value={editor} onChange={(event) => { setEditor(event.target.value); setError(""); }} spellCheck={false} aria-label={lane.requestLabel} />
          </label>
          <div className="editor-actions">
            <button className="secondary-button" onClick={validate} disabled={running}>Validate</button>
            {running ? (
              <button className="danger-button" onClick={() => runController.current?.abort()}>Cancel run</button>
            ) : (
              <button
                className="primary-button"
                onClick={() => void analyze()}
                disabled={loadingDemo || ready.state !== "online"}
                title={ready.state === "online" ? undefined : "Backend readiness must be online to run."}
              >Run analysis <span>→</span></button>
            )}
          </div>
          <div className={`studio-message ${error ? "error" : ""}`} role={error ? "alert" : "status"}>
            <i />
            <span>{error || message}</span>
          </div>
          <div className="input-boundary">
            <p>{mode === "gbm-rna-purity" ? "Raw-count and context contract" : mode === "gbm-factor-graph" ? "Independent nested evidence contracts" : "Explicit evidence states"}</p>
            {mode === "gbm-rna-purity"
              ? <><span>raw counts</span><span>bulk RNA-seq</span><span>primary IDH-wildtype GBM</span><span>research only</span></>
              : <><span>observed</span><span>left_censored</span><span>missing</span><span>unsupported</span></>}
            {mode === "gbm-proteomic-axes" && <strong>Unmeasured model features follow the published numeric zero-fill convention; they are not negative observations.</strong>}
            {mode === "evidence-graph" && <strong>Every estimate is capped LIMITED because caller-curated and synthetic-abstraction graphs are not validated glioma models.</strong>}
            {mode === "neftel-programs" && <strong>Bulk-protein program evidence is not a cell fraction, tumor-cell assignment, diagnosis, or molecular subtype call.</strong>}
            {mode === "gbm-master-kinases" && <strong>This is an independent signature-concordance engine—not an exact SPHINKS port, calibrated kinase activity, or patient subtype classification.</strong>}
            {mode === "gbm-functional-proteotype" && <strong>GPM, MTC, NEU, and PPR are jointly constrained source-cohort concordance axes—not patient subtype labels, probabilities, winners, diagnoses, or treatment assignments. Table 2e pathways are context only and never sample pathway activity.</strong>}
            {mode === "gbm-rna-purity" && <strong>Only exact primary IDH-wildtype GBM bulk RNA-seq raw counts are in scope. The output is one published-model malignant-cell-fraction estimate—not histology, immune composition, diagnosis, prognosis, or treatment guidance.</strong>}
            {mode === "longitudinal-gbm" && <strong>Transition direction means source-cohort T2−T1 concordance—not patient evolution, recurrence prediction, prognosis, or treatment guidance.</strong>}
            {mode === "longitudinal-gbm-phospho" && <strong>Raw phosphosite concordance is not occupancy, kinase activity, protein/phosphosite fusion, recurrence prediction, or clinical guidance. Composite source site groups remain indivisible.</strong>}
            {mode === "longitudinal-gbm-kinase-transition" && <strong>These are same-assay SPHINKS signature-transition concordance coordinates—not kinase activity, biochemical activity, causal effects, independent validation, patient evolution, recurrence prediction, or clinical guidance. Every estimable output is LIMITED.</strong>}
            {mode === "longitudinal-gbm-reactome-transition" && <strong>Pathway outputs are global-adjusted KNCC source-cohort concordance coordinates—not pathway activity, flux, causal effects, patient evolution, recurrence prediction, or clinical guidance. PI3K/AKT is always overlap-confounded and LIMITED.</strong>}
            {mode === "longitudinal-gbm-neftel-transition" && <strong>All eight outputs are global-adjusted source-cohort bulk-protein program concordance only. The fitted dictionary loses to equal membership, every leave-program interval crosses zero, and no program is individually supported. This is not cell-state deconvolution, activation, evolution, outcome prediction, or clinical guidance.</strong>}
            {mode === "longitudinal-gbm-complex-transition" && <strong>Reactome participant membership supports robust member-transition concordance only. It does not establish physical assembly, biochemical activity, stoichiometry, essential subunits, causal effects, recurrence prediction, or clinical guidance.</strong>}
            {mode === "gbm-factor-graph" && <strong>This is a composition and presentation surface, not an additional fitted model. The two source-cohort children execute deterministically in sequence, remain assay-specific and semantically independent, and exchange no scores, evidence, uncertainty, or numerical edges.</strong>}
          </div>
        </aside>

        <section className="result-space">
          <div className="result-toolbar">
            <div>
              <p className="eyebrow">02 / INFERENCE</p>
              <h3>{result ? `${copy.receiptLabel} ${resultReceiptId}` : "Awaiting analysis"}</h3>
            </div>
            <div className="result-actions">
              {request && <button onClick={() => downloadJson(`${requestReceiptId}-request.json`, request)}>↓ Request</button>}
              {result && <button onClick={() => downloadJson(`${resultReceiptId}-receipt.json`, result)}>↓ Result</button>}
              {verifying ? (
                <button className="danger-button" onClick={cancelVerification}>Cancel verification</button>
              ) : (
                <button className="verify-button" onClick={() => void verifyReplay()} disabled={!result}>Verify replay</button>
              )}
            </div>
          </div>

          {result && (
            <div className="result-ledger">
              <div><span>REQUEST</span><code>{shortDigest(requestDigest)}</code></div>
              <div><span>RESULT</span><code>{shortDigest(resultDigest)}</code></div>
              {mode === "evidence-graph" ? <>
                <div><span>SOLVER</span><b className={converged === true ? "ok" : "warn"}>{converged === true ? "converged" : converged === false ? "not converged" : "reported"}</b></div>
                <div><span>SUPPORT</span><b>{supportedCount} full · {estimatedStateCount} estimated</b></div>
              </> : mode === "gbm-proteomic-axes" ? <>
                <div><span>MODEL</span><b className="ok">published port</b></div>
                <div><span>SUPPORT</span><b>{supportedSignatureCount} full · {estimatedSignatureCount} estimated</b></div>
              </> : mode === "neftel-programs" ? <>
                <div><span>METHODS</span><b className="ok">location + rank</b></div>
                <div><span>SUPPORT</span><b>{supportedProgramCount} full · {estimatedProgramCount} estimated</b></div>
              </> : mode === "gbm-master-kinases" ? <>
                <div><span>METHODS</span><b className="ok">independent concordance</b></div>
                <div><span>SUPPORT</span><b>{supportedMasterKinaseCount} full · {estimatedMasterKinaseCount} estimated</b></div>
              </> : mode === "gbm-functional-proteotype" ? <>
                <div><span>METHODS</span><b className={converged === true ? "ok" : "warn"}>constrained IRLS + rank</b></div>
                <div><span>SUPPORT</span><b>{supportedFunctionalProteotypeCount} full · {estimatedFunctionalProteotypeCount} estimated</b></div>
              </> : mode === "gbm-rna-purity" ? <>
                <div><span>MODEL</span><b className="ok">exact published MLP</b></div>
                <div><span>SUPPORT</span><b>{gbmRnaPurityEvidence?.support ?? "not parsed"} · {gbmRnaPurityEvidence ? `${formatNumber(gbmRnaPurityEvidence.coverage.coverageFraction * 100, 1)}% coverage` : "no coverage"}</b></div>
              </> : mode === "longitudinal-gbm" ? <>
                <div><span>METHODS</span><b className="ok">paired axis + PELT</b></div>
                <div><span>SUPPORT</span><b>{supportedTransitionCount} full · {estimatedTransitionCount} estimated</b></div>
              </> : mode === "longitudinal-gbm-phospho" ? <>
                <div><span>METHODS</span><b className="warn">raw phosphosite axis</b></div>
                <div><span>SUPPORT</span><b>{supportedPhosphoTransitionCount} full · {estimatedPhosphoTransitionCount} estimated</b></div>
              </> : mode === "longitudinal-gbm-kinase-transition" ? <>
                <div><span>RELEASE GATE</span><b className="warn">LIMITED · same-assay evidence</b></div>
                <div><span>SIGNATURES</span><b>0 full · {estimatedKinaseTransitionCount} estimated / {totalKinaseTransitionSignatureCount}</b></div>
              </> : mode === "longitudinal-gbm-reactome-transition" ? <>
                <div><span>METHODS</span><b className="ok">global-adjusted robust dictionary</b></div>
                <div><span>SUPPORT</span><b>{supportedReactomePathwayCount} full · {estimatedReactomePathwayCount} estimated / {totalReactomePathwayCount}</b></div>
              </> : mode === "longitudinal-gbm-neftel-transition" ? <>
                <div><span>RELEASE GATE</span><b className="warn">LIMITED · equal membership preferred</b></div>
                <div><span>SUPPORT</span><b>{supportedNeftelTransitionProgramCount} full · {estimatedNeftelTransitionProgramCount} estimated / {totalNeftelTransitionProgramCount}</b></div>
              </> : mode === "longitudinal-gbm-complex-transition" ? <>
                <div><span>METHODS</span><b className="ok">robust fitted member factors</b></div>
                <div><span>SUPPORT</span><b>{supportedComplexCount} full · {estimatedComplexCount} estimated / {totalComplexCount}</b></div>
              </> : mode === "gbm-factor-graph" ? <>
                <div><span>COMPOSITION</span><b className="ok">2 independent child receipts</b></div>
                <div><span>CROSS-BLOCK</span><b className="ok">0 numerical edges · no fusion</b></div>
              </> : null}
            </div>
          )}

          <div className="result-tabs" role="tablist" aria-label="Result views">
            {((mode === "evidence-graph" ? ["results", "network", "evidence", "audit"] : ["results", "evidence", "audit"]) as View[]).map((tab) => (
              <button key={tab} role="tab" aria-selected={view === tab} className={view === tab ? "active" : ""} onClick={() => setView(tab)}>{tab}</button>
            ))}
          </div>

          {!result && (
            <div className="awaiting-state">
              <div className="evidence-orbit"><i /><i /><i /><span>{copy.emptyMark}</span></div>
              <h3>{copy.emptyTitle}</h3>
              <p>{copy.emptyBody}</p>
              <div>{copy.emptyTags.map((tag) => <span key={tag}>{tag}</span>)}</div>
            </div>
          )}

          {mode === "evidence-graph" && result && view === "results" && (
            <div className="panel-stack">
              <div className="summary-grid">
                <article><span>FULL SUPPORT</span><b>{supportedCount}</b><small>{limitedStateCount} limited · {states.length - estimatedStateCount} abstained</small></article>
                <article><span>MEAN STABILITY</span><b>{formatNumber(states.length ? states.reduce((sum, state) => sum + (state.stability ?? 0), 0) / states.length : null)}</b><small>deterministic bootstrap</small></article>
                <article><span>KINASE SIGNALS</span><b>{stateGroups.kinase.filter((state) => state.qValue !== null && state.qValue <= 0.1).length}</b><small>q ≤ 0.10</small></article>
                <article><span>MAX DISCORDANCE</span><b>{formatNumber(states.reduce<number | null>((max, state) => state.discordance === null ? max : Math.max(max ?? state.discordance, state.discordance), null))}</b><small>evidence inconsistency</small></article>
              </div>
              <StateTable title="Protein & proteoform state" states={[...stateGroups.protein, ...stateGroups.proteoform, ...stateGroups.phosphosite]} empty="No molecular states were returned." />
              <StateTable title="Complex state & bottlenecks" states={stateGroups.complex} empty="No complex states were returned." />
              <StateTable title="Directed pathway state" states={stateGroups.pathway} empty="No pathway states were returned." />
              <div className="mechanism-grid">
                <section className="result-panel">
                  <div className="panel-title-row"><div><p className="eyebrow">ESSENTIAL-SUBUNIT CONSTRAINT</p><h3>Complex bottlenecks</h3></div><span className="count-chip">{complexBottlenecks.length}</span></div>
                  {complexBottlenecks.length === 0 ? <p className="panel-empty">No complex membership edges were available.</p> : <div className="mechanism-list">{complexBottlenecks.map((item) => <article key={item.complex.id}><div><b>{item.complex.label}</b><span>{item.memberCount} mapped members</span></div><strong>{item.member ? item.member.label : "unresolved"}</strong><small>{item.essential ? "essential bottleneck" : "lowest inferred member"} · activity {formatSigned(item.member?.estimate ?? null)} · gap {formatSigned(item.gap)}</small></article>)}</div>}
                </section>
                <section className="result-panel">
                  <div className="panel-title-row"><div><p className="eyebrow">DIRECTED GRAPH SUPPORT</p><h3>Pathway drivers</h3></div><span className="count-chip">{stateGroups.pathway.length}</span></div>
                  {stateGroups.pathway.length === 0 ? <p className="panel-empty">No pathway states were returned.</p> : <div className="mechanism-list">{stateGroups.pathway.map((state) => <article key={state.id}><div><b>{state.label}</b><StateBadge value={state.classification} /></div><strong>{state.drivers.slice(0, 3).join(" · ") || "No ranked driver"}</strong><small>discordance {formatNumber(state.discordance)} · stability {formatNumber(state.stability)}</small></article>)}</div>}
                </section>
              </div>
              <section className="result-panel state-panel">
                <div className="panel-title-row"><div><p className="eyebrow">EXPERIMENTAL INFERENCE</p><h3>Kinase rank enrichment</h3></div><span className="boundary-chip">never overrides KINOPHOS</span></div>
                {stateGroups.kinase.length === 0 ? <p className="panel-empty">No kinase estimates were supported.</p> : (
                  <div className="state-table-wrap"><table className="state-table kinase-table"><thead><tr><th>Kinase</th><th>Activity</th><th>Interval</th><th>Rank / enrichment</th><th>p / q</th><th>State</th><th>Substrates</th></tr></thead><tbody>
                    {stateGroups.kinase.map((state) => <tr key={state.id}><td><b>{state.label}</b></td><td className="mono-cell">{formatSigned(state.estimate)}</td><td className="mono-cell">[{formatNumber(state.lower)}, {formatNumber(state.upper)}]</td><td className="mono-cell">{formatNumber(numberAt(state.raw, ["rank_statistic"]))} / {formatNumber(numberAt(state.raw, ["enrichment_score"]))}</td><td className="mono-cell">{formatNumber(numberAt(state.raw, ["p_value"]), 4)} / {formatNumber(state.qValue, 4)}</td><td><StateBadge value={state.classification} /><small><span className={`support-badge ${state.support.toLowerCase()}`}>{state.support}</span></small></td><td>{numberAt(state.raw, ["mapped_substrates"]) ?? state.evidenceCount ?? "—"}{state.abstentionReason && <small className="warning-copy">{state.abstentionReason}</small>}</td></tr>)}
                  </tbody></table></div>
                )}
              </section>
            </div>
          )}

          {mode === "gbm-proteomic-axes" && result && view === "results" && (
            <div className="panel-stack">
              <div className="summary-grid">
                <article><span>FULL SUPPORT</span><b>{supportedSignatureCount} / {gbmSignatures.length}</b><small>{gbmSignatures.filter((signature) => signature.support === "limited").length} limited · {gbmSignatures.filter((signature) => signature.support === "abstained").length} abstained</small></article>
                <article><span>OBSERVED MODEL FEATURES</span><b>{gbmEvidence ? numberAt(gbmEvidence, ["observed_model_features"]) ?? 0 : 0}</b><small>of 3,025 published model inputs</small></article>
                <article><span>ZERO-FILL BURDEN</span><b>{gbmSignatures[0] ? `${formatNumber(gbmSignatures[0].missingFeatureRatio * 100, 1)}%` : "—"}</b><small>numeric model convention, not absence</small></article>
                <article><span>BOOTSTRAP</span><b>{gbmSignatures.reduce((maximum, signature) => Math.max(maximum, signature.bootstrapReplicates), 0)}</b><small>measurement-error perturbations</small></article>
              </div>
              <GbmSignatureTable signatures={gbmSignatures} />
              <GbmDriverPanels signatures={gbmSignatures} />
            </div>
          )}

          {mode === "neftel-programs" && result && view === "results" && (
            <div className="panel-stack">
              <div className="summary-grid">
                <article><span>FULL SUPPORT</span><b>{supportedProgramCount} / {neftelPrograms.length}</b><small>{neftelPrograms.filter((program) => program.support === "limited").length} limited · {neftelPrograms.filter((program) => program.support === "abstained").length} abstained</small></article>
                <article><span>Q ≤ 0.10</span><b>{neftelPrograms.filter((program) => program.qValue !== null && program.qValue <= 0.1).length}</b><small>BH-adjusted rank enrichments</small></article>
                <article><span>METHOD AGREEMENT</span><b>{neftelPrograms.filter((program) => program.agreement === "concordant").length}</b><small>concordant location and rank evidence</small></article>
                <article><span>EXACT MODULES</span><b>8</b><small>MES2 · MES1 · AC · OPC · NPC1 · NPC2 · G1/S · G2/M</small></article>
              </div>
              <NeftelProgramTable programs={neftelPrograms} />
              <NeftelExplanationPanels programs={neftelPrograms} />
            </div>
          )}

          {mode === "gbm-master-kinases" && result && view === "results" && (
            <div className="panel-stack">
              <div className="summary-grid">
                <article><span>FULL SUPPORT</span><b>{supportedMasterKinaseCount} / {masterKinases.length}</b><small>{masterKinases.filter((kinase) => kinase.support === "limited").length} limited · {masterKinases.filter((kinase) => kinase.support === "abstained").length} abstained</small></article>
                <article><span>Q ≤ 0.10</span><b>{masterKinases.filter((kinase) => kinase.qValue !== null && kinase.qValue <= 0.1).length}</b><small>BH-adjusted residue-stratified rank tests</small></article>
                <article><span>METHOD AGREEMENT</span><b>{masterKinases.filter((kinase) => kinase.agreement === "concordant").length}</b><small>concordant location and rank evidence</small></article>
                <article><span>SUBTYPE AGGREGATES</span><b>{masterKinaseSubtypes.filter((subtype) => subtype.support !== "abstained").length} / 4</b><small>GPM · MTC · NEU · PPR research evidence</small></article>
              </div>
              <MasterKinaseSubtypePanel subtypes={masterKinaseSubtypes} />
              <MasterKinaseTable kinases={masterKinases} />
              <MasterKinaseExplanationPanels kinases={masterKinases} />
            </div>
          )}

          {mode === "gbm-functional-proteotype" && result && view === "results" && (
            <div className="panel-stack">
              <div className="summary-grid">
                <article><span>FULL SUPPORT</span><b>{supportedFunctionalProteotypeCount} / {functionalProteotypeAxes.length}</b><small>{functionalProteotypeAxes.filter((axis) => axis.support === "limited").length} limited · {functionalProteotypeAxes.filter((axis) => axis.support === "abstained").length} abstained</small></article>
                <article><span>INDEPENDENT Q ≤ 0.10</span><b>{functionalProteotypeAxes.filter((axis) => axis.qValue !== null && axis.qValue <= 0.1).length}</b><small>competitive rank evidence, separate from latent coordinates</small></article>
                <article><span>MEAN STABILITY</span><b>{formatNumber(functionalProteotypeAxes.length ? functionalProteotypeAxes.reduce((sum, axis) => sum + (axis.stability ?? 0), 0) / functionalProteotypeAxes.length : null)}</b><small>deterministic bootstrap perturbations</small></article>
                <article><span>Σ Z RESIDUAL</span><b>{formatNumber(solver ? numberAt(solver, ["sum_to_zero_residual"]) : null, 6)}</b><small>four-axis equality constraint</small></article>
              </div>
              <FunctionalProteotypeAxisTable axes={functionalProteotypeAxes} />
              <FunctionalProteotypeExplanationPanels axes={functionalProteotypeAxes} />
              <FunctionalProteotypePathwayContextPanel axes={functionalProteotypeAxes} />
            </div>
          )}

          {mode === "gbm-rna-purity" && result && gbmRnaPurityEvidence && view === "results" && (
            <GbmRnaPurityResultPanels evidence={gbmRnaPurityEvidence} />
          )}

          {mode === "longitudinal-gbm" && result && request && view === "results" && (
            <div className="panel-stack">
              <div className="summary-grid">
                <article><span>FULL SUPPORT</span><b>{supportedTransitionCount} / {longitudinalTransitions.length}</b><small>{longitudinalTransitions.filter((transition) => transition.support === "limited").length} limited · {longitudinalTransitions.filter((transition) => transition.support === "abstained").length} abstained</small></article>
                <article><span>MEAN COVERAGE</span><b>{longitudinalTransitions.length ? `${formatNumber(longitudinalTransitions.reduce((sum, transition) => sum + (transition.coverage ?? 0), 0) * 100 / longitudinalTransitions.length, 1)}%` : "—"}</b><small>shared active proteins on the frozen axis</small></article>
                <article><span>MAX |SCORE|</span><b>{formatNumber(longitudinalTransitions.reduce<number | null>((maximum, transition) => transition.score === null ? maximum : Math.max(maximum ?? 0, Math.abs(transition.score)), null))}</b><small>source-cohort transition concordance</small></article>
                <article><span>PELT BOUNDARIES</span><b>{peltAnalysis?.boundaries.length ?? 0}</b><small>{peltAnalysis?.support ?? "not returned"} change-point sensitivity</small></article>
              </div>
              <LongitudinalTimeline request={request} transitions={longitudinalTransitions} pelt={peltAnalysis} />
              <LongitudinalTransitionTable transitions={longitudinalTransitions} />
              <LongitudinalUncertaintyInteractionPanel transitions={longitudinalTransitions} />
              <LongitudinalExplanationPanels transitions={longitudinalTransitions} />
              <PeltPanel pelt={peltAnalysis} />
            </div>
          )}

          {mode === "longitudinal-gbm-phospho" && result && request && view === "results" && (
            <div className="panel-stack">
              <div className="summary-grid">
                <article><span>FULL SUPPORT</span><b>{supportedPhosphoTransitionCount} / {longitudinalPhosphoTransitions.length}</b><small>{longitudinalPhosphoTransitions.filter((transition) => transition.support === "limited").length} limited · {longitudinalPhosphoTransitions.filter((transition) => transition.support === "abstained").length} abstained</small></article>
                <article><span>MEAN WEIGHT COVERAGE</span><b>{longitudinalPhosphoTransitions.length ? `${formatNumber(longitudinalPhosphoTransitions.reduce((sum, transition) => sum + (transition.coefficientCoverage ?? 0), 0) * 100 / longitudinalPhosphoTransitions.length, 1)}%` : "—"}</b><small>absolute frozen coefficient mass observed</small></article>
                <article><span>MAX |SCORE|</span><b>{formatNumber(longitudinalPhosphoTransitions.reduce<number | null>((maximum, transition) => transition.score === null ? maximum : Math.max(maximum ?? 0, Math.abs(transition.score)), null))}</b><small>PDC000515 source-transition concordance</small></article>
                <article><span>SELECTION GATE</span><b className="warn">limited</b><small>17/20 release-size partitions · bootstrap Jaccard 0.255</small></article>
              </div>
              <PhosphoTimeline request={request} transitions={longitudinalPhosphoTransitions} />
              <PhosphoTransitionTable transitions={longitudinalPhosphoTransitions} />
              <PhosphoUncertaintyPanel transitions={longitudinalPhosphoTransitions} />
              <PhosphoExplanationPanels transitions={longitudinalPhosphoTransitions} />
            </div>
          )}

          {mode === "longitudinal-gbm-kinase-transition" && result && request && view === "results" && (
            <KinaseTransitionResultPanels transitions={kinaseTransitions} />
          )}

          {mode === "longitudinal-gbm-reactome-transition" && result && request && view === "results" && (
            <ReactomeTransitionResultPanels
              request={request}
              transitions={reactomeTransitions}
              evaluation={reactomeEvaluation}
            />
          )}

          {mode === "longitudinal-gbm-neftel-transition" && result && request && view === "results" && (
            <NeftelTransitionResultPanels
              request={request}
              transitions={neftelTransitions}
              evaluation={neftelTransitionEvaluation}
            />
          )}

          {mode === "longitudinal-gbm-complex-transition" && result && request && view === "results" && (
            <ComplexTransitionResultPanels
              request={request}
              transitions={complexTransitions}
              evaluation={complexEvaluation}
            />
          )}

          {mode === "gbm-factor-graph" && result && request && factorGraphResult && view === "results" && (
            <FactorGraphResultPanels
              request={request}
              result={result}
              normalized={factorGraphResult}
              topology={factorGraphTopology}
            />
          )}

          {mode === "evidence-graph" && result && request && view === "network" && <NetworkColumns request={request} states={states} />}

          {mode === "evidence-graph" && result && view === "evidence" && (
            <div className="panel-stack">
              <TopologyProvenancePanel topology={topologyProvenance} />
              <section className="result-panel">
                <div className="panel-title-row"><div><p className="eyebrow">MEASUREMENT SUPPORT</p><h3>Evidence provenance</h3></div><span className="count-chip">{observedEvidence.length}</span></div>
                <div className="state-table-wrap"><table className="state-table"><thead><tr><th>Observation</th><th>Target</th><th>Modality</th><th>Evidence state</th><th>Effect ± SE</th><th>Quality</th><th>Provenance</th></tr></thead><tbody>
                  {observedEvidence.map((item, index) => isJsonObject(item) && <tr key={textAt(item, ["observation_id", "id"], String(index))}><td><b>{textAt(item, ["observation_id", "id"], `obs-${index + 1}`)}</b></td><td>{textAt(item, ["node_id", "entity_id"])}</td><td>{textAt(item, ["modality"], "—")}</td><td><span className="evidence-state">{textAt(item, ["state"], "—")}</span></td><td className="mono-cell">{formatSigned(numberAt(item, ["standardized_effect", "effect"]))} ± {formatNumber(numberAt(item, ["standard_error", "se"]))}</td><td className="mono-cell">{formatNumber(numberAt(item, ["quality_weight", "quality"]))}</td><td><code>{shortDigest(textAt(item, ["provenance_digest", "digest"]))}</code></td></tr>)}
                </tbody></table></div>
              </section>
              <section className="result-panel">
                <div className="panel-title-row"><div><p className="eyebrow">UNCERTAINTY</p><h3>Bootstrap intervals & stability</h3></div></div>
                <div className="uncertainty-grid">{states.map((state) => <article key={`${state.kind}-${state.id}`}><div><b>{state.label}</b><span>{state.kind}</span></div><strong>{formatSigned(state.estimate)}</strong><ActivityMark state={state} /><small>{formatNumber(state.lower)} ↔ {formatNumber(state.upper)} · stability {formatNumber(state.stability)}</small></article>)}</div>
              </section>
              <section className="result-panel">
                <div className="panel-title-row"><div><p className="eyebrow">SENSITIVITY</p><h3>Edge-family & modality ablations</h3></div><span className="count-chip">{ablations.length}</span></div>
                {ablations.length === 0 ? <p className="panel-empty">No ablation effects were returned.</p> : <div className="ablation-grid">{ablations.map((ablation, index) => <article key={`${ablation.target}-${ablation.family}-${index}`}><span>{ablation.family}</span><b>{ablation.target}</b><strong>{formatSigned(ablation.delta)}</strong><small>{ablation.detail || "change when this evidence family is withheld"}</small></article>)}</div>}
              </section>
              <JsonPanel title="External KINOPHOS agreement" eyebrow="NON-OVERRIDING COMPARISON" value={kinophos ? safeJson(kinophos) : null} empty="No external KINOPHOS profile was supplied. Local kinase estimates remain explicitly experimental." />
            </div>
          )}

          {mode === "gbm-proteomic-axes" && result && view === "evidence" && (
            <div className="panel-stack">
              <section className="result-panel zero-fill-panel">
                <div className="panel-title-row"><div><p className="eyebrow">COVERAGE / ABSTENTION</p><h3>Evidence-conserving model input</h3></div><span className="boundary-chip">source convention made visible</span></div>
                <div className="zero-fill-explainer">
                  <article><b>Observed LFQ</b><strong>{gbmEvidence ? numberAt(gbmEvidence, ["observed_model_features"]) ?? 0 : 0}</strong><p>Positive measured proteins that intersect the published 3,025-feature universe.</p></article>
                  <article><b>Declared non-model</b><strong>{gbmEvidence ? numberAt(gbmEvidence, ["observed_non_model_features"]) ?? 0 : 0}</strong><p>Observed proteins preserved in the request but unused by these exact ensembles.</p></article>
                  <article><b>Left-censored</b><strong>{gbmEvidence ? numberAt(gbmEvidence, ["left_censored"]) ?? 0 : 0}</strong><p>Upper limits are retained in the receipt and excluded from point prediction.</p></article>
                  <article className="warning"><b>Published zero-fill</b><strong>{gbmSignatures[0]?.missingFeatureCount ?? "—"}</strong><p>Unmeasured model features set to numeric zero by the published predictor; never interpreted as biological loss.</p></article>
                </div>
              </section>
              <section className="result-panel">
                <div className="panel-title-row"><div><p className="eyebrow">EXECUTED REQUEST</p><h3>Protein evidence ledger</h3></div><span className="count-chip">{request ? arrayAt(request, ["measurements"]).length : 0}</span></div>
                <div className="state-table-wrap"><table className="state-table"><thead><tr><th>Gene</th><th>State</th><th>LFQ intensity</th><th>Upper limit</th><th>log2 SE</th><th>Provenance</th></tr></thead><tbody>
                  {(request ? arrayAt(request, ["measurements"]) : []).map((item, index) => isJsonObject(item) && <tr key={textAt(item, ["gene_symbol"], String(index))}>
                    <td><b>{textAt(item, ["gene_symbol"], `protein-${index + 1}`)}</b></td>
                    <td><span className="evidence-state">{textAt(item, ["state"], "—")}</span></td>
                    <td className="mono-cell">{formatNumber(numberAt(item, ["lfq_intensity"]), 2)}</td>
                    <td className="mono-cell">{formatNumber(numberAt(item, ["lfq_upper_limit"]), 2)}</td>
                    <td className="mono-cell">{formatNumber(numberAt(item, ["log2_standard_error"]), 3)}</td>
                    <td><code>{shortDigest(textAt(item, ["provenance_digest"]))}</code></td>
                  </tr>)}
                </tbody></table></div>
              </section>
              <section className="mechanism-grid">
                <JsonPanel title="LFQ normalization" eyebrow="PUBLISHED PREPROCESSING" value={gbmNormalization ? safeJson(gbmNormalization) : null} empty="No normalization summary was returned." />
                <JsonPanel title="Evidence summary" eyebrow="EXPLICIT ABSENCE SEMANTICS" value={gbmEvidence ? safeJson(gbmEvidence) : null} empty="No evidence summary was returned." />
              </section>
              <GbmDriverPanels signatures={gbmSignatures} />
            </div>
          )}

          {mode === "neftel-programs" && result && view === "evidence" && (
            <div className="panel-stack">
              <section className="result-panel zero-fill-panel">
                <div className="panel-title-row"><div><p className="eyebrow">INTERPRETATION BOUNDARY</p><h3>Bulk-protein program evidence</h3></div><span className="boundary-chip">not cell-state deconvolution</span></div>
                <div className="zero-fill-explainer">
                  <article><b>Exact source modules</b><strong>8</strong><p>MES2, MES1, AC, OPC, NPC1, NPC2, G1/S, and G2/M from the pinned Table S2 catalog.</p></article>
                  <article><b>Derived families</b><strong>5</strong><p>Equal-source-program, equal-marker-mass pooling; never a hidden average across unequal marker sets.</p></article>
                  <article><b>Active observations</b><strong>{request ? neftelRequestStats(request).active : 0}</strong><p>Observed and left-censored effects evaluated with explicit quality and error.</p></article>
                  <article className="warning"><b>Abstained outputs</b><strong>{neftelPrograms.filter((program) => program.support === "abstained").length}</strong><p>Coverage and effective-sample floors prevent sparse evidence from becoming a negative program claim.</p></article>
                </div>
              </section>
              <section className="result-panel">
                <div className="panel-title-row"><div><p className="eyebrow">EXECUTED REQUEST</p><h3>Standardized protein contrast ledger</h3></div><span className="count-chip">{request ? arrayAt(request, ["observations"]).length : 0}</span></div>
                <div className="state-table-wrap"><table className="state-table"><thead><tr><th>Observation</th><th>Gene</th><th>State</th><th>Effect ± SE</th><th>Quality</th><th>Provenance</th></tr></thead><tbody>
                  {(request ? arrayAt(request, ["observations"]) : []).map((item, index) => isJsonObject(item) && <tr key={textAt(item, ["observation_id"], String(index))}>
                    <td><b>{textAt(item, ["observation_id"], `observation-${index + 1}`)}</b></td><td>{textAt(item, ["gene_symbol"], "—")}</td><td><span className="evidence-state">{textAt(item, ["state"], "—")}</span></td><td className="mono-cell">{formatSigned(numberAt(item, ["standardized_effect"]))} ± {formatNumber(numberAt(item, ["standard_error"]))}</td><td className="mono-cell">{formatNumber(numberAt(item, ["quality_weight"]))}</td><td><code>{shortDigest(textAt(item, ["provenance_digest"]))}</code></td>
                  </tr>)}
                </tbody></table></div>
              </section>
              <NeftelExplanationPanels programs={neftelPrograms} />
              <JsonPanel title="Pinned numerical profile" eyebrow="METHOD CONSTANTS / ABSTENTION FLOORS" value={profile ? safeJson(profile) : null} empty="The Neftel profile is unavailable." />
            </div>
          )}

          {mode === "gbm-master-kinases" && result && view === "evidence" && (
            <div className="panel-stack">
              <section className="result-panel zero-fill-panel">
                <div className="panel-title-row"><div><p className="eyebrow">INTERPRETATION / SOURCE BOUNDARY</p><h3>Independent master-kinase concordance evidence</h3></div><span className="boundary-chip">not an exact SPHINKS port</span></div>
                <div className="zero-fill-explainer">
                  <article><b>Pinned source signatures</b><strong>24</strong><p>Master-kinase edges and subtype labels are frozen from SPHINKS/MK Tables 5d and 5e.</p></article>
                  <article><b>Active phosphosites</b><strong>{request ? masterKinaseRequestStats(request).active : 0}</strong><p>Observed values and left-censored upper limits retain distinct likelihood roles.</p></article>
                  <article><b>Rank null</b><strong>{request ? numberAt(request, ["permutation_replicates"]) ?? 256 : 256}</strong><p>Deterministic residue-stratified observation-tuple permutations keep source-edge weights fixed and produce empirical p-values with fixed-24 BH q-values.</p></article>
                  <article className="warning"><b>Abstained kinases</b><strong>{masterKinases.filter((kinase) => kinase.support === "abstained").length}</strong><p>Sparse coverage is never converted into absent, suppressed, or clinically actionable kinase activity.</p></article>
                </div>
              </section>
              <section className="result-panel">
                <div className="panel-title-row"><div><p className="eyebrow">EXECUTED REQUEST</p><h3>Phosphosite contrast ledger</h3></div><span className="count-chip">{request ? arrayAt(request, ["observations"]).length : 0}</span></div>
                <div className="state-table-wrap"><table className="state-table"><thead><tr><th>Observation</th><th>Phosphosite</th><th>State</th><th>Effect ± SE</th><th>Quality</th><th>Provenance</th></tr></thead><tbody>
                  {(request ? arrayAt(request, ["observations"]) : []).map((item, index) => isJsonObject(item) && <tr key={textAt(item, ["observation_id"], String(index))}>
                    <td><b>{textAt(item, ["observation_id"], `observation-${index + 1}`)}</b></td><td>{textAt(item, ["phosphosite_id"], "—")}</td><td><span className="evidence-state">{textAt(item, ["state"], "—")}</span></td><td className="mono-cell">{formatSigned(numberAt(item, ["standardized_effect"]))} ± {formatNumber(numberAt(item, ["standard_error"]))}</td><td className="mono-cell">{formatNumber(numberAt(item, ["quality_weight"]) ?? (item.state === "observed" || item.state === "left_censored" ? 1 : null))}</td><td><code>{shortDigest(textAt(item, ["provenance_digest"]))}</code></td>
                  </tr>)}
                </tbody></table></div>
              </section>
              <MasterKinaseExplanationPanels kinases={masterKinases} />
              <section className="mechanism-grid">
                <JsonPanel title="Pinned source provenance" eyebrow="TABLES 5A / 5D / 5E DIGESTS" value={provenance ? safeJson(provenance) : null} empty="No source provenance was returned." />
                <JsonPanel title="Numerical profile" eyebrow="METHOD CONSTANTS / SUPPORT FLOORS" value={profile ? safeJson(profile) : null} empty="The master-kinase profile is unavailable." />
              </section>
            </div>
          )}

          {mode === "gbm-functional-proteotype" && result && view === "evidence" && (
            <div className="panel-stack">
              <section className="result-panel zero-fill-panel">
                <div className="panel-title-row"><div><p className="eyebrow">EVIDENCE SEMANTICS / CLAIM BOUNDARY</p><h3>Evidence-conserving protein input</h3></div><span className="boundary-chip">concordance · never subtype classification</span></div>
                <div className="zero-fill-explainer">
                  <article><b>Observed proteins</b><strong>{request ? functionalProteotypeRequestStats(request).observed : 0}</strong><p>Standardized point contrasts with explicit errors and reliability weights enter the robust constrained solve.</p></article>
                  <article><b>Left-censored limits</b><strong>{request ? functionalProteotypeRequestStats(request).leftCensored : 0}</strong><p>Upper limits enter a one-sided Huber hinge and are never converted into point observations.</p></article>
                  <article><b>Four source axes</b><strong>4 × 150</strong><p>Exact GPM, MTC, NEU, and PPR Table 2d gene signatures are fitted jointly under Σ z = 0.</p></article>
                  <article className="warning"><b>Subtype calls emitted</b><strong>0</strong><p>Coordinates, rank q-values, and Table 2e pathway context never produce a winner, subtype probability, or patient classification.</p></article>
                </div>
              </section>
              <section className="result-panel">
                <div className="panel-title-row"><div><p className="eyebrow">EXECUTED REQUEST</p><h3>Standardized protein contrast ledger</h3></div><span className="count-chip">{request ? arrayAt(request, ["observations"]).length : 0}</span></div>
                <div className="state-table-wrap"><table className="state-table"><thead><tr><th>Observation</th><th>Gene</th><th>State</th><th>Effect ± SE</th><th>Quality</th><th>Provenance</th></tr></thead><tbody>
                  {(request ? arrayAt(request, ["observations"]) : []).map((item, index) => isJsonObject(item) && <tr key={textAt(item, ["observation_id"], String(index))}>
                    <td><b>{textAt(item, ["observation_id"], `observation-${index + 1}`)}</b></td><td>{textAt(item, ["gene_symbol"], "—")}</td><td><span className="evidence-state">{textAt(item, ["state"], "—")}</span></td><td className="mono-cell">{formatSigned(numberAt(item, ["standardized_effect"]))} ± {formatNumber(numberAt(item, ["standard_error"]))}</td><td className="mono-cell">{formatNumber(numberAt(item, ["quality_weight"]) ?? (item.state === "observed" || item.state === "left_censored" ? 1 : null))}</td><td><code>{shortDigest(textAt(item, ["provenance_digest"]))}</code></td>
                  </tr>)}
                </tbody></table></div>
              </section>
              <FunctionalProteotypeExplanationPanels axes={functionalProteotypeAxes} />
              <FunctionalProteotypePathwayContextPanel axes={functionalProteotypeAxes} />
              <section className="mechanism-grid">
                <JsonPanel title="Content-bound source provenance" eyebrow="TABLE 2D / TABLE 2E / LICENSE / SEEDS" value={provenance ? safeJson(provenance) : null} empty="No functional-proteotype provenance was returned." />
                <JsonPanel title="Numerical profile" eyebrow="CONSTRAINED SOLVER / SUPPORT FLOORS" value={profile ? safeJson(profile) : null} empty="The functional-proteotype profile is unavailable." />
              </section>
            </div>
          )}

          {mode === "gbm-rna-purity" && result && request && gbmRnaPurityEvidence && view === "evidence" && (
            <GbmRnaPurityEvidencePanel request={request} evidence={gbmRnaPurityEvidence} />
          )}

          {mode === "longitudinal-gbm" && result && request && view === "evidence" && (
            <LongitudinalEvidencePanel
              request={request}
              transitions={longitudinalTransitions}
              profile={profile}
              provenance={isJsonObject(provenance) ? provenance : null}
            />
          )}

          {mode === "longitudinal-gbm-phospho" && result && request && view === "evidence" && (
            <PhosphoEvidencePanel
              request={request}
              result={result}
              transitions={longitudinalPhosphoTransitions}
              profile={profile}
              provenance={isJsonObject(provenance) ? provenance : null}
            />
          )}

          {mode === "longitudinal-gbm-kinase-transition" && result && request && view === "evidence" && (
            <KinaseTransitionEvidencePanel
              request={request}
              transitions={kinaseTransitions}
              profile={profile}
              provenance={isJsonObject(provenance) ? provenance : null}
            />
          )}

          {mode === "longitudinal-gbm-reactome-transition" && result && request && view === "evidence" && (
            <ReactomeTransitionEvidencePanel
              request={request}
              transitions={reactomeTransitions}
              profile={profile}
              provenance={isJsonObject(provenance) ? provenance : null}
            />
          )}

          {mode === "longitudinal-gbm-neftel-transition" && result && request && view === "evidence" && (
            <NeftelTransitionEvidencePanel
              request={request}
              transitions={neftelTransitions}
              profile={profile}
              provenance={isJsonObject(provenance) ? provenance : null}
            />
          )}

          {mode === "longitudinal-gbm-complex-transition" && result && request && view === "evidence" && (
            <ComplexTransitionEvidencePanel
              request={request}
              transitions={complexTransitions}
              profile={profile}
              provenance={isJsonObject(provenance) ? provenance : null}
            />
          )}

          {mode === "gbm-factor-graph" && result && request && factorGraphResult && view === "evidence" && (
            <FactorGraphEvidencePanels
              request={request}
              result={result}
              normalized={factorGraphResult}
            />
          )}

          {mode === "evidence-graph" && result && view === "audit" && (
            <div className="panel-stack audit-grid">
              <section className="result-panel receipt-panel">
                <div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC REPLAY</p><h3>Verification receipt</h3></div>{verifying ? <button className="danger-button" onClick={cancelVerification}>Cancel verification</button> : <button className="verify-button" onClick={() => void verifyReplay()}>Recompute</button>}</div>
                {verification ? (
                  <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{pretty(verification)}</pre></>
                ) : <p className="panel-empty">Recompute this exact request to verify its request digest, result digest, profile, solver trace, and semantic result.</p>}
              </section>
              <JsonPanel title="Solver diagnostics" eyebrow="CONVERGENCE TRACE" value={solver ? safeJson(solver) : null} empty="No solver diagnostics were returned." />
              <JsonPanel title="Provenance ledger" eyebrow="TRACEABLE SOURCES" value={provenance ? safeJson(provenance) : null} empty="No provenance ledger was returned." />
              <section className="result-panel limitations-panel"><div className="panel-title-row"><div><p className="eyebrow">BOUNDARIES</p><h3>Limitations</h3></div></div><ul>{limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : pretty(item)}</li>)}</ul><p>This output is research-use-only, non-prescriptive, and must not be used for diagnosis or treatment selection.</p></section>
              <JsonPanel title="Raw result receipt" eyebrow="IMMUTABLE PAYLOAD" value={safeJson(result)} empty="No result is available." />
            </div>
          )}

          {mode === "gbm-proteomic-axes" && result && view === "audit" && (
            <div className="panel-stack audit-grid">
              <section className="result-panel receipt-panel">
                <div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC REPLAY</p><h3>Published-model verification</h3></div>{verifying ? <button className="danger-button" onClick={cancelVerification}>Cancel verification</button> : <button className="verify-button" onClick={() => void verifyReplay()}>Recompute</button>}</div>
                {verification ? (
                  <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{pretty(verification)}</pre></>
                ) : <p className="panel-empty">Recompute this exact LFQ request to verify the request, profile, original model source, converted artifact, result digest, and semantic payload.</p>}
              </section>
              <JsonPanel title="Model provenance" eyebrow="PINNED SOURCE / CONVERSION" value={provenance ? safeJson(provenance) : null} empty="No model provenance was returned." />
              <JsonPanel title="Algorithm profile" eyebrow="CONTENT-BOUND CONSTANTS" value={profile ? safeJson(profile) : null} empty="The algorithm profile is unavailable." />
              <section className="result-panel limitations-panel"><div className="panel-title-row"><div><p className="eyebrow">BOUNDARIES</p><h3>GBM model limitations</h3></div></div><ul>{limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : pretty(item)}</li>)}</ul><p>These are bulk-tissue research signature activations—not cell fractions, diagnoses, prognoses, patient subtypes, or treatment recommendations.</p></section>
              <JsonPanel title="Raw model receipt" eyebrow="IMMUTABLE PAYLOAD" value={safeJson(result)} empty="No result is available." />
            </div>
          )}

          {mode === "neftel-programs" && result && view === "audit" && (
            <div className="panel-stack audit-grid">
              <section className="result-panel receipt-panel">
                <div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC REPLAY</p><h3>Neftel program verification</h3></div>{verifying ? <button className="danger-button" onClick={cancelVerification}>Cancel verification</button> : <button className="verify-button" onClick={() => void verifyReplay()}>Recompute</button>}</div>
                {verification ? <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{pretty(verification)}</pre></> : <p className="panel-empty">Recompute the exact request to verify its profile-pinned catalog, random seeds, digests, and semantic result.</p>}
              </section>
              <JsonPanel title="Catalog provenance" eyebrow="TABLE S2 / HGNC / EXACT PROGRAMS" value={provenance ? safeJson(provenance) : null} empty="No catalog provenance was returned." />
              <JsonPanel title="Algorithm profile" eyebrow="CONTENT-BOUND CONSTANTS" value={profile ? safeJson(profile) : null} empty="The algorithm profile is unavailable." />
              <section className="result-panel limitations-panel"><div className="panel-title-row"><div><p className="eyebrow">BOUNDARIES</p><h3>Neftel program limitations</h3></div></div><ul>{limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : pretty(item)}</li>)}</ul><p>Protein-level evidence can be confounded by non-tumor cells and must not be interpreted as a cell fraction, tumor-cell origin, diagnosis, subtype, or treatment recommendation.</p></section>
              <JsonPanel title="Raw program receipt" eyebrow="IMMUTABLE PAYLOAD" value={safeJson(result)} empty="No result is available." />
            </div>
          )}

          {mode === "gbm-master-kinases" && result && view === "audit" && (
            <div className="panel-stack audit-grid">
              <section className="result-panel receipt-panel">
                <div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC REPLAY</p><h3>Master-kinase concordance verification</h3></div>{verifying ? <button className="danger-button" onClick={cancelVerification}>Cancel verification</button> : <button className="verify-button" onClick={() => void verifyReplay()}>Recompute</button>}</div>
                {verification ? <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{pretty(verification)}</pre></> : <p className="panel-empty">Recompute the exact request to verify its profile-pinned source catalog, request and result digests, and semantic payload.</p>}
              </section>
              <JsonPanel title="Source provenance" eyebrow="SPHINKS TABLES 5A / 5D / 5E" value={provenance ? safeJson(provenance) : null} empty="No source provenance was returned." />
              <JsonPanel title="Algorithm profile" eyebrow="CONTENT-BOUND CONSTANTS" value={profile ? safeJson(profile) : null} empty="The algorithm profile is unavailable." />
              <section className="result-panel limitations-panel"><div className="panel-title-row"><div><p className="eyebrow">BOUNDARIES</p><h3>Master-kinase concordance limitations</h3></div></div><ul>{limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : pretty(item)}</li>)}</ul><p>This independent signature-concordance output is not an exact SPHINKS port, calibrated kinase activity, subtype probability, diagnosis, prognosis, or treatment recommendation.</p></section>
              <JsonPanel title="Raw concordance receipt" eyebrow="IMMUTABLE PAYLOAD" value={safeJson(result)} empty="No result is available." />
            </div>
          )}

          {mode === "gbm-functional-proteotype" && result && view === "audit" && (
            <div className="panel-stack audit-grid">
              <section className="result-panel receipt-panel">
                <div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC REPLAY</p><h3>Functional-proteotype verification</h3></div>{verifying ? <button className="danger-button" onClick={cancelVerification}>Cancel verification</button> : <button className="verify-button" onClick={() => void verifyReplay()}>Recompute</button>}</div>
                {verification ? <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{pretty(verification)}</pre></> : <p className="panel-empty">Recompute the exact request to verify request and result digests, the constrained solver trace, numerical profile, source catalogs, and semantic payload.</p>}
              </section>
              <JsonPanel title="Constrained solver diagnostics" eyebrow="MONOTONE OBJECTIVE TRACE / Σ Z = 0" value={solver ? safeJson(solver) : null} empty="No constrained solver diagnostics were returned." />
              <JsonPanel title="Source and computation provenance" eyebrow="WORKBOOK / CATALOG / SOURCE / SEEDS" value={provenance ? safeJson(provenance) : null} empty="No functional-proteotype provenance was returned." />
              <JsonPanel title="Algorithm profile" eyebrow="CONTENT-BOUND CONSTANTS" value={profile ? safeJson(profile) : null} empty="The functional-proteotype profile is unavailable." />
              <section className="result-panel limitations-panel"><div className="panel-title-row"><div><p className="eyebrow">BOUNDARIES</p><h3>Functional-proteotype limitations</h3></div></div><ul>{limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : pretty(item)}</li>)}</ul><p>GPM, MTC, NEU, and PPR are bulk-protein source-cohort concordance coordinates—not patient subtype labels, probabilities, winners, diagnoses, prognoses, or treatment guidance. Table 2e remains source-only pathway context; sample pathway inference is not evaluated.</p></section>
              <JsonPanel title="Raw functional-proteotype receipt" eyebrow="IMMUTABLE PAYLOAD" value={safeJson(result)} empty="No result is available." />
            </div>
          )}

          {mode === "gbm-rna-purity" && result && view === "audit" && (
            <div className="panel-stack audit-grid">
              <section className="result-panel receipt-panel">
                <div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC REPLAY</p><h3>GBMPurity model verification</h3></div>{verifying ? <button className="danger-button" onClick={cancelVerification}>Cancel verification</button> : <button className="verify-button" onClick={() => void verifyReplay()}>Recompute</button>}</div>
                {verification ? <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{pretty(verification)}</pre></> : <p className="panel-empty">Recompute the exact raw-count request to verify its request digest, frozen profile, converted model artifact, result digest, and semantic payload.</p>}
              </section>
              <JsonPanel title="Forward-pass diagnostics" eyebrow="PREPROCESSING / HIDDEN ACTIVATIONS / FLOAT32" value={solver ? safeJson(solver) : null} empty="No GBMPurity forward-pass diagnostics were returned." />
              <JsonPanel title="Model provenance" eyebrow="UPSTREAM COMMIT / MODEL / GENES / CONVERSION" value={provenance ? safeJson(provenance) : null} empty="No GBMPurity source provenance was returned." />
              <JsonPanel title="Algorithm profile" eyebrow="CONTENT-BOUND SOURCE AND RUNTIME" value={profile ? safeJson(profile) : null} empty="The GBMPurity algorithm profile is unavailable." />
              <section className="result-panel limitations-panel"><div className="panel-title-row"><div><p className="eyebrow">BOUNDARIES</p><h3>GBMPurity limitations</h3></div></div><ul>{limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : pretty(item)}</li>)}</ul><p>This single published-model estimate is research-use-only. It is not histologic truth, immune/stromal composition, diagnosis, prognosis, treatment-response prediction, or treatment guidance, and it carries no fabricated calibrated interval.</p></section>
              <JsonPanel title="Raw GBMPurity receipt" eyebrow="IMMUTABLE PAYLOAD" value={safeJson(result)} empty="No result is available." />
            </div>
          )}

          {mode === "longitudinal-gbm" && result && view === "audit" && (
            <div className="panel-stack audit-grid">
              <section className="result-panel receipt-panel">
                <div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC REPLAY</p><h3>Longitudinal transition verification</h3></div>{verifying ? <button className="danger-button" onClick={cancelVerification}>Cancel verification</button> : <button className="verify-button" onClick={() => void verifyReplay()}>Recompute</button>}</div>
                {verification ? <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{pretty(verification)}</pre></> : <p className="panel-empty">Recompute the exact ordered series to verify request, profile, transition semantics, PELT semantics, and result digests.</p>}
              </section>
              <JsonPanel title="Source provenance" eyebrow="PDC000514 / DE-IDENTIFIED MODEL LOCKS" value={isJsonObject(provenance) ? provenance : null} empty="No longitudinal source provenance was returned." />
              <JsonPanel title="Algorithm profile" eyebrow="FROZEN AXIS / SUPPORT FLOORS / SEEDS" value={profile ? safeJson(profile) : null} empty="The longitudinal algorithm profile is unavailable." />
              <section className="result-panel limitations-panel"><div className="panel-title-row"><div><p className="eyebrow">BOUNDARIES</p><h3>Longitudinal GBM limitations</h3></div></div><ul>{limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : pretty(item)}</li>)}</ul><p>This protein-level source-cohort concordance output is not patient evolution, recurrence prediction, diagnosis, prognosis, a clinical state, or treatment guidance.</p></section>
              <JsonPanel title="Raw longitudinal receipt" eyebrow="IMMUTABLE PAYLOAD" value={safeJson(result)} empty="No result is available." />
            </div>
          )}

          {mode === "longitudinal-gbm-phospho" && result && view === "audit" && (
            <div className="panel-stack audit-grid">
              <section className="result-panel receipt-panel">
                <div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC REPLAY</p><h3>Phosphosite transition verification</h3></div>{verifying ? <button className="danger-button" onClick={cancelVerification}>Cancel verification</button> : <button className="verify-button" onClick={() => void verifyReplay()}>Recompute</button>}</div>
                {verification ? <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{pretty(verification)}</pre></> : <p className="panel-empty">Recompute the exact ordered phosphosite series to verify request, source artifact, profile, transitions, explicit unfitted views, and result digest.</p>}
              </section>
              <JsonPanel title="Standalone source provenance" eyebrow="PDC000515 / HGNC / SPHINKS CC-BY LOCKS" value={isJsonObject(provenance) ? provenance : null} empty="No phosphosite source provenance was returned." />
              <JsonPanel title="Algorithm profile" eyebrow="FROZEN AXIS / QUALITY GATES / SEMANTIC DIGEST" value={profile ? safeJson(profile) : null} empty="The phosphosite algorithm profile is unavailable." />
              <section className="result-panel limitations-panel"><div className="panel-title-row"><div><p className="eyebrow">BOUNDARIES</p><h3>Longitudinal phosphosite limitations</h3></div></div><ul>{limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : pretty(item)}</li>)}</ul><p>This raw phosphosite source-concordance output is not occupancy, kinase activity, protein/phosphosite fusion, patient evolution, recurrence prediction, diagnosis, prognosis, or treatment guidance.</p></section>
              <JsonPanel title="Raw phosphosite receipt" eyebrow="IMMUTABLE PAYLOAD" value={safeJson(result)} empty="No result is available." />
            </div>
          )}

          {mode === "longitudinal-gbm-kinase-transition" && result && view === "audit" && (
            <div className="panel-stack audit-grid">
              <section className="result-panel receipt-panel">
                <div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC REPLAY</p><h3>SPHINKS signature-transition verification</h3></div>{verifying ? <button className="danger-button" onClick={cancelVerification}>Cancel verification</button> : <button className="verify-button" onClick={() => void verifyReplay()}>Recompute</button>}</div>
                {verification ? <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{pretty(verification)}</pre></> : <p className="panel-empty">Recompute the exact ordered phosphosite series to verify the request, exact 24-kinase family, transition semantics, LIMITED claim boundary, source provenance, and result digest.</p>}
              </section>
              <JsonPanel title="Source and computation provenance" eyebrow="PDC000515 / SPHINKS / PATIENT REFITS / SEEDS" value={isJsonObject(provenance) ? provenance : null} empty="No kinase-transition provenance was returned." />
              <JsonPanel title="Algorithm profile" eyebrow="24 HYPOTHESES / QUALITY GATES / CLAIM CEILING" value={profile ? safeJson(profile) : null} empty="The kinase-transition profile is unavailable." />
              <section className="result-panel limitations-panel"><div className="panel-title-row"><div><p className="eyebrow">BOUNDARIES</p><h3>Signature-transition limitations</h3></div><span className="support-badge limited">LIMITED only</span></div><ul>{limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : pretty(item)}</li>)}</ul><p>These same-assay source-cohort signature coordinates do not infer kinase activity, biochemical activity, causality, independent evidence, patient evolution, recurrence, prognosis, response, or treatment guidance.</p></section>
              <JsonPanel title="Raw signature-transition receipt" eyebrow="IMMUTABLE PAYLOAD" value={safeJson(result)} empty="No result is available." />
            </div>
          )}

          {mode === "longitudinal-gbm-reactome-transition" && result && view === "audit" && (
            <div className="panel-stack audit-grid">
              <section className="result-panel receipt-panel">
                <div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC REPLAY</p><h3>Reactome conditional-transition verification</h3></div>{verifying ? <button className="danger-button" onClick={cancelVerification}>Cancel verification</button> : <button className="verify-button" onClick={() => void verifyReplay()}>Recompute</button>}</div>
                {verification ? <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{pretty(verification)}</pre></> : <p className="panel-empty">Recompute the exact ordered protein series to verify the request, fixed pathway panel, fitted model, transition topology, global and conditional semantics, uncertainty, ablations, provenance, and result digest.</p>}
              </section>
              <JsonPanel title="Source and computation provenance" eyebrow="REACTOME V97 / PDC000514 / FITTED ARTIFACT / SEEDS" value={isJsonObject(provenance) ? provenance : null} empty="No Reactome transition provenance was returned." />
              <JsonPanel title="Algorithm profile" eyebrow="FIXED PANEL / ROBUST RIDGE / SUPPORT GATES" value={profile ? safeJson(profile) : null} empty="The Reactome transition profile is unavailable." />
              <ReactomeLockedEvaluationPanel evaluation={reactomeEvaluation} />
              <section className="result-panel limitations-panel"><div className="panel-title-row"><div><p className="eyebrow">BOUNDARIES</p><h3>Reactome transition limitations</h3></div></div><ul>{limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : pretty(item)}</li>)}</ul><p>These are research-only global and conditional source-cohort concordance coordinates. They are not pathway activity, pathway flux, causal biology, patient evolution, recurrence prediction, prognosis, treatment-response prediction, or treatment guidance. PI3K/AKT remains overlap-confounded and LIMITED.</p></section>
              <JsonPanel title="Raw Reactome transition receipt" eyebrow="IMMUTABLE PAYLOAD" value={safeJson(result)} empty="No result is available." />
            </div>
          )}

          {mode === "longitudinal-gbm-neftel-transition" && result && view === "audit" && (
            <div className="panel-stack audit-grid">
              <section className="result-panel receipt-panel">
                <div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC REPLAY</p><h3>Neftel conditional-transition verification</h3></div>{verifying ? <button className="danger-button" onClick={cancelVerification}>Cancel verification</button> : <button className="verify-button" onClick={() => void verifyReplay()}>Recompute</button>}</div>
                {verification ? <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{pretty(verification)}</pre></> : <p className="panel-empty">Recompute the exact ordered protein series to verify the request, eight exact Neftel programs, fitted artifact, LIMITED release gate, transition topology, uncertainty, ablations, provenance, and result digest.</p>}
              </section>
              <JsonPanel title="Source and computation provenance" eyebrow="NEFTEL TABLE S2 / HGNC / PDC000514 / FITTED ARTIFACT" value={isJsonObject(provenance) ? provenance : null} empty="No Neftel transition provenance was returned." />
              <JsonPanel title="Algorithm profile" eyebrow="8 EXACT PROGRAMS / ROBUST RIDGE / LIMITED RELEASE GATE" value={profile ? safeJson(profile) : null} empty="The Neftel transition profile is unavailable." />
              <NeftelLockedEvaluationPanel evaluation={neftelTransitionEvaluation} />
              <section className="result-panel limitations-panel"><div className="panel-title-row"><div><p className="eyebrow">BOUNDARIES</p><h3>Neftel transition limitations</h3></div><span className="support-badge limited">equal membership preferred</span></div><ul>{limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : pretty(item)}</li>)}</ul><p>These are research-only global and conditional bulk-protein program concordance coordinates. The fitted dictionary did not beat equal membership, all eight leave-program intervals cross zero, and no individual program effect is established. Outputs are not cell states, fractions, activation, causal evolution, recurrence prediction, prognosis, treatment response, or clinical guidance.</p></section>
              <JsonPanel title="Raw Neftel transition receipt" eyebrow="IMMUTABLE PAYLOAD" value={safeJson(result)} empty="No result is available." />
            </div>
          )}

          {mode === "longitudinal-gbm-complex-transition" && result && view === "audit" && (
            <div className="panel-stack audit-grid">
              <section className="result-panel receipt-panel">
                <div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC REPLAY</p><h3>Reactome complex-transition verification</h3></div>{verifying ? <button className="danger-button" onClick={cancelVerification}>Cancel verification</button> : <button className="verify-button" onClick={() => void verifyReplay()}>Recompute</button>}</div>
                {verification ? <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{pretty(verification)}</pre></> : <p className="panel-empty">Recompute the exact ordered protein series to verify the request, fixed participant sets, fitted factor artifact, transition topology, uncertainty, ablations, provenance, and result digest.</p>}
              </section>
              <JsonPanel title="Source and computation provenance" eyebrow="PDC000514 / REACTOME V97 / FITTED FACTOR / SEEDS" value={isJsonObject(provenance) ? provenance : null} empty="No complex-transition provenance was returned." />
              <JsonPanel title="Algorithm profile" eyebrow="28 PARTICIPANT SETS / HUBER IRLS / SUPPORT GATES" value={profile ? safeJson(profile) : null} empty="The complex-transition profile is unavailable." />
              <ComplexLockedEvaluationPanel evaluation={complexEvaluation} />
              <section className="result-panel limitations-panel"><div className="panel-title-row"><div><p className="eyebrow">BOUNDARIES</p><h3>Complex-transition limitations</h3></div></div><ul>{limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : pretty(item)}</li>)}</ul><p>These are source-cohort Reactome participant-set member-transition coordinates. They are not physical complex assembly, abundance, activity, occupancy, stoichiometry, essential-subunit evidence, causal biology, patient evolution, recurrence prediction, prognosis, treatment-response prediction, or treatment guidance.</p></section>
              <JsonPanel title="Raw complex-transition receipt" eyebrow="IMMUTABLE PAYLOAD" value={safeJson(result)} empty="No result is available." />
            </div>
          )}

          {mode === "gbm-factor-graph" && result && view === "audit" && (
            <div className="panel-stack audit-grid">
              <FactorGraphBoundary result={result} />
              <section className="result-panel receipt-panel">
                <div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC OUTER + CHILD REPLAY</p><h3>Independent factor-graph composition verification</h3></div>{verifying ? <button className="danger-button" onClick={cancelVerification}>Cancel verification</button> : <button className="verify-button" onClick={() => void verifyReplay()}>Recompute</button>}</div>
                {verification ? <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{pretty(verification)}</pre></> : <p className="panel-empty">Recompute the exact outer request in deterministic child sequence to verify both nested receipts, the 41-node / 39-edge annotation topology, independent-block semantics, the no-fusion boundary, provenance, and result digests.</p>}
              </section>
              <FactorGraphTopologyPanel topology={factorGraphTopology} />
              <JsonPanel title="Outer composition provenance" eyebrow="TWO CHILD RECEIPTS / INDEPENDENT BLOCKS / NO FUSION" value={isJsonObject(provenance) ? provenance : null} empty="No factor-graph provenance was returned." />
              <JsonPanel title="Composition profile" eyebrow="TOPOLOGY / CHILD PROFILE BINDINGS / RESOURCE LIMITS" value={profile ? safeJson(profile) : null} empty="The factor-graph composition profile is unavailable." />
              <section className="result-panel limitations-panel factor-limitations-panel"><div className="panel-title-row"><div><p className="eyebrow">SOURCE-COHORT / NO-FUSION BOUNDARIES</p><h3>Factor-graph composition limitations</h3></div><span className="support-badge limited">research use only</span></div><ul>{limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : pretty(item)}</li>)}</ul><p>This surface composes two independently fitted, source-cohort concordance models; it is not another fitted model. The children execute deterministically in sequence, not concurrently. Annotation-only containment never implies cross-modal coupling. There is no protein/phosphosite fusion, joint latent state, causal biology, patient evolution, recurrence prediction, prognosis, treatment-response prediction, diagnosis, or treatment guidance.</p></section>
              <JsonPanel title="Raw factor-graph receipt" eyebrow="IMMUTABLE OUTER DOCUMENT WITH EXACT NESTED CHILD RESULTS" value={safeJson(result)} empty="No result is available." />
            </div>
          )}
        </section>
      </section>

      <footer className="workbench-footer"><span>GLIO / PROTEOGEN</span><span>Evidence-conserving research inference · no patient data · no persistence</span><span>{profileId}</span></footer>
    </main>
  );
}
