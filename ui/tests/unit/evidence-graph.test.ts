import { describe, expect, it } from "vitest";

import {
  buildEvidenceGraph,
  describeGraphEdge,
  GRAPH_NODE_WIDTH,
} from "../../src/lib/evidence-graph";
import type { JsonObject } from "../../src/lib/research-state";

const executedRequest: JsonObject = {
  sample_id: "synthetic-network",
  nodes: [
    { node_id: "pathway.MAPK", kind: "pathway", display_name: "MAPK" },
    { node_id: "phosphosite.EGFR.Y1068", kind: "phosphosite", display_name: "EGFR Y1068" },
    { node_id: "protein.EGFR", kind: "protein", display_name: "EGFR" },
    { node_id: "kinase.EGFR", kind: "kinase", display_name: "EGFR kinase" },
  ],
  edges: [
    {
      edge_id: "edge.negative",
      source_id: "pathway.MAPK",
      target_id: "protein.EGFR",
      kind: "regulates",
      sign: -1,
      weight: 0.6,
      essential: false,
    },
    {
      edge_id: "edge.substrate",
      source_id: "kinase.EGFR",
      target_id: "phosphosite.EGFR.Y1068",
      kind: "kinase_substrate",
      sign: 1,
      weight: 0.9,
      essential: false,
    },
  ],
  observations: [],
};

describe("executed evidence graph layout", () => {
  it("retains exact relation identity, direction, sign, weight, and node type", () => {
    const graph = buildEvidenceGraph(executedRequest, []);

    expect(graph.columns.map((column) => column.kind)).toEqual([
      "protein",
      "phosphosite",
      "pathway",
      "kinase",
    ]);
    expect(graph.nodes.find((node) => node.id === "kinase.EGFR")).toMatchObject({
      kind: "kinase",
      label: "EGFR kinase",
      column: 3,
    });
    expect(graph.edges.map((edge) => edge.id)).toEqual(["edge.negative", "edge.substrate"]);
    expect(graph.edges[0]).toMatchObject({
      sourceId: "pathway.MAPK",
      targetId: "protein.EGFR",
      kind: "regulates",
      sign: -1,
      weight: 0.6,
    });
    expect(graph.edges[1]).toMatchObject({
      sourceId: "kinase.EGFR",
      targetId: "phosphosite.EGFR.Y1068",
      kind: "kinase_substrate",
      sign: 1,
      weight: 0.9,
    });

    const source = graph.nodes.find((node) => node.id === "kinase.EGFR");
    const target = graph.nodes.find((node) => node.id === "phosphosite.EGFR.Y1068");
    expect(graph.edges[1].path).toMatch(new RegExp(`^M ${source?.x} `));
    expect(graph.edges[1].path).toContain(`${(target?.x ?? 0) + GRAPH_NODE_WIDTH}`);
    expect(describeGraphEdge(graph.edges[1])).toBe(
      "edge.substrate: kinase.EGFR to phosphosite.EGFR.Y1068; kinase_substrate; positive sign; weight 0.9",
    );
  });

  it("is invariant to node and edge input order", () => {
    const reversed: JsonObject = {
      ...executedRequest,
      nodes: [...(executedRequest.nodes as JsonObject[])].reverse(),
      edges: [...(executedRequest.edges as JsonObject[])].reverse(),
    };

    expect(buildEvidenceGraph(reversed, [])).toEqual(buildEvidenceGraph(executedRequest, []));
  });

  it("lays out same-column and forward edges while discarding malformed graph fragments", () => {
    const request: JsonObject = {
      nodes: [
        null,
        { kind: "protein" },
        { node_id: "protein.B", kind: "protein" },
        { node_id: "protein.A", kind: "protein", display_name: 7 },
        { node_id: "mystery.X", kind: "unrecognized" },
        { node_id: "pathway.P", kind: "pathway" },
      ],
      edges: [
        null,
        { edge_id: "edge.missing", source_id: "protein.A", target_id: "missing", sign: 1, weight: 1 },
        { edge_id: "edge.sign", source_id: "protein.A", target_id: "protein.B", sign: 0, weight: 1 },
        { edge_id: "edge.weight", source_id: "protein.A", target_id: "protein.B", sign: 1 },
        { edge_id: "edge.same", source_id: "protein.A", target_id: "protein.B", sign: -1, weight: 1, essential: true },
        { edge_id: "edge.forward", source_id: "protein.A", target_id: "pathway.P", kind: "regulates", sign: 1, weight: 0.5 },
      ],
    };
    const state = {
      id: "protein.A",
      label: "A state",
      kind: "protein" as const,
      estimate: 1,
      lower: 0.5,
      upper: 1.5,
      classification: "activated",
      evidenceCount: 1,
      stability: 1,
      discordance: 0,
      qValue: null,
      support: "supported",
      abstentionReason: "",
      drivers: [],
      raw: {},
    };

    const graph = buildEvidenceGraph(request, [state]);
    expect(graph.nodes.find((node) => node.id === "protein.A")).toMatchObject({ label: "7", state });
    expect(graph.nodes.find((node) => node.id === "mystery.X")?.kind).toBe("other");
    expect(graph.edges.map((edge) => edge.id)).toEqual(["edge.forward", "edge.same"]);
    expect(graph.edges.find((edge) => edge.id === "edge.same")?.path).toContain(" C ");
    expect(graph.edges.find((edge) => edge.id === "edge.same")?.essential).toBe(true);
    expect(graph.edges.find((edge) => edge.id === "edge.forward")?.kind).toBe("regulates");
    expect(graph.width).toBeGreaterThanOrEqual(360);
    expect(describeGraphEdge(graph.edges.find((edge) => edge.id === "edge.same")!)).toContain("negative sign; weight 1, essential");
  });

  it("returns bounded empty-canvas dimensions", () => {
    expect(buildEvidenceGraph({}, [])).toMatchObject({
      columns: [],
      edges: [],
      height: 160,
      nodes: [],
      width: 360,
    });
  });
});
