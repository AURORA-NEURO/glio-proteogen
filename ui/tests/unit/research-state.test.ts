import { describe, expect, it } from "vitest";

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
} from "../../src/lib/research-state";

const request: JsonObject = {
  profile_id: "glio-ecgi/1.0.0",
  sample_id: "synthetic-001",
  nodes: [
    { node_id: "protein.EGFR", kind: "protein" },
    { node_id: "pathway.MAPK", kind: "pathway" },
  ],
  edges: [{ edge_id: "edge.001", source_id: "protein.EGFR", target_id: "pathway.MAPK", kind: "regulates", sign: 1, weight: 1, essential: false }],
  observations: [{
    observation_id: "obs.001",
    node_id: "protein.EGFR",
    modality: "proteomics",
    state: "observed",
    standardized_effect: 0.8,
    standard_error: 0.1,
    quality_weight: 0.95,
    provenance_digest: `sha256:${"a".repeat(64)}`,
  }],
};

describe("research request helpers", () => {
  it("parses and validates a bounded graph request", () => {
    expect(parseJsonObject(JSON.stringify(request))).toEqual(request);
    expect(validateResearchRequest(request)).toEqual([]);
    expect(requestStats(request)).toEqual({ nodes: 2, edges: 1, observations: 1 });
  });

  it("rejects non-object JSON and reports duplicates", () => {
    expect(() => parseJsonObject("[]")).toThrow("JSON object");
    expect(() => parseJsonObject('{"sample_id":"first","sample_id":"second"}'))
      .toThrow("Duplicate JSON key request.sample_id.");
    expect(() => parseJsonObject('{"nested":{"node_id":"first","node\\u005fid":"second"}}'))
      .toThrow("Duplicate JSON key request.nested.node_id.");
    expect(validateResearchRequest({ ...request, nodes: [{ node_id: "protein.EGFR" }, { node_id: "protein.EGFR" }] })).toContain("Duplicate node identifiers: protein.EGFR.");
  });

  it("enforces exact required fields, types, enums, identifiers, and numeric bounds", () => {
    const malformed: JsonObject = {
      ...request,
      sample_id: 42,
      profile_id: "glio-ecgi/latest",
      bootstrap_replicates: 7,
      permutation_replicates: 32.5,
      unknown_field: true,
      nodes: [{ node_id: "1-not-an-identifier", kind: "gene", display_name: "" }],
      edges: [{ edge_id: "edge.001", source_id: "protein.EGFR", target_id: "pathway.MAPK", kind: "regulates", sign: 0, weight: 0 }],
    };

    const errors = validateResearchRequest(malformed);
    expect(errors).toEqual(expect.arrayContaining([
      "request contains unsupported fields: unknown_field.",
      "sample_id must be a string.",
      "profile_id must equal glio-ecgi/1.0.0.",
      "bootstrap_replicates must be an integer from 8 through 256.",
      "permutation_replicates must be an integer from 32 through 2048.",
      "nodes[0].node_id must be a valid identifier (1–128 characters, beginning with a letter).",
      "nodes[0].kind must be one of: protein, proteoform, phosphosite, complex, pathway, kinase.",
      "nodes[0].display_name must contain 1–160 characters.",
      "edges[0].sign must be exactly -1 or 1.",
      "edges[0].weight must be within [0.01, 10].",
    ]));
  });

  it("requires unique closed graph references and compatible signed endpoint kinds", () => {
    const malformed: JsonObject = {
      ...request,
      edges: [
        { edge_id: "edge.duplicate", source_id: "protein.EGFR", target_id: "pathway.MAPK", kind: "member_of", sign: -1, weight: 1, essential: true },
        { edge_id: "edge.duplicate", source_id: "protein.missing", target_id: "pathway.MAPK", kind: "regulates", sign: 1, weight: 1, essential: true },
      ],
      observations: [
        { ...request.observations[0] as JsonObject, observation_id: "obs.duplicate" },
        { ...request.observations[0] as JsonObject, observation_id: "obs.duplicate", node_id: "protein.missing" },
      ],
    };

    const errors = validateResearchRequest(malformed);
    expect(errors).toEqual(expect.arrayContaining([
      "Duplicate edge identifiers: edge.duplicate.",
      "Duplicate observation identifiers: obs.duplicate.",
      "edges[0].member_of edges must have positive sign.",
      "edges[0].member_of requires a protein/proteoform source and complex target.",
      "edges[1].source_id references an unresolved node.",
      "edges[1].essential is only valid for member_of edges.",
      "observations[1].node_id references an unresolved node.",
    ]));
  });

  it("matches the backend rejection of parallel semantic relations", () => {
    const errors = validateResearchRequest({
      ...request,
      edges: [
        request.edges[0] as JsonObject,
        { ...(request.edges[0] as JsonObject), edge_id: "edge.parallel", sign: -1 },
      ],
    });
    expect(errors).toContain("Parallel semantic relations are not supported.");
  });

  it("keeps active evidence numeric and missing evidence non-numeric", () => {
    const malformed: JsonObject = {
      ...request,
      observations: [
        {
          observation_id: "obs.active",
          node_id: "protein.EGFR",
          modality: "not-a-modality",
          state: "observed",
          standardized_effect: null,
          standard_error: null,
          quality_weight: 0,
          provenance_digest: "sha256:NOT-A-DIGEST",
        },
        {
          observation_id: "obs.missing",
          node_id: "protein.EGFR",
          modality: "proteomics",
          state: "missing",
          standardized_effect: -2,
          standard_error: 0.2,
          quality_weight: 1,
          provenance_digest: `sha256:${"f".repeat(64)}`,
        },
      ],
    };

    const errors = validateResearchRequest(malformed);
    expect(errors).toEqual(expect.arrayContaining([
      "observations[0].modality must be one of: proteomics, phosphoproteomics, transcriptomics, copy_number, external.",
      "observations[0] active evidence requires an effect and standard error.",
      "observations[0] active evidence requires a positive quality weight.",
      "observations[0].provenance_digest must be a lowercase sha256 digest.",
      "observations[1] missing/unsupported evidence cannot carry numeric effects.",
    ]));
  });

  it("validates KINOPHOS intervals, uniqueness, and exact kinase-node identity", () => {
    const kinaseNodes: JsonObject[] = [
      ...(request.nodes as JsonObject[]),
      { node_id: "kinase.AKT1", kind: "kinase" },
    ];
    const malformed: JsonObject = {
      ...request,
      nodes: kinaseNodes,
      external_kinase_profile: {
        profile_id: "kinophos.v1",
        source_digest: `sha256:${"e".repeat(64)}`,
        estimates: [
          { kinase_id: "protein.EGFR", activity: 0.4, lower_bound: 0.5, upper_bound: 0.7 },
          { kinase_id: "protein.EGFR", activity: 0.4, lower_bound: 0.2, upper_bound: 0.7 },
        ],
      },
    };

    const errors = validateResearchRequest(malformed);
    expect(errors).toEqual(expect.arrayContaining([
      "external_kinase_profile.estimates[0].kinase_id must exactly match a kinase node ID.",
      "external_kinase_profile.estimates[0] interval must contain its activity.",
      "external_kinase_profile.estimates[1].kinase_id must exactly match a kinase node ID.",
      "Duplicate external kinase identifiers: protein.EGFR.",
    ]));
  });

  it("enforces the independent 128-kinase limit", () => {
    const kinaseNodes: JsonObject[] = Array.from({ length: 129 }, (_, index) => ({
      node_id: `kinase.K${index}`,
      kind: "kinase",
    }));
    expect(validateResearchRequest({ ...request, nodes: [...request.nodes, ...kinaseNodes] }))
      .toContain("The graph exceeds the 128-kinase limit.");
  });

  it("rejects missing collections, wrong collection types, and all request size limits", () => {
    expect(validateResearchRequest({})).toEqual(expect.arrayContaining([
      "sample_id must be a string.",
      "nodes is required.",
      "At least one graph node is required.",
    ]));
    expect(validateResearchRequest({ sample_id: "sample", nodes: {}, edges: false, observations: "none" })).toEqual(expect.arrayContaining([
      "nodes must be an array.",
      "edges must be an array.",
      "observations must be an array.",
    ]));

    const oversizedNodes = Array.from({ length: 257 }, (_, index) => ({
      node_id: `protein.N${index}`,
      kind: "protein",
    }));
    expect(validateResearchRequest({ ...request, nodes: oversizedNodes })).toContain("The graph exceeds the 256-node limit.");
    expect(validateResearchRequest({ ...request, edges: Array.from({ length: 2049 }, () => null) }))
      .toContain("The graph exceeds the 2,048-edge limit.");
    expect(validateResearchRequest({ ...request, observations: Array.from({ length: 4097 }, () => null) }))
      .toContain("The request exceeds the 4,096-observation limit.");
  });

  it("rejects malformed node, relation, and evidence objects across every bounded field family", () => {
    const nodes: JsonObject[] = [
      { node_id: "protein.P", kind: "protein" },
      { node_id: "proteoform.P.1", kind: "proteoform" },
      { node_id: "phosphosite.P.S1", kind: "phosphosite" },
      { node_id: "complex.C", kind: "complex" },
      { node_id: "pathway.W", kind: "pathway" },
      { node_id: "kinase.K", kind: "kinase" },
      { node_id: "protein.BadName", kind: "protein", display_name: 7, unexpected: true },
      null as unknown as JsonObject,
    ];
    const edges: JsonObject[] = [
      null as unknown as JsonObject,
      { unexpected: true },
      { edge_id: "edge.self", source_id: "protein.P", target_id: "protein.P", kind: "regulates", sign: 1, weight: 1, essential: "yes" },
      { edge_id: "edge.target", source_id: "protein.P", target_id: "protein.Missing", kind: "regulates", sign: 2, weight: 11 },
      { edge_id: "edge.kinase", source_id: "protein.P", target_id: "phosphosite.P.S1", kind: "kinase_substrate", sign: 1, weight: 1 },
      { edge_id: "edge.kinaseTarget", source_id: "kinase.K", target_id: "protein.P", kind: "kinase_substrate", sign: 1, weight: 1 },
      { edge_id: "edge.proteoform", source_id: "protein.P", target_id: "protein.P", kind: "proteoform_of", sign: -1, weight: 1 },
      { edge_id: "edge.proteoformTarget", source_id: "proteoform.P.1", target_id: "complex.C", kind: "proteoform_of", sign: 1, weight: 1 },
      { edge_id: "edge.site", source_id: "protein.P", target_id: "protein.P", kind: "site_of", sign: -1, weight: 1 },
      { edge_id: "edge.siteTarget", source_id: "phosphosite.P.S1", target_id: "pathway.W", kind: "site_of", sign: 1, weight: 1 },
      { edge_id: "edge.memberValid", source_id: "protein.P", target_id: "complex.C", kind: "member_of", sign: 1, weight: 1, essential: true },
      { edge_id: "edge.participatesValid", source_id: "protein.P", target_id: "pathway.W", kind: "participates_in", sign: 1, weight: 1 },
    ];
    const observations: JsonObject[] = [
      null as unknown as JsonObject,
      { unexpected: true },
      {
        observation_id: "obs.nonfinite",
        node_id: "protein.P",
        modality: "proteomics",
        state: "left_censored",
        standardized_effect: Number.POSITIVE_INFINITY,
        standard_error: 0,
        quality_weight: 2,
        provenance_digest: `sha256:${"a".repeat(64)}`,
      },
      {
        observation_id: "obs.defaultQuality",
        node_id: "protein.P",
        modality: "proteomics",
        state: "unsupported",
        standardized_effect: null,
        standard_error: null,
        provenance_digest: `sha256:${"b".repeat(64)}`,
      },
    ];

    const errors = validateResearchRequest({ ...request, nodes, edges, observations });
    expect(errors).toEqual(expect.arrayContaining([
      "nodes[6] contains unsupported fields: unexpected.",
      "nodes[6].display_name must be a string.",
      "nodes[7] must be an object.",
      "edges[0] must be an object.",
      "edges[1] contains unsupported fields: unexpected.",
      "edges[2].essential must be a boolean.",
      "edges[2] cannot be a self edge.",
      "edges[3].target_id references an unresolved node.",
      "edges[3].sign must be within [-1, 1].",
      "edges[3].weight must be within [0.01, 10].",
      "edges[4].kinase_substrate requires a kinase source and phosphosite target.",
      "edges[5].kinase_substrate requires a kinase source and phosphosite target.",
      "edges[6].proteoform_of edges must have positive sign.",
      "edges[7].proteoform_of requires a proteoform source and protein target.",
      "edges[8].site_of edges must have positive sign.",
      "edges[9].site_of requires a phosphosite source and proteoform/protein target.",
      "observations[0] must be an object.",
      "observations[1] contains unsupported fields: unexpected.",
      "observations[2].standardized_effect must be a finite number or null.",
      "observations[2].standard_error must be within (0, 20].",
      "observations[2].quality_weight must be within [0, 1].",
    ]));
  });

  it("rejects malformed optional external profiles without merging identifiers", () => {
    expect(validateResearchRequest({ ...request, external_kinase_profile: [] })).toContain(
      "external_kinase_profile must be an object.",
    );
    const errors = validateResearchRequest({
      ...request,
      nodes: [...request.nodes, { node_id: "kinase.K", kind: "kinase" }],
      external_kinase_profile: {
        unexpected: true,
        profile_id: "bad id",
        source_digest: "invalid",
        estimates: [null, {
          unexpected: true,
          kinase_id: "kinase.K",
          activity: -21,
          lower_bound: -21,
          upper_bound: 21,
        }],
      },
    });
    expect(errors).toEqual(expect.arrayContaining([
      "external_kinase_profile contains unsupported fields: unexpected.",
      "external_kinase_profile.profile_id must be a valid identifier (1–128 characters, beginning with a letter).",
      "external_kinase_profile.source_digest must be a lowercase sha256 digest.",
      "external_kinase_profile.estimates[0] must be an object.",
      "external_kinase_profile.estimates[1] contains unsupported fields: unexpected.",
      "external_kinase_profile.estimates[1].activity must be within [-20, 20].",
      "external_kinase_profile.estimates[1].lower_bound must be within [-20, 20].",
      "external_kinase_profile.estimates[1].upper_bound must be within [-20, 20].",
    ]));
    expect(validateResearchRequest({
      ...request,
      external_kinase_profile: { profile_id: "kinophos", source_digest: `sha256:${"a".repeat(64)}` },
    })).toEqual(expect.arrayContaining([
      "external_kinase_profile.estimates is required.",
      "external_kinase_profile.estimates must contain 1–128 entries.",
    ]));
  });

  it("rejects malformed topology envelopes, collections, and source bounds", () => {
    expect(validateResearchRequest({ ...request, topology_provenance: [] })).toContain(
      "topology_provenance must be an object.",
    );
    const errors = validateResearchRequest({
      ...request,
      topology_provenance: {
        unexpected: true,
        topology_digest: "invalid",
        derivation: "unknown",
        curation_note: 7,
        sources: [null, {
          source_id: "source.A",
          resource_name: "",
          resource_release: "x".repeat(161),
          record_id: "bad id",
          record_title: "Title",
          source_uri: "https://example.test/source",
          source_format: "JSON",
          source_digest: `sha256:${"a".repeat(64)}`,
          source_size_bytes: 0,
          license_id: "CC0-1.0",
          license_uri: "https://example.test/license",
          retrieved_on: "2026-08-29",
          scope_node_ids: [7, "protein.P"],
        }],
      },
    });
    expect(errors).toEqual(expect.arrayContaining([
      "topology_provenance contains unsupported fields: unexpected.",
      "topology_provenance.topology_digest must be a lowercase sha256 digest.",
      "topology_provenance.derivation must be one of: caller_curated, synthetic_abstraction.",
      "topology_provenance.curation_note must be a string.",
      "topology_provenance.sources[0] must be an object.",
      "topology_provenance.sources[1].resource_name must contain 1–160 characters.",
      "topology_provenance.sources[1].resource_release must contain 1–160 characters.",
      "topology_provenance.sources[1].record_id must be a valid identifier (1–128 characters, beginning with a letter).",
      "topology_provenance.sources[1].source_size_bytes must be within [1, 67108864].",
      "topology_provenance.sources[1].scope_node_ids[0] must be a valid identifier.",
      "topology_provenance.sources[1].scope_node_ids[1] references an unresolved node.",
    ]));
    expect(validateResearchRequest({
      ...request,
      topology_provenance: {
        topology_digest: `sha256:${"a".repeat(64)}`,
        derivation: "caller_curated",
        curation_note: "context",
      },
    })).toEqual(expect.arrayContaining([
      "topology_provenance.sources is required.",
      "topology_provenance.sources must contain 1–32 entries.",
    ]));
  });
});

describe("result normalization", () => {
  it("normalizes canonical node and kinase states without duplicates", () => {
    const result: JsonObject = {
      node_states: [{
        node_id: "EGFR",
        kind: "protein",
        activity: 0.8,
        lower_bound: 0.4,
        upper_bound: 1.1,
        classification: "activated",
        support: "supported",
        evidence_count: 3,
        top_drivers: [{ driver_id: "edge.001", driver_type: "edge", signed_contribution: 0.125, strength: 0.125 }],
        ablation_effects: [{ kind: "modality", omitted: "proteomics", activity_delta: -0.3 }],
      }],
      kinase_states: [{
        node_id: "AKT1",
        kind: "kinase",
        activity: 0.5,
        lower_bound: 0.2,
        upper_bound: 0.9,
        classification: "indeterminate",
        q_value: 0.04,
      }],
    };
    const states = normalizeStates(result);
    expect(states).toHaveLength(2);
    expect(states[0]).toMatchObject({ id: "EGFR", kind: "protein", estimate: 0.8, lower: 0.4, upper: 1.1, drivers: ["edge.001 (+0.125)"] });
    expect(states[1]).toMatchObject({ id: "AKT1", kind: "kinase", qValue: 0.04 });
    expect(normalizeAblations(result, states)).toEqual([{ target: "EGFR", family: "modality · proteomics", delta: -0.3, detail: "" }]);
  });

  it("normalizes aliases, nested intervals, primitive drivers, and fallback state fields", () => {
    const result: JsonObject = {
      states: [
        null,
        { entity_id: "site.A", entity_type: "phospho_site", confidence_interval: { low: -1, high: 1 }, drivers: ["direct", 7, null, { id: "edge.A", weight: -0.5 }, {}] },
        { id: "form.A", type: "proteo-form", uncertainty: { minimum: -2, maximum: 2 } },
        { id: "protein.A", type: "protein" },
        { id: "complex.A", type: "complex" },
        { id: "pathway.A", type: "pathway" },
        { id: "kinase.A", type: "kinase" },
        { type: "gene" },
      ],
      proteins: [{ id: "protein.A", activity: 2 }],
      ablations: [null, { target: "global", family: "topology", delta: 0.25, description: "remove topology" }],
    };
    const states = normalizeStates(result);
    expect(states.map((state) => state.kind)).toEqual([
      "phosphosite", "proteoform", "protein", "complex", "pathway", "kinase", "other",
    ]);
    expect(states.find((state) => state.id === "protein.A")?.estimate).toBe(2);
    expect(states[0]).toMatchObject({
      drivers: ["direct", "7", "edge.A (-0.5)"],
      lower: -1,
      upper: 1,
    });
    expect(states.find((state) => state.kind === "other")).toMatchObject({
      abstentionReason: "",
      classification: "indeterminate",
      id: "unnamed",
      support: "abstained",
    });
    expect(normalizeAblations(result, states)).toContainEqual({
      delta: 0.25,
      detail: "remove topology",
      family: "topology",
      target: "global",
    });
  });

  it("exposes null-safe accessors, formatting, digest labels, and alias statistics", () => {
    const value: JsonObject = { first: null, second: 7, truth: true, infinite: Number.POSITIVE_INFINITY, object: { x: 1 }, array: [1] };
    expect(isJsonObject(value)).toBe(true);
    expect(isJsonObject([])).toBe(false);
    expect(textAt(value, ["first", "second"])).toBe("7");
    expect(textAt(value, ["truth"])).toBe("true");
    expect(textAt(value, ["missing"], "fallback")).toBe("fallback");
    expect(numberAt(value, ["infinite", "second"])).toBe(7);
    expect(numberAt(value, ["missing"])).toBeNull();
    expect(objectAt(value, ["first", "object"])).toEqual({ x: 1 });
    expect(objectAt(value, ["missing"])).toBeNull();
    expect(arrayAt(value, ["first", "array"])).toEqual([1]);
    expect(arrayAt(value, ["missing"])).toEqual([]);
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(1.2)).toBe("1.2");
    expect(formatSigned(null)).toBe("—");
    expect(formatSigned(1.25)).toBe("+1.25");
    expect(formatSigned(-1)).toBe("-1");
    expect(shortDigest(`sha256:${"a".repeat(64)}`)).toBe("aaaaaaaaaaaa");
    expect(shortDigest("")).toBe("—");
    expect(requestStats({ entities: [1], relations: [1, 2], evidence: [1, 2, 3] })).toEqual({
      edges: 2,
      nodes: 1,
      observations: 3,
    });
  });
});
