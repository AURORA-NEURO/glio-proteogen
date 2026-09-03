import { describe, expect, it } from "vitest";

import {
  catalogOperationKey,
  filterCatalogOperations,
  preferredRequestMediaType,
  resolveCatalogOperation,
  type CatalogOperation,
  type OperationOpenApiDocument,
} from "../../src/lib/operation-catalog";

const analyze: CatalogOperation = {
  operation_id: "research_state_analyze",
  method: "POST",
  path: "/v1/research/proteogenomic-state/analyze",
  summary: "Analyze a bounded evidence graph",
  tags: ["research-ecgi"],
  request_media_types: ["application/json"],
  response_media_types: ["application/json"],
  parameter_locations: ["query"],
  request_max_bytes: 2 * 1024 * 1024,
  result_max_bytes: 4 * 1024 * 1024,
  safety_class: "research-use-only",
  mutability_class: "stateless-compute",
  validated_example_status: "validated",
  validated_example_id: "synthetic-glioma-demo-v1",
  validated_example_abstention_reason: null,
};

const livez: CatalogOperation = {
  operation_id: "livez",
  method: "GET",
  path: "/livez",
  summary: "Process liveness",
  tags: ["operations"],
  request_media_types: [],
  response_media_types: ["application/json"],
  parameter_locations: [],
  request_max_bytes: null,
  result_max_bytes: null,
  safety_class: "operational",
  mutability_class: "read-only",
  validated_example_status: "abstained",
  validated_example_id: null,
  validated_example_abstention_reason: "operation_has_no_request_body",
};

const openapi: OperationOpenApiDocument = {
  paths: {
    [analyze.path]: {
      parameters: [{ name: "trace", in: "query", schema: { type: "boolean", default: false } }],
      post: {
        operationId: analyze.operation_id,
        summary: analyze.summary ?? undefined,
        parameters: [{ name: "mode", in: "query", schema: { enum: ["strict"] } }],
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: { type: "object", properties: { sample_id: { const: "demo-1" } } },
            },
          },
        },
      },
    },
  },
};

describe("v2 operation catalog integration", () => {
  it("searches operation identity, route, safety, mutability, and validated examples", () => {
    const operations = [livez, analyze];
    expect(filterCatalogOperations(operations, "proteogenomic-state")).toEqual([analyze]);
    expect(filterCatalogOperations(operations, "research-use-only")).toEqual([analyze]);
    expect(filterCatalogOperations(operations, "stateless-compute")).toEqual([analyze]);
    expect(filterCatalogOperations(operations, "synthetic-glioma-demo-v1")).toEqual([analyze]);
    expect(filterCatalogOperations(operations, "operation_has_no_request_body")).toEqual([livez]);
    expect(filterCatalogOperations(operations, " OPERATIONS ")).toEqual([livez]);
    expect(filterCatalogOperations(operations, "")).toEqual(operations);
  });

  it("joins a catalog method/path to OpenAPI without losing shared or operation parameters", () => {
    const resolved = resolveCatalogOperation(analyze, openapi);
    expect(catalogOperationKey(analyze)).toBe(`POST ${analyze.path}`);
    expect(resolved?.method).toBe("post");
    expect(resolved?.operation.operationId).toBe(analyze.operation_id);
    expect(resolved?.parameters.map((parameter) => parameter.name)).toEqual(["trace", "mode"]);
    expect(resolved?.operation.requestBody?.required).toBe(true);
    expect(preferredRequestMediaType(resolved?.operation ?? {})).toBe("application/json");
  });

  it("selects the mounted raw-inspection media type without treating it as JSON", () => {
    expect(preferredRequestMediaType({
      requestBody: {
        content: {
          "application/octet-stream": { schema: { type: "string" } },
        },
      },
    })).toBe("application/octet-stream");
    expect(preferredRequestMediaType({})).toBeNull();
  });

  it("rejects catalog entries that cannot be executed from the OpenAPI document", () => {
    expect(resolveCatalogOperation(livez, openapi)).toBeNull();
    expect(resolveCatalogOperation({ ...analyze, method: "OPTIONS" }, openapi)).toBeNull();
    expect(resolveCatalogOperation({ ...analyze, method: "CONNECT" }, openapi)).toBeNull();
    expect(resolveCatalogOperation({ ...analyze, path: "/missing" }, openapi)).toBeNull();
  });

  it("searches nullable metadata and resolves operations with no parameter arrays", () => {
    const minimal = {
      ...livez,
      method: "GET",
      summary: null,
      validated_example_abstention_reason: null,
    };
    expect(filterCatalogOperations([minimal], "absent-value")).toEqual([]);
    expect(resolveCatalogOperation(minimal, {
      paths: { [minimal.path]: { get: { operationId: minimal.operation_id } } },
    })?.parameters).toEqual([]);
  });
});
