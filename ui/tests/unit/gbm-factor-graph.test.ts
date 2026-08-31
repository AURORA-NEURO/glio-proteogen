import { describe, expect, it } from "vitest";

import {
  GBM_FACTOR_GRAPH_EDGE_COUNT,
  GBM_FACTOR_GRAPH_NODE_COUNT,
  GBM_FACTOR_GRAPH_TOPOLOGY_DIGEST,
  factorGraphChildResultDigest,
  factorGraphProfileDigest,
  factorGraphRequestDigest,
  factorGraphResultDigest,
  factorGraphRequestStats,
  normalizeFactorGraphKinaseTransitions,
  normalizeFactorGraphResult,
  normalizeFactorGraphTopology,
  validateFactorGraphDemo,
  validateFactorGraphKinaseRequest,
  validateFactorGraphProfile,
  validateFactorGraphProfileHeaders,
  validateFactorGraphRequest,
  validateFactorGraphResult,
  validateFactorGraphResultHeaders,
  validateFactorGraphResultProfileBinding,
  validateFactorGraphResultRequestBinding,
  validateFactorGraphVerification,
  validateFactorGraphVerificationHeaders,
} from "../../src/lib/gbm-factor-graph";
import type { JsonObject } from "../../src/lib/research-state";
import {
  factorGraphAnalysisResult,
  factorGraphDemoRequest,
  factorGraphProfile,
  factorGraphVerification,
} from "../fixtures/gbm-factor-graph";

function cloneObject(value: unknown): JsonObject {
  return structuredClone(value) as JsonObject;
}

function resealNestedChild(
  result: JsonObject,
  childField: "reactome_result" | "kinase_result",
  bindingField: "reactome_child" | "kinase_child",
): void {
  const child = result[childField] as JsonObject;
  child.result_digest = factorGraphChildResultDigest(child);
  const provenance = result.provenance as JsonObject;
  const binding = provenance[bindingField] as JsonObject;
  binding.child_result_digest = child.result_digest;
  result.result_digest = factorGraphResultDigest(result);
}

describe("KNCC GBM factor-graph request validation", () => {
  it("accepts the exact independent nested children and reports both inventories", () => {
    const request = cloneObject(factorGraphDemoRequest);
    expect(validateFactorGraphRequest(request)).toEqual([]);
    expect(factorGraphRequestStats(request)).toEqual({
      reactomeTimePoints: 2,
      reactomeActive: 12,
      kinaseTimePoints: 4,
      kinaseActive: 12,
      childTransitions: 4,
    });
  });

  it("fails closed on outer drift and prefixes strict child errors", () => {
    const request = cloneObject(factorGraphDemoRequest);
    request.profile_id = "latest";
    request.relationship = "fused";
    request.unapproved = true;
    const reactome = request.reactome_request as JsonObject;
    reactome.profile_id = "latest";
    reactome.hidden = "open";
    const kinase = request.kinase_request as JsonObject;
    kinase.profile_id = "latest";
    const points = kinase.time_points as JsonObject[];
    const observation = (points[0].observations as JsonObject[])[0];
    observation.state = "unsupported";

    const errors = validateFactorGraphRequest(request).join("\n");
    expect(errors).toContain("request contains unsupported fields: unapproved");
    expect(errors).toContain("profile_id must equal glio-ecgi-kncc-gbm-transition/1.0.0");
    expect(errors).toContain("relationship must equal independent_parallel_source_cohort_concordance_no_cross_modal_fusion");
    expect(errors).toContain("reactome_request.profile_id must equal kncc-reactome-conditional-transition/1.0.0");
    expect(errors).toContain("reactome_request contains unsupported fields: hidden");
    expect(errors).toContain("kinase_request.profile_id must equal kncc-gbm-longitudinal-kinase-transition/1.0.0");
    expect(errors).toContain("kinase_request.time_points[0].observations[0] missing/unsupported evidence requires no value/error and zero quality");
  });

  it("reuses the exact phosphosite child contract and applies the outer five-point cap", () => {
    const kinase = cloneObject(factorGraphDemoRequest.kinase_request);
    const points = kinase.time_points as JsonObject[];
    const template = points[points.length - 1];
    kinase.time_points = Array.from({ length: 6 }, (_, index) => {
      const point = structuredClone(template);
      point.time_point_id = `factor-kinase-p${index}`;
      point.time_offset_days = index * 30;
      point.observations = (point.observations as JsonObject[]).map((observation, observationIndex) => ({
        ...observation,
        observation_id: `factor-kinase-${index}-${observationIndex}`,
      }));
      return point;
    });
    const errors = validateFactorGraphKinaseRequest(kinase).join("\n");
    expect(errors).toContain("time_points must contain at most 5 entries in the factor-graph lane");

    kinase.assay_compatibility = { unexpected: true };
    expect(validateFactorGraphKinaseRequest(kinase).join("\n")).toContain(
      "assay_compatibility contains unsupported fields: unexpected",
    );
  });

  it("rejects missing or malformed nested child objects without guessing a lane", () => {
    const request = cloneObject(factorGraphDemoRequest);
    request.reactome_request = null;
    request.kinase_request = [];
    request.analysis_id = "9invalid";
    expect(validateFactorGraphRequest(request)).toEqual(expect.arrayContaining([
      "analysis_id must be a valid identifier.",
      "reactome_request must be an object.",
      "kinase_request must be an object.",
    ]));
    expect(factorGraphRequestStats({})).toEqual({
      reactomeTimePoints: 0,
      reactomeActive: 0,
      kinaseTimePoints: 0,
      kinaseActive: 0,
      childTransitions: 0,
    });
  });
});

describe("KNCC GBM factor-graph fail-closed receipt admission", () => {
  it("admits a fully bound profile, demo, result, and replay receipt", () => {
    const profile = cloneObject(factorGraphProfile);
    const request = cloneObject(factorGraphDemoRequest);
    const result = cloneObject(factorGraphAnalysisResult);
    const verification = cloneObject(factorGraphVerification);
    const profileHeaders = new Headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
    });
    const demoHeaders = new Headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
      "X-GLIO-Request-Digest": String(profile.demo_request_digest),
    });
    const resultHeaders = new Headers({
      "X-GLIO-Profile-Digest": String(result.profile_digest),
      "X-GLIO-Request-Digest": String(result.request_digest),
      "X-GLIO-Result-Digest": String(result.result_digest),
    });
    const verificationHeaders = new Headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
      "X-GLIO-Request-Digest": String(verification.recomputed_request_digest),
      "X-GLIO-Result-Digest": String(verification.recomputed_result_digest),
    });

    expect(validateFactorGraphProfile(profile)).toEqual([]);
    expect(factorGraphProfileDigest(profile)).toBe(profile.profile_digest);
    expect(factorGraphRequestDigest(request)).toBe(result.request_digest);
    expect(factorGraphResultDigest(result)).toBe(result.result_digest);
    expect(validateFactorGraphProfileHeaders(profileHeaders, profile)).toEqual([]);
    expect(validateFactorGraphDemo(request, demoHeaders, profile)).toEqual([]);
    expect(validateFactorGraphResult(result)).toEqual([]);
    expect(validateFactorGraphResultRequestBinding(result, request)).toEqual([]);
    expect(validateFactorGraphResultProfileBinding(result, profile)).toEqual([]);
    expect(validateFactorGraphResultHeaders(resultHeaders, result, request, profile)).toEqual([]);
    expect(validateFactorGraphVerification(verification, result, profile)).toEqual([]);
    expect(validateFactorGraphVerificationHeaders(
      verificationHeaders,
      verification,
      profile,
    )).toEqual([]);
  });

  it("rejects non-demo payloads and profile or digest-header drift before admission", () => {
    const profile = cloneObject(factorGraphProfile);
    const nonDemo = cloneObject(factorGraphDemoRequest);
    nonDemo.analysis_id = "different-valid-demo-id";
    const wrongProfileHeader = `sha256:${"a".repeat(64)}`;
    const wrongRequestHeader = `sha256:${"b".repeat(64)}`;
    const errors = validateFactorGraphDemo(
      nonDemo,
      new Headers({
        "X-GLIO-Profile-Digest": wrongProfileHeader,
        "X-GLIO-Request-Digest": wrongRequestHeader,
      }),
      profile,
    ).join("\n");
    expect(errors).toContain("demo request.analysis_id must match the admitted profile.demo_id");
    expect(errors).toContain("X-GLIO-Profile-Digest response header must match the admitted payload");
    expect(errors).toContain("X-GLIO-Request-Digest response header must match the admitted payload");

    const driftedProfile = cloneObject(factorGraphProfile);
    driftedProfile.model_id = "latest";
    delete driftedProfile.source_attestation_state;
    const profileErrors = validateFactorGraphProfile(driftedProfile).join("\n");
    expect(profileErrors).toContain("profile algorithm/model identity is invalid");
    expect(profileErrors).toContain("profile is missing required fields: source_attestation_state");
    expect(validateFactorGraphProfileHeaders(new Headers(), profile)).toContain(
      "X-GLIO-Profile-Digest response header must be a lowercase sha256 digest.",
    );
  });

  it("reports every locked profile safety, inventory, and child-attestation violation", () => {
    const profile = cloneObject(factorGraphProfile);
    profile.relationship = "learned_cross_modal_fusion";
    profile.reactome_child = null;
    const kinaseChild = profile.kinase_child as JsonObject;
    kinaseChild.block = "protein_reactome";
    kinaseChild.child_profile_id = "latest";
    for (const field of [
      "child_profile_digest",
      "source_digest",
      "fitted_digest",
      "bootstrap_digest",
      "evaluation_digest",
    ]) kinaseChild[field] = "not-a-digest";
    for (const field of [
      "profile_digest",
      "topology_digest",
      "source_inventory_digest",
      "composition_semantic_digest",
      "demo_request_digest",
      "demo_semantic_oracle_digest",
    ]) profile[field] = "not-a-digest";
    profile.limits = null;
    profile.counts = null;
    profile.numpy_version = "latest";
    profile.demo_id = "unbound-demo";
    profile.source_attestation_state = "unverified";
    profile.safety_class = "clinical";
    profile.claim_ceiling = "causal";
    profile.research_use_only = false;
    profile.non_prescriptive = false;
    profile.independent_parallel_blocks = false;
    profile.cross_modal_fusion_performed = true;
    profile.no_numerical_cross_block_edges = false;

    const errors = validateFactorGraphProfile(profile).join("\n");
    expect(errors).toContain("profile.relationship must equal");
    expect(errors).toContain("profile.reactome_child must be an object");
    expect(errors).toContain("profile.kinase_child.block must equal phosphosite_sphinks");
    expect(errors).toContain("profile.kinase_child.child_profile_id must equal");
    expect(errors).toContain("profile.kinase_child.child_profile_digest must be a lowercase sha256 digest");
    expect(errors).toContain("profile.profile_digest must be a lowercase sha256 digest");
    expect(errors).toContain("profile.limits must be an object");
    expect(errors).toContain("profile.counts must be an object");
    expect(errors).toContain("profile.numpy_version must equal the locked 2.5.2 runtime");
    expect(errors).toContain("profile.demo_id must equal");
    expect(errors).toContain("profile.source_attestation_state must affirm the exact child snapshots");
    expect(errors).toContain("profile exceeds or differs from the admitted source-cohort claim ceiling");
    expect(errors).toContain("profile must preserve the research-only independent no-fusion boundary");

    const inventoryDrift = cloneObject(factorGraphProfile);
    (inventoryDrift.limits as JsonObject).maximum_result_bytes = 1;
    (inventoryDrift.counts as JsonObject).kinase_signature_factors = 23;
    const inventoryErrors = validateFactorGraphProfile(inventoryDrift).join("\n");
    expect(inventoryErrors).toContain("profile.limits does not match the version-locked factor-graph transport boundary");
    expect(inventoryErrors).toContain("profile.counts does not match the version-locked factor inventory");
  });

  it("rejects request, child, profile, and authoritative analysis-header mismatches", () => {
    const request = cloneObject(factorGraphDemoRequest);
    const result = cloneObject(factorGraphAnalysisResult);
    result.analysis_id = "another-analysis";
    const kinaseResult = result.kinase_result as JsonObject;
    kinaseResult.time_point_ids = ["wrong-0", "wrong-1"];
    const bindingErrors = validateFactorGraphResultRequestBinding(result, request).join("\n");
    expect(bindingErrors).toContain("result.analysis_id must match the submitted request");
    expect(bindingErrors).toContain(
      "result.kinase_result.time_point_ids must exactly match the submitted child request order",
    );

    const profile = cloneObject(factorGraphProfile);
    const provenance = result.provenance as JsonObject;
    provenance.source_inventory_digest = `sha256:${"f".repeat(64)}`;
    expect(validateFactorGraphResultProfileBinding(result, profile).join("\n")).toContain(
      "result.provenance.source_inventory_digest must match the admitted loaded profile",
    );
    expect(validateFactorGraphResultHeaders(new Headers({
      "X-GLIO-Profile-Digest": String(result.profile_digest),
      "X-GLIO-Request-Digest": String(result.request_digest),
      "X-GLIO-Result-Digest": `sha256:${"0".repeat(64)}`,
    }), result, request, profile)).toContain(
      "X-GLIO-Result-Digest response header must match the admitted payload.",
    );
  });

  it("rejects malformed outer and independently computed child result envelopes", () => {
    const outer = cloneObject(factorGraphAnalysisResult);
    outer.algorithm_id = "latest";
    outer.algorithm_version = "2.0.0";
    outer.profile_id = "latest";
    outer.analysis_id = "9invalid";
    outer.relationship = "fused";
    for (const field of ["profile_digest", "topology_digest", "request_digest", "result_digest"]) {
      outer[field] = "not-a-digest";
    }
    outer.research_use_only = false;
    outer.non_prescriptive = false;
    outer.independent_parallel_blocks = false;
    outer.limitations = [""];
    outer.reactome_result = null;
    outer.kinase_result = null;
    outer.provenance = null;
    const outerErrors = validateFactorGraphResult(outer).join("\n");
    expect(outerErrors).toContain("result.algorithm_id is invalid");
    expect(outerErrors).toContain("result.algorithm_version must equal 1.0.0");
    expect(outerErrors).toContain("result.profile_id must equal");
    expect(outerErrors).toContain("result.analysis_id must be a valid identifier");
    expect(outerErrors).toContain("result.relationship must equal");
    expect(outerErrors).toContain("result.profile_digest must be a lowercase sha256 digest");
    expect(outerErrors).toContain("result must remain research-only, non-prescriptive, and independently parallel");
    expect(outerErrors).toContain("result.limitations must contain 6 through 20 non-empty strings");
    expect(outerErrors).toContain("result.reactome_result must be an object");
    expect(outerErrors).toContain("result.kinase_result must be an object");
    expect(outerErrors).toContain("result.provenance must be an object");

    const malformedReactome = cloneObject(factorGraphAnalysisResult);
    const reactome = malformedReactome.reactome_result as JsonObject;
    reactome.algorithm_id = "latest";
    reactome.algorithm_version = "2.0.0";
    reactome.profile_id = "latest";
    reactome.profile_digest = "invalid";
    reactome.request_digest = "invalid";
    reactome.result_digest = "invalid";
    reactome.series_id = "9invalid";
    reactome.assay_compatibility = null;
    reactome.normalization_reference = null;
    reactome.provenance = null;
    reactome.limitations = [];
    reactome.research_use_only = false;
    reactome.non_prescriptive = false;
    reactome.output_semantics = "clinical_prediction";
    reactome.validation_scope = "external_validation";
    reactome.time_point_ids = ["duplicate", "duplicate"];
    reactome.transitions = [null];
    const reactomeErrors = validateFactorGraphResult(malformedReactome).join("\n");
    expect(reactomeErrors).toContain("result.reactome_result.algorithm_id must equal");
    expect(reactomeErrors).toContain("result.reactome_result.algorithm_version must equal 1.0.0");
    expect(reactomeErrors).toContain("result.reactome_result.series_id must be a valid identifier");
    expect(reactomeErrors).toContain("result.reactome_result.assay_compatibility must be an object");
    expect(reactomeErrors).toContain("result.reactome_result.normalization_reference must be an object");
    expect(reactomeErrors).toContain("result.reactome_result.provenance must be an object");
    expect(reactomeErrors).toContain("result.reactome_result.limitations must contain 6 through 20 non-empty strings");
    expect(reactomeErrors).toContain("result.reactome_result must remain research-use-only and non-prescriptive");
    expect(reactomeErrors).toContain("result.reactome_result.output_semantics exceeds the Reactome concordance-only boundary");
    expect(reactomeErrors).toContain("result.reactome_result.validation_scope must remain same-cohort and non-external");
    expect(reactomeErrors).toContain("result.reactome_result.profile_digest must be a lowercase sha256 digest");
    expect(reactomeErrors).toContain("result.reactome_result.time_point_ids must contain 2 through 5 unique identifiers");
    expect(reactomeErrors).toContain("result.reactome_result.transitions[0] must be an object");

    const malformedKinase = cloneObject(factorGraphAnalysisResult);
    const kinase = malformedKinase.kinase_result as JsonObject;
    kinase.algorithm_id = "latest";
    kinase.algorithm_version = "2.0.0";
    kinase.profile_id = "latest";
    kinase.profile_digest = "invalid";
    kinase.request_digest = "invalid";
    kinase.result_digest = "invalid";
    kinase.series_id = "9invalid";
    kinase.assay_compatibility = null;
    kinase.normalization_reference = null;
    kinase.provenance = null;
    kinase.limitations = [];
    kinase.research_use_only = false;
    kinase.non_prescriptive = false;
    kinase.output_semantics = "kinase_activity";
    kinase.infers_biochemical_activity = true;
    kinase.time_point_ids = ["only-one"];
    kinase.transitions = [];
    const kinaseErrors = validateFactorGraphResult(malformedKinase).join("\n");
    expect(kinaseErrors).toContain("result.kinase_result.algorithm_id must equal");
    expect(kinaseErrors).toContain("result.kinase_result.output_semantics exceeds the SPHINKS concordance-only boundary");
    expect(kinaseErrors).toContain("result.kinase_result.infers_biochemical_activity must remain false");
    expect(kinaseErrors).toContain("result.kinase_result.time_point_ids must contain 2 through 5 unique identifiers");
  });

  it("closes request, profile, child-provenance, and replay bindings independently", () => {
    const request = cloneObject(factorGraphDemoRequest);
    request.profile_id = "request-profile";
    request.relationship = "request-relationship";
    const result = cloneObject(factorGraphAnalysisResult);
    result.profile_id = "result-profile";
    result.relationship = "result-relationship";
    const reactome = result.reactome_result as JsonObject;
    reactome.series_id = "different-series";
    reactome.profile_id = "different-profile";
    reactome.assay_compatibility = { platform: "different" };
    reactome.normalization_reference = { method: "different" };
    reactome.time_point_ids = ["different-p0", "different-p1"];
    const requestErrors = validateFactorGraphResultRequestBinding(result, request).join("\n");
    expect(requestErrors).toContain("result.profile_id must match the submitted request");
    expect(requestErrors).toContain("result.relationship must match the submitted request");
    expect(requestErrors).toContain("result.reactome_result.series_id must match the submitted child request");
    expect(requestErrors).toContain("result.reactome_result.profile_id must match the submitted child request");
    expect(requestErrors).toContain("result.reactome_result.assay_compatibility must exactly match the submitted child request");
    expect(requestErrors).toContain("result.reactome_result.normalization_reference must exactly match the submitted child request");
    expect(requestErrors).toContain("result.reactome_result.time_point_ids must exactly match the submitted child request order");

    const invalidDigestProfile = cloneObject(factorGraphProfile);
    invalidDigestProfile.profile_digest = "invalid";
    expect(validateFactorGraphResultProfileBinding(
      cloneObject(factorGraphAnalysisResult),
      invalidDigestProfile,
    )).toContain("loaded profile.profile_digest must be a lowercase sha256 digest.");

    const topologyMismatchResult = cloneObject(factorGraphAnalysisResult);
    topologyMismatchResult.topology_digest = `sha256:${"e".repeat(64)}`;
    expect(validateFactorGraphResultProfileBinding(
      topologyMismatchResult,
      cloneObject(factorGraphProfile),
    )).toContain("result.topology_digest must match the admitted loaded profile topology digest.");

    const childProfileMismatch = cloneObject(factorGraphAnalysisResult);
    const childBinding = ((childProfileMismatch.provenance as JsonObject).reactome_child as JsonObject);
    childBinding.child_profile_digest = `sha256:${"e".repeat(64)}`;
    expect(validateFactorGraphResultProfileBinding(
      childProfileMismatch,
      cloneObject(factorGraphProfile),
    )).toContain("result.provenance.reactome_child must match the admitted child profile binding.");

    const verification = cloneObject(factorGraphVerification);
    verification.recomputed_request_digest = `sha256:${"e".repeat(64)}`;
    verification.recomputed_result_digest = `sha256:${"e".repeat(64)}`;
    const driftedResult = cloneObject(factorGraphAnalysisResult);
    driftedResult.profile_digest = `sha256:${"e".repeat(64)}`;
    driftedResult.topology_digest = `sha256:${"e".repeat(64)}`;
    (driftedResult.provenance as JsonObject).source_inventory_digest = `sha256:${"e".repeat(64)}`;
    const verificationErrors = validateFactorGraphVerification(
      verification,
      driftedResult,
      cloneObject(factorGraphProfile),
    ).join("\n");
    expect(verificationErrors).toContain("verification recomputed request digest does not match the admitted result binding");
    expect(verificationErrors).toContain("verification recomputed result digest does not match the admitted result");
    expect(verificationErrors).toContain("verification profile match does not close the admitted result/profile binding");
    expect(verificationErrors).toContain("verification topology match does not close the admitted result/profile binding");
    expect(verificationErrors).toContain("verification source-inventory match does not close the admitted result/profile binding");
  });

  it("binds child results after applying legal normalization-reference defaults", () => {
    const request = cloneObject(factorGraphDemoRequest);
    for (const childField of ["reactome_request", "kinase_request"] as const) {
      const child = request[childField] as JsonObject;
      const reference = child.normalization_reference as JsonObject;
      delete reference.abundance_scale;
      delete reference.invariant_across_time_points;
    }
    const result = cloneObject(factorGraphAnalysisResult);
    expect(validateFactorGraphRequest(request)).toEqual([]);
    expect(factorGraphRequestDigest(request)).toBe(result.request_digest);
    expect(validateFactorGraphResultRequestBinding(result, request)).toEqual([]);
  });

  it("recomputes each nested child digest before admitting the outer receipt", () => {
    const changed = cloneObject(factorGraphAnalysisResult);
    const kinase = changed.kinase_result as JsonObject;
    const transition = (kinase.transitions as JsonObject[])[0];
    transition.score = 0.987654;
    changed.result_digest = factorGraphResultDigest(changed);
    expect(validateFactorGraphResult(changed)).toContain(
      "result.kinase_result.result_digest must match canonical nested child content.",
    );
  });

  it.each([
    "infers_kinase_activity",
    "makes_causal_claim",
    "independent_evidence",
  ] as const)("rejects resealed kinase child safety drift in %s", (field) => {
    const changed = cloneObject(factorGraphAnalysisResult);
    const kinase = changed.kinase_result as JsonObject;
    kinase[field] = true;
    resealNestedChild(changed, "kinase_result", "kinase_child");
    expect(validateFactorGraphResult(changed)).toContain(
      `result.kinase_result.${field} must remain false.`,
    );
  });

  it("rejects resealed malformed nested scientific evidence and Reactome claim drift", () => {
    const malformedKinase = cloneObject(factorGraphAnalysisResult);
    const kinase = malformedKinase.kinase_result as JsonObject;
    const transition = (kinase.transitions as JsonObject[])[0];
    const signature = (transition.kinase_signatures as JsonObject[])
      .find((item) => (item.top_family_drivers as JsonObject[]).length > 0);
    if (!signature) throw new Error("fixture must include a kinase signature driver");
    ((signature.top_family_drivers as JsonObject[])[0]).inverse_multiplicity = -1;
    resealNestedChild(malformedKinase, "kinase_result", "kinase_child");
    expect(validateFactorGraphResult(malformedKinase).join("\n")).toContain(
      "contains malformed or incomplete child results",
    );

    const malformedReactome = cloneObject(factorGraphAnalysisResult);
    const reactome = malformedReactome.reactome_result as JsonObject;
    reactome.validation_scope = "external_clinical_validation";
    const reactomeTransition = (reactome.transitions as JsonObject[])[0];
    delete reactomeTransition.global_recurrence;
    resealNestedChild(malformedReactome, "reactome_result", "reactome_child");
    const errors = validateFactorGraphResult(malformedReactome).join("\n");
    expect(errors).toContain(
      "result.reactome_result.validation_scope must remain same-cohort and non-external.",
    );
    expect(errors).toContain(
      "result.reactome_result.transitions contains malformed or incomplete Reactome child results.",
    );
  });

  it("rejects unchanged digest headers when profile, demo, result, or executed request content changes", () => {
    const profile = cloneObject(factorGraphProfile);
    const profileHeaders = new Headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
    });
    const reactomeChild = profile.reactome_child as JsonObject;
    reactomeChild.source_digest = `sha256:${"f".repeat(64)}`;
    expect(validateFactorGraphProfile(profile)).toContain(
      "profile.profile_digest must match canonical profile content.",
    );
    expect(validateFactorGraphProfileHeaders(profileHeaders, profile)).toContain(
      "X-GLIO-Profile-Digest response header must match the admitted payload.",
    );

    const admittedProfile = cloneObject(factorGraphProfile);
    const demo = cloneObject(factorGraphDemoRequest);
    const demoHeaders = new Headers({
      "X-GLIO-Profile-Digest": String(admittedProfile.profile_digest),
      "X-GLIO-Request-Digest": String(admittedProfile.demo_request_digest),
    });
    const demoReactome = demo.reactome_request as JsonObject;
    demoReactome.bootstrap_replicates = 32;
    const demoErrors = validateFactorGraphDemo(demo, demoHeaders, admittedProfile);
    expect(demoErrors).toContain(
      "profile.demo_request_digest must match canonical demo request content.",
    );
    expect(demoErrors).toContain(
      "X-GLIO-Request-Digest response header must match the admitted payload.",
    );

    const request = cloneObject(factorGraphDemoRequest);
    const result = cloneObject(factorGraphAnalysisResult);
    const resultHeaders = new Headers({
      "X-GLIO-Profile-Digest": String(result.profile_digest),
      "X-GLIO-Request-Digest": String(result.request_digest),
      "X-GLIO-Result-Digest": String(result.result_digest),
    });
    (result.limitations as string[])[0] = "Mutated result content with an unchanged receipt.";
    expect(validateFactorGraphResult(result)).toContain(
      "result.result_digest must match canonical result content.",
    );
    expect(validateFactorGraphResultHeaders(
      resultHeaders,
      result,
      request,
      admittedProfile,
    )).toContain(
      "X-GLIO-Result-Digest response header must match the admitted payload.",
    );

    const changedRequest = cloneObject(factorGraphDemoRequest);
    const changedKinase = changedRequest.kinase_request as JsonObject;
    changedKinase.bootstrap_replicates = 32;
    expect(validateFactorGraphResultRequestBinding(
      cloneObject(factorGraphAnalysisResult),
      changedRequest,
    )).toContain(
      "result.request_digest must match the canonical submitted request.",
    );
  });

  it("enforces Boolean semantic closure and rejects a bare verified flag", () => {
    const result = cloneObject(factorGraphAnalysisResult);
    const profile = cloneObject(factorGraphProfile);
    const bareErrors = validateFactorGraphVerification(
      { verified: true },
      result,
      profile,
    ).join("\n");
    expect(bareErrors).toContain("verification is missing required fields");
    expect(bareErrors).toContain("verification.request_digest_match must be Boolean");
    expect(bareErrors).toContain("verification.recomputed_request_digest must be a lowercase sha256 digest");
    expect(bareErrors).toContain("verification.verified does not close all digest and semantic checks");

    const contradictory = cloneObject(factorGraphVerification);
    contradictory.reactome_child_verified = false;
    contradictory.semantic_match = false;
    contradictory.verified = true;
    expect(validateFactorGraphVerification(contradictory, result, profile)).toContain(
      "verification.verified does not close all digest and semantic checks.",
    );

    const nonBoolean = cloneObject(factorGraphVerification);
    nonBoolean.provenance_match = 1;
    expect(validateFactorGraphVerification(nonBoolean, result, profile)).toContain(
      "verification.provenance_match must be Boolean.",
    );

    expect(validateFactorGraphVerificationHeaders(new Headers({
      "X-GLIO-Profile-Digest": String(profile.profile_digest),
      "X-GLIO-Request-Digest": String(factorGraphVerification.recomputed_request_digest),
      "X-GLIO-Result-Digest": `sha256:${"0".repeat(64)}`,
    }), cloneObject(factorGraphVerification), profile)).toContain(
      "X-GLIO-Result-Digest response header must match the admitted payload.",
    );
  });
});

describe("KNCC GBM factor topology normalization", () => {
  it("admits only the complete two-column annotation inventory", () => {
    const topology = normalizeFactorGraphTopology(cloneObject(factorGraphProfile));
    expect(topology).not.toBeNull();
    expect(topology?.nodes).toHaveLength(GBM_FACTOR_GRAPH_NODE_COUNT);
    expect(topology?.containmentEdges).toHaveLength(GBM_FACTOR_GRAPH_EDGE_COUNT);
    expect(topology?.digest).toBe(GBM_FACTOR_GRAPH_TOPOLOGY_DIGEST);
    expect(topology?.nodes.filter((node) => node.kind === "computation_block")).toHaveLength(2);
    expect(topology?.nodes.filter((node) => node.kind === "reactome_pathway_factor")).toHaveLength(10);
    expect(topology?.nodes.filter((node) => node.kind === "kinase_signature_factor")).toHaveLength(24);
    expect(topology?.nodes.filter((node) => node.kind === "subtype_signature_factor")).toHaveLength(4);
    expect(topology?.containmentEdges.every((edge) => edge.computationalRole === "annotation_only" && edge.numericalWeight === null)).toBe(true);
    expect(topology?.numericalCrossBlockEdgeCount).toBe(0);
  });

  it("fails closed on count, cross-block, numerical, digest, identity, and unknown-field drift", () => {
    const cases: JsonObject[] = [];

    const missingNode = cloneObject(factorGraphProfile);
    ((missingNode.topology as JsonObject).nodes as unknown[]).pop();
    cases.push(missingNode);

    const crossBlock = cloneObject(factorGraphProfile);
    const crossTopology = crossBlock.topology as JsonObject;
    const edges = crossTopology.containment_edges as JsonObject[];
    edges[0].source_node_id = "block.phosphosite_sphinks";
    cases.push(crossBlock);

    const numerical = cloneObject(factorGraphProfile);
    ((numerical.topology as JsonObject).containment_edges as JsonObject[])[0].numerical_weight = 0.1;
    cases.push(numerical);

    const digestMismatch = cloneObject(factorGraphProfile);
    digestMismatch.topology_digest = `sha256:${"f".repeat(64)}`;
    cases.push(digestMismatch);

    const forgedDigest = cloneObject(factorGraphProfile);
    forgedDigest.topology_digest = `sha256:${"e".repeat(64)}`;
    (forgedDigest.topology as JsonObject).topology_digest = forgedDigest.topology_digest;
    cases.push(forgedDigest);

    const wrongKindBlock = cloneObject(factorGraphProfile);
    const wrongKindNodes = (wrongKindBlock.topology as JsonObject).nodes as JsonObject[];
    const kinaseNode = wrongKindNodes.find((node) => node.kind === "kinase_signature_factor");
    if (!kinaseNode) throw new Error("fixture must include a kinase-signature node");
    kinaseNode.block = "protein_reactome";
    kinaseNode.child_profile_id = factorGraphDemoRequest.reactome_request.profile_id;
    cases.push(wrongKindBlock);

    const duplicate = cloneObject(factorGraphProfile);
    const duplicateNodes = (duplicate.topology as JsonObject).nodes as JsonObject[];
    duplicateNodes[1].node_id = duplicateNodes[0].node_id;
    cases.push(duplicate);

    const extra = cloneObject(factorGraphProfile);
    ((extra.topology as JsonObject).nodes as JsonObject[])[0].fusion_weight = 0;
    cases.push(extra);

    for (const invalid of cases) expect(normalizeFactorGraphTopology(invalid)).toBeNull();
    expect(normalizeFactorGraphTopology(null)).toBeNull();
  });

  it("rejects every malformed node, edge, and aggregate containment invariant", () => {
    const cases: Array<[string, (profile: JsonObject) => void]> = [
      ["unknown topology field", (profile) => {
        (profile.topology as JsonObject).learned_cross_block_weight = 0;
      }],
      ["topology identity", (profile) => {
        (profile.topology as JsonObject).topology_id = "latest";
      }],
      ["containment role", (profile) => {
        (profile.topology as JsonObject).containment_edge_role = "numerical";
      }],
      ["numerical cross-block count", (profile) => {
        (profile.topology as JsonObject).numerical_cross_block_edge_count = 1;
      }],
      ["cross-block edge inventory", (profile) => {
        (profile.topology as JsonObject).cross_block_edges = [{ edge_id: "forbidden" }];
      }],
      ["profile/topology digest disagreement", (profile) => {
        profile.topology_digest = `sha256:${"a".repeat(64)}`;
      }],
      ["non-object node", (profile) => {
        ((profile.topology as JsonObject).nodes as unknown[])[2] = null;
      }],
      ["invalid node identifier", (profile) => {
        ((profile.topology as JsonObject).nodes as JsonObject[])[2].node_id = "9invalid";
      }],
      ["invalid node block", (profile) => {
        ((profile.topology as JsonObject).nodes as JsonObject[])[2].block = "fused";
      }],
      ["invalid node kind", (profile) => {
        ((profile.topology as JsonObject).nodes as JsonObject[])[2].kind = "joint_factor";
      }],
      ["missing biological identifier", (profile) => {
        ((profile.topology as JsonObject).nodes as JsonObject[])[2].biological_identifier = "";
      }],
      ["missing node label", (profile) => {
        ((profile.topology as JsonObject).nodes as JsonObject[])[2].label = "";
      }],
      ["missing child profile", (profile) => {
        ((profile.topology as JsonObject).nodes as JsonObject[])[2].child_profile_id = "";
      }],
      ["invalid learned semantics", (profile) => {
        ((profile.topology as JsonObject).nodes as JsonObject[])[2].learned_semantics = "cross_modal_fit";
      }],
      ["wrong child profile", (profile) => {
        ((profile.topology as JsonObject).nodes as JsonObject[])[2].child_profile_id = "latest";
      }],
      ["kind/block disagreement", (profile) => {
        const node = ((profile.topology as JsonObject).nodes as JsonObject[])[2];
        node.block = "phosphosite_sphinks";
        node.child_profile_id = "kncc-gbm-longitudinal-kinase-transition/1.0.0";
      }],
      ["container semantics on a fitted factor", (profile) => {
        ((profile.topology as JsonObject).nodes as JsonObject[])[2].learned_semantics = "child_result_container_only";
      }],
      ["invalid Reactome identifier", (profile) => {
        const nodes = (profile.topology as JsonObject).nodes as JsonObject[];
        const node = nodes.find((item) => item.kind === "reactome_pathway_factor");
        if (!node) throw new Error("fixture must contain a Reactome factor");
        node.biological_identifier = "R-HSA-0";
      }],
      ["invalid kinase identifier", (profile) => {
        const nodes = (profile.topology as JsonObject).nodes as JsonObject[];
        const node = nodes.find((item) => item.kind === "kinase_signature_factor");
        if (!node) throw new Error("fixture must contain a kinase factor");
        node.biological_identifier = "egfr";
      }],
      ["invalid subtype identifier", (profile) => {
        const nodes = (profile.topology as JsonObject).nodes as JsonObject[];
        const node = nodes.find((item) => item.kind === "subtype_signature_factor");
        if (!node) throw new Error("fixture must contain a subtype factor");
        node.biological_identifier = "MES";
      }],
      ["non-object edge", (profile) => {
        ((profile.topology as JsonObject).containment_edges as unknown[])[0] = false;
      }],
      ["unknown edge field", (profile) => {
        ((profile.topology as JsonObject).containment_edges as JsonObject[])[0].coefficient = 0;
      }],
      ["invalid edge identifier", (profile) => {
        ((profile.topology as JsonObject).containment_edges as JsonObject[])[0].edge_id = "9invalid";
      }],
      ["invalid source identifier", (profile) => {
        ((profile.topology as JsonObject).containment_edges as JsonObject[])[0].source_node_id = "9invalid";
      }],
      ["invalid target identifier", (profile) => {
        ((profile.topology as JsonObject).containment_edges as JsonObject[])[0].target_node_id = "9invalid";
      }],
      ["invalid edge relationship", (profile) => {
        ((profile.topology as JsonObject).containment_edges as JsonObject[])[0].relationship = "activates";
      }],
      ["invalid computational role", (profile) => {
        ((profile.topology as JsonObject).containment_edges as JsonObject[])[0].computational_role = "fitted";
      }],
      ["duplicate edge identifier", (profile) => {
        const edges = (profile.topology as JsonObject).containment_edges as JsonObject[];
        edges[1].edge_id = edges[0].edge_id;
      }],
      ["wrong factor inventory", (profile) => {
        const nodes = (profile.topology as JsonObject).nodes as JsonObject[];
        nodes[2].kind = "reactome_pathway_factor";
        nodes[2].biological_identifier = "R-HSA-177929";
      }],
      ["duplicate computation block", (profile) => {
        const nodes = (profile.topology as JsonObject).nodes as JsonObject[];
        nodes[1].block = "protein_reactome";
        nodes[1].child_profile_id = nodes[0].child_profile_id;
      }],
      ["unresolved source", (profile) => {
        ((profile.topology as JsonObject).containment_edges as JsonObject[])[0].source_node_id = "block.missing";
      }],
      ["factor used as source", (profile) => {
        const edges = (profile.topology as JsonObject).containment_edges as JsonObject[];
        edges[0].source_node_id = edges[1].target_node_id;
      }],
      ["computation block used as target", (profile) => {
        ((profile.topology as JsonObject).containment_edges as JsonObject[])[0].target_node_id = "block.protein_reactome";
      }],
      ["duplicate containment target", (profile) => {
        const edges = (profile.topology as JsonObject).containment_edges as JsonObject[];
        edges[1].target_node_id = edges[0].target_node_id;
      }],
    ];

    for (const [name, mutate] of cases) {
      const profile = cloneObject(factorGraphProfile);
      mutate(profile);
      expect(normalizeFactorGraphTopology(profile), name).toBeNull();
    }

    const malformedWrapper = cloneObject(factorGraphProfile);
    malformedWrapper.topology = [];
    expect(normalizeFactorGraphTopology(malformedWrapper)).toBeNull();
  });
});

describe("KNCC GBM factor-graph nested result normalization", () => {
  it("retains all ten Reactome and all 24-kinase/four-subtype child families", () => {
    const result = cloneObject(factorGraphAnalysisResult);
    expect(validateFactorGraphResult(result)).toEqual([]);
    const normalized = normalizeFactorGraphResult(result);
    expect(normalized).not.toBeNull();
    expect(normalized?.reactomeTransitions).toHaveLength(1);
    expect(normalized?.reactomeTransitions[0].pathways).toHaveLength(10);
    expect(normalized?.kinaseTransitions).toHaveLength(3);
    expect(normalized?.kinaseTransitions[0].kinaseSignatures).toHaveLength(24);
    expect(normalized?.kinaseTransitions[0].subtypeSignatures.map((item) => item.subtype)).toEqual([
      "GPM", "MTC", "NEU", "PPR",
    ]);
    expect(normalized?.kinaseTransitions[0].ablations).toHaveLength(3);
    expect(normalized?.kinaseTransitions[0].kinaseSignatures.find((item) => item.kinase === "GSK3B")).toMatchObject({
      support: "limited",
      selectionState: "selected_core",
      score: 0.31,
    });
    expect(validateFactorGraphResultProfileBinding(result, cloneObject(factorGraphProfile))).toEqual([]);
  });

  it("binds results to the admitted loaded profile and its exact topology", () => {
    const result = cloneObject(factorGraphAnalysisResult);

    const profileDigestDrift = cloneObject(factorGraphProfile);
    profileDigestDrift.profile_digest = `sha256:${"c".repeat(64)}`;
    expect(validateFactorGraphResultProfileBinding(result, profileDigestDrift)).toContain(
      "result.profile_digest must match the loaded profile.profile_digest.",
    );

    const inadmissibleTopology = cloneObject(factorGraphProfile);
    (inadmissibleTopology.topology as JsonObject).topology_digest = `sha256:${"e".repeat(64)}`;
    expect(validateFactorGraphResultProfileBinding(result, inadmissibleTopology)).toContain(
      "loaded profile topology was not admitted by the version-locked factor topology validator.",
    );

    const resultTopologyDrift = cloneObject(factorGraphAnalysisResult);
    resultTopologyDrift.topology_digest = `sha256:${"e".repeat(64)}`;
    expect(validateFactorGraphResult(resultTopologyDrift)).toContain(
      "result.topology_digest must equal the version-locked factor topology digest.",
    );
  });

  it("rejects missing, fractional, or out-of-range kinase transition counts", () => {
    const missing = cloneObject(factorGraphAnalysisResult);
    const missingKinase = missing.kinase_result as JsonObject;
    const missingTransition = (missingKinase.transitions as JsonObject[])[0];
    delete missingTransition.exact_family_count;
    expect(validateFactorGraphResult(missing).join("\n")).toContain(
      "contains malformed or incomplete child results",
    );

    const fractional = cloneObject(factorGraphAnalysisResult);
    const fractionalKinase = fractional.kinase_result as JsonObject;
    const fractionalTransition = (fractionalKinase.transitions as JsonObject[])[0];
    fractionalTransition.selected_kinase_count = 11.5;
    expect(normalizeFactorGraphKinaseTransitions(fractionalKinase)).toHaveLength(2);

    const nestedFractional = cloneObject(factorGraphAnalysisResult);
    const nestedKinase = nestedFractional.kinase_result as JsonObject;
    const nestedTransition = (nestedKinase.transitions as JsonObject[])[0];
    const nestedSignature = (nestedTransition.kinase_signatures as JsonObject[])[0];
    nestedSignature.mapped_source_family_count = 2.25;
    expect(normalizeFactorGraphKinaseTransitions(nestedKinase)).toHaveLength(2);

    const outOfRangeSubtype = cloneObject(factorGraphAnalysisResult);
    const outOfRangeKinase = outOfRangeSubtype.kinase_result as JsonObject;
    const outOfRangeTransition = (outOfRangeKinase.transitions as JsonObject[])[0];
    const subtype = (outOfRangeTransition.subtype_signatures as JsonObject[])[0];
    subtype.estimable_kinase_count = 10;
    expect(normalizeFactorGraphKinaseTransitions(outOfRangeKinase)).toHaveLength(2);

    const missingBootstrapCount = cloneObject(factorGraphAnalysisResult);
    const missingBootstrapKinase = missingBootstrapCount.kinase_result as JsonObject;
    const missingBootstrapTransition = (missingBootstrapKinase.transitions as JsonObject[])[0];
    const abstainedSignature = (missingBootstrapTransition.kinase_signatures as JsonObject[])
      .find((signature) => signature.support === "abstained");
    if (!abstainedSignature) throw new Error("fixture must include an abstained kinase signature");
    const missingBootstrapUncertainty = structuredClone(abstainedSignature.uncertainty) as JsonObject;
    delete missingBootstrapUncertainty.bootstrap_replicates_used;
    abstainedSignature.uncertainty = missingBootstrapUncertainty;
    expect(normalizeFactorGraphKinaseTransitions(missingBootstrapKinase)).toHaveLength(2);
  });

  it("rejects no-fusion drift, child-binding mismatch, malformed signatures, and unknown outer fields", () => {
    const noFusionDrift = cloneObject(factorGraphAnalysisResult);
    noFusionDrift.cross_modal_fusion_performed = true;
    expect(validateFactorGraphResult(noFusionDrift).join("\n")).toContain(
      "no cross-modal fusion and zero numerical cross-block edges",
    );
    expect(normalizeFactorGraphResult(noFusionDrift)).toBeNull();

    const bindingMismatch = cloneObject(factorGraphAnalysisResult);
    const provenance = bindingMismatch.provenance as JsonObject;
    const kinaseBinding = provenance.kinase_child as JsonObject;
    kinaseBinding.child_result_digest = `sha256:${"f".repeat(64)}`;
    expect(validateFactorGraphResult(bindingMismatch).join("\n")).toContain(
      "child_result_digest must match result_digest on the nested child result",
    );

    const malformed = cloneObject(factorGraphAnalysisResult);
    const kinaseResult = malformed.kinase_result as JsonObject;
    const transitions = kinaseResult.transitions as JsonObject[];
    (transitions[0].kinase_signatures as JsonObject[]).pop();
    expect(validateFactorGraphResult(malformed).join("\n")).toContain(
      "contains malformed or incomplete child results",
    );
    expect(normalizeFactorGraphKinaseTransitions(kinaseResult)).toHaveLength(2);

    const extra = cloneObject(factorGraphAnalysisResult);
    extra.joint_score = 0.9;
    expect(validateFactorGraphResult(extra).join("\n")).toContain(
      "result contains unsupported fields: joint_score",
    );
  });
});
