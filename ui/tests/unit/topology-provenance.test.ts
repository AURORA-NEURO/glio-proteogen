import { describe, expect, it } from "vitest";

import { validateResearchRequest, type JsonObject } from "../../src/lib/research-state";
import { graphTopologyDigest } from "../../src/lib/topology-provenance";
import { demoRequest } from "../fixtures/proteogenomic-state";

const topologyDigest = "sha256:f15f635772f2fa604904a78a452e9e5f6d8af26e7154adb8f87cc8397b6d9602";
const request: JsonObject = {
  profile_id: "glio-ecgi/1.0.0",
  sample_id: "synthetic-topology",
  nodes: [
    { node_id: "protein.EGFR", kind: "protein" },
    { node_id: "pathway.MAPK", kind: "pathway" },
  ],
  edges: [{
    edge_id: "edge.001",
    source_id: "protein.EGFR",
    target_id: "pathway.MAPK",
    kind: "regulates",
    sign: 1,
    weight: 1,
    essential: false,
  }],
  observations: [],
  topology_provenance: {
    topology_digest: topologyDigest,
    derivation: "caller_curated",
    curation_note: "Public pathway context; edge interpretation remains caller-curated.",
    sources: [{
      source_id: "reactome.R-HSA-123.release97",
      resource_name: "Reactome",
      resource_release: "97",
      record_id: "R-HSA-123",
      record_title: "MAPK signaling",
      source_uri: "https://reactome.org/example.sbml",
      source_format: "SBML Level 3 Version 1",
      source_digest: `sha256:${"a".repeat(64)}`,
      source_size_bytes: 1024,
      license_id: "CC0-1.0",
      license_uri: "https://creativecommons.org/publicdomain/zero/1.0/",
      retrieved_on: "2026-08-27",
      scope_node_ids: ["pathway.MAPK"],
      role: "biological_context",
    }],
  },
};

describe("topology provenance validation", () => {
  it("matches the backend canonical graph digest and accepts a closed public source declaration", () => {
    expect(graphTopologyDigest(request)).toBe(topologyDigest);
    expect(graphTopologyDigest(demoRequest as JsonObject)).toBe(
      "sha256:7ccc01a460714c7f4920002cf4570bb49a43c91191ee9de85f9177f1d52341a5",
    );
    expect(validateResearchRequest(request)).toEqual([]);
    const reversed: JsonObject = {
      ...request,
      nodes: [...(request.nodes as JsonObject[])].reverse(),
      edges: [...(request.edges as JsonObject[])].reverse(),
    };
    expect(graphTopologyDigest(reversed)).toBe(topologyDigest);
  });

  it("rejects forged digests, duplicate sources and scopes, unresolved scope, and non-public locations", () => {
    const source = ((request.topology_provenance as JsonObject).sources as JsonObject[])[0];
    const malformed: JsonObject = {
      ...request,
      topology_provenance: {
        ...(request.topology_provenance as JsonObject),
        topology_digest: `sha256:${"0".repeat(64)}`,
        sources: [
          {
            ...source,
            source_uri: "http://example.org/private-copy.sbml",
            scope_node_ids: ["pathway.MAPK", "pathway.MAPK", "protein.absent"],
          },
          source,
        ],
      },
    };

    expect(validateResearchRequest(malformed)).toEqual(expect.arrayContaining([
      "topology_provenance.sources[0].source_uri must be an HTTPS URL of at most 512 characters.",
      "topology_provenance.sources[0].scope_node_ids[2] references an unresolved node.",
      "topology_provenance.sources[0].scope_node_ids contains duplicate node identifiers: pathway.MAPK.",
      "Duplicate topology source identifiers: reactome.R-HSA-123.release97.",
      "topology_provenance.topology_digest does not match the canonical nodes and edges.",
    ]));
  });

  it("rejects malformed source metadata and padded or blank curation notes", () => {
    const topology = request.topology_provenance as JsonObject;
    const source = (topology.sources as JsonObject[])[0];
    const malformed: JsonObject = {
      ...request,
      topology_provenance: {
        ...topology,
        curation_note: " ",
        sources: [{
          ...source,
          source_size_bytes: 1.5,
          source_digest: `sha256:${"A".repeat(64)}`,
          license_uri: "ftp://example.org/license",
          retrieved_on: "2026-13-40",
          role: "inference_input",
          unexpected: true,
        }],
      },
    };

    const errors = validateResearchRequest(malformed);
    expect(errors).toEqual(expect.arrayContaining([
      "topology_provenance.curation_note must contain 1–512 non-blank, unpadded characters.",
      "topology_provenance.sources[0] contains unsupported fields: unexpected.",
      "topology_provenance.sources[0].source_digest must be a lowercase sha256 digest.",
      "topology_provenance.sources[0].source_size_bytes must be an integer.",
      "topology_provenance.sources[0].license_uri must be an HTTPS URL of at most 512 characters.",
      "topology_provenance.sources[0].retrieved_on must use YYYY-MM-DD format.",
      "topology_provenance.sources[0].role must be one of: biological_context.",
    ]));
  });

  it("abstains from digesting structurally incomplete topology fragments", () => {
    const invalid: JsonObject[] = [
      {},
      { nodes: [], edges: {} },
      { nodes: [null], edges: [] },
      { nodes: [{ node_id: 7, kind: "protein" }], edges: [] },
      { nodes: [{ node_id: "protein.A", kind: 7 }], edges: [] },
      { nodes: [{ node_id: "protein.A", kind: "protein", display_name: 7 }], edges: [] },
      { nodes: request.nodes, edges: [null] },
      { nodes: request.nodes, edges: [{ edge_id: 7, source_id: "protein.EGFR", target_id: "pathway.MAPK", kind: "regulates", sign: 1, weight: 1 }] },
      { nodes: request.nodes, edges: [{ edge_id: "edge.X", source_id: 7, target_id: "pathway.MAPK", kind: "regulates", sign: 1, weight: 1 }] },
      { nodes: request.nodes, edges: [{ edge_id: "edge.X", source_id: "protein.EGFR", target_id: 7, kind: "regulates", sign: 1, weight: 1 }] },
      { nodes: request.nodes, edges: [{ edge_id: "edge.X", source_id: "protein.EGFR", target_id: "pathway.MAPK", kind: 7, sign: 1, weight: 1 }] },
      { nodes: request.nodes, edges: [{ edge_id: "edge.X", source_id: "protein.EGFR", target_id: "pathway.MAPK", kind: "regulates", sign: "1", weight: 1 }] },
      { nodes: request.nodes, edges: [{ edge_id: "edge.X", source_id: "protein.EGFR", target_id: "pathway.MAPK", kind: "regulates", sign: 1, weight: "1" }] },
      { nodes: request.nodes, edges: [{ edge_id: "edge.X", source_id: "protein.EGFR", target_id: "pathway.MAPK", kind: "regulates", sign: 1, weight: 1, essential: "yes" }] },
    ];
    for (const fragment of invalid) expect(graphTopologyDigest(fragment)).toBeNull();
  });

  it("canonicalizes optional edges, display names, booleans, and decimal weights", () => {
    expect(graphTopologyDigest({ nodes: [{ node_id: "protein.A", kind: "protein" }] })).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(graphTopologyDigest({
      nodes: [
        { node_id: "protein.A", kind: "protein", display_name: "A" },
        { node_id: "protein.B", kind: "protein", display_name: null },
      ],
      edges: [{
        edge_id: "edge.AB",
        source_id: "protein.A",
        target_id: "protein.B",
        kind: "regulates",
        sign: -1,
        weight: 0.75,
        essential: true,
      }],
    })).toMatch(/^sha256:[0-9a-f]{64}$/);
  });
});
