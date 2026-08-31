import { describe, expect, it } from "vitest";

import { resolveJsonPointer, sampleFromSchema, schemaProperties, serializeQueryValue } from "../../src/lib/openapi";

const document = {
  components: {
    schemas: {
      Base: {
        type: "object",
        properties: {
          id: { type: "string", const: "sample-1" },
          enabled: { type: "boolean", default: true },
        },
      },
      Request: {
        allOf: [
          { $ref: "#/components/schemas/Base" },
          { type: "object", properties: { mode: { oneOf: [{ const: "robust" }, { const: "fast" }] } } },
        ],
      },
    },
  },
};

describe("OpenAPI schema samples", () => {
  it("resolves pointers and composes allOf with defaults and const values", () => {
    expect(resolveJsonPointer(document, "#/components/schemas/Base")).toEqual(document.components.schemas.Base);
    expect(sampleFromSchema({ $ref: "#/components/schemas/Request" }, document)).toEqual({
      id: "sample-1",
      enabled: true,
      mode: "robust",
    });
  });

  it("supports anyOf, arrays, prefix items, and recursive references", () => {
    expect(sampleFromSchema({ anyOf: [{ type: "integer", default: 7 }, { type: "null" }] }, document)).toBe(7);
    expect(sampleFromSchema({ type: "array", items: { enum: ["observed", "missing"] } }, document)).toEqual(["observed"]);
    expect(sampleFromSchema({ prefixItems: [{ const: "x" }, { type: "number" }] }, document)).toEqual(["x", 0]);
    expect(sampleFromSchema({ $ref: "#/components/schemas/Unknown" }, document)).toEqual({});
  });

  it("collects fields through references and composition", () => {
    expect(Object.keys(schemaProperties({ $ref: "#/components/schemas/Request" }, document))).toEqual(["id", "enabled", "mode"]);
  });

  it("serializes scalar and comma-delimited array query inputs", () => {
    expect(serializeQueryValue(" 0.25 ", { type: "number" })).toEqual(["0.25"]);
    expect(serializeQueryValue("protein, kinase, ,pathway", { type: "array" })).toEqual(["protein", "kinase", "pathway"]);
    expect(serializeQueryValue(" ", { type: "string" })).toEqual([]);
  });

  it("rejects external and malformed pointers and decodes escaped pointer segments", () => {
    const escaped = { "a/b": { "t~n": 7 }, array: [1] };
    expect(resolveJsonPointer(escaped, "https://example.test/schema")).toBeUndefined();
    expect(resolveJsonPointer(escaped, "#/a~1b/t~0n")).toBe(7);
    expect(resolveJsonPointer(escaped, "#/missing/value")).toBeUndefined();
    expect(resolveJsonPointer(escaped, "#/array/0")).toBeUndefined();
  });

  it("samples every JSON Schema primitive, annotation, and composition fallback", () => {
    expect(sampleFromSchema(undefined, document)).toEqual({});
    expect(sampleFromSchema({ examples: ["example"] }, document)).toBe("example");
    expect(sampleFromSchema({ example: false }, document)).toBe(false);
    expect(sampleFromSchema({ enum: [null, "next"] }, document)).toBeNull();
    expect(sampleFromSchema({ type: ["null", "boolean"] }, document)).toBe(false);
    expect(sampleFromSchema({ type: "boolean" }, document)).toBe(false);
    expect(sampleFromSchema({ type: "integer" }, document)).toBe(0);
    expect(sampleFromSchema({ type: "number" }, document)).toBe(0);
    expect(sampleFromSchema({ type: "null" }, document)).toBeNull();
    expect(sampleFromSchema({ type: "string" }, document)).toBe("");
    expect(sampleFromSchema({ type: "object" }, document)).toEqual({});
    expect(sampleFromSchema({ type: "array" }, document)).toEqual([]);
    expect(sampleFromSchema({ allOf: [{ const: "first" }, { type: "string" }] }, document)).toBe("first");
    expect(sampleFromSchema({ allOf: [{ type: "string" }, { type: "number" }] }, document)).toBe("");
    expect(sampleFromSchema({ oneOf: [{ const: "one" }] }, document)).toBe("one");
  });

  it("bounds unresolved and circular references", () => {
    const circular = { components: { schemas: { Self: { $ref: "#/components/schemas/Self" } } } };
    expect(sampleFromSchema({ $ref: "#/components/schemas/Self" }, circular)).toEqual({});
    expect(sampleFromSchema({ $ref: "#/components/schemas/Array" }, {
      components: { schemas: { Array: [] as never } },
    })).toEqual({});
  });

  it("collects properties from variants and returns empty properties for invalid schemas", () => {
    expect(schemaProperties(undefined, document)).toEqual({});
    expect(schemaProperties({ $ref: "#/components/schemas/Unknown" }, document)).toEqual({});
    expect(schemaProperties({ oneOf: [{ properties: { inherited: { type: "string" } } }], properties: { local: { type: "number" } } }, document))
      .toEqual({ inherited: { type: "string" }, local: { type: "number" } });
    expect(schemaProperties({ anyOf: [{ properties: { alternate: { type: "boolean" } } }] }, document))
      .toEqual({ alternate: { type: "boolean" } });
    expect(schemaProperties({ type: "string" }, document)).toEqual({});
    expect(serializeQueryValue("a,b", { type: ["null", "array"] })).toEqual(["a", "b"]);
    expect(serializeQueryValue(" value ")).toEqual(["value"]);
  });
});
