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
