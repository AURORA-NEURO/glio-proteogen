export type SchemaNode = {
  $ref?: string;
  $defs?: Record<string, SchemaNode>;
  definitions?: Record<string, SchemaNode>;
  type?: string | string[];
  title?: string;
  description?: string;
  properties?: Record<string, SchemaNode>;
  additionalProperties?: boolean | SchemaNode;
  items?: SchemaNode;
  prefixItems?: SchemaNode[];
  enum?: unknown[];
  required?: string[];
  default?: unknown;
  const?: unknown;
  example?: unknown;
  examples?: unknown[];
  oneOf?: SchemaNode[];
  anyOf?: SchemaNode[];
  allOf?: SchemaNode[];
  nullable?: boolean;
};

export type OpenApiDocument = {
  components?: { schemas?: Record<string, SchemaNode> };
  $defs?: Record<string, SchemaNode>;
  definitions?: Record<string, SchemaNode>;
};

function hasOwn(object: object, key: PropertyKey): boolean {
  return Object.prototype.hasOwnProperty.call(object, key);
}

function decodePointerSegment(value: string): string {
  return decodeURIComponent(value).replace(/~1/g, "/").replace(/~0/g, "~");
}

export function resolveJsonPointer(root: unknown, reference: string): unknown {
  if (!reference.startsWith("#/")) return undefined;
  return reference
    .slice(2)
    .split("/")
    .map(decodePointerSegment)
    .reduce<unknown>((current, segment) => {
      if (!current || typeof current !== "object" || Array.isArray(current)) return undefined;
      return (current as Record<string, unknown>)[segment];
    }, root);
}

function mergeSamples(values: unknown[]): unknown {
  const objects = values.filter(
    (value): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value),
  );
  if (objects.length === values.length && objects.length > 0) return Object.assign({}, ...objects);
  return values.find((value) => value !== undefined) ?? {};
}

export function sampleFromSchema(
  schema: SchemaNode | undefined,
  root: OpenApiDocument,
  seen: ReadonlySet<string> = new Set(),
): unknown {
  if (!schema) return {};

  if (schema.$ref) {
    if (seen.has(schema.$ref)) return {};
    const resolved = resolveJsonPointer(root, schema.$ref);
    if (!resolved || typeof resolved !== "object" || Array.isArray(resolved)) return {};
    return sampleFromSchema(resolved as SchemaNode, root, new Set([...seen, schema.$ref]));
  }

  if (hasOwn(schema, "default")) return schema.default;
  if (hasOwn(schema, "const")) return schema.const;
  if (schema.examples?.length) return schema.examples[0];
  if (hasOwn(schema, "example")) return schema.example;
  if (schema.enum?.length) return schema.enum[0];

  if (schema.allOf?.length) {
    return mergeSamples(schema.allOf.map((part) => sampleFromSchema(part, root, seen)));
  }

  const variant = schema.oneOf?.[0] ?? schema.anyOf?.[0];
  if (variant) return sampleFromSchema(variant, root, seen);

  const types = Array.isArray(schema.type) ? schema.type : schema.type ? [schema.type] : [];
  const effectiveType = types.find((type) => type !== "null") ?? types[0];
  if (effectiveType === "object" || schema.properties) {
    return Object.fromEntries(
      Object.entries(schema.properties ?? {}).map(([key, value]) => [key, sampleFromSchema(value, root, seen)]),
    );
  }
  if (effectiveType === "array" || schema.items || schema.prefixItems) {
    if (schema.prefixItems?.length) return schema.prefixItems.map((item) => sampleFromSchema(item, root, seen));
    return schema.items ? [sampleFromSchema(schema.items, root, seen)] : [];
  }
  if (effectiveType === "boolean") return false;
  if (effectiveType === "integer" || effectiveType === "number") return 0;
  if (effectiveType === "null") return null;
  return "";
}

export function schemaProperties(
  schema: SchemaNode | undefined,
  root: OpenApiDocument,
): Record<string, SchemaNode> {
  if (!schema) return {};
  if (schema.$ref) {
    const resolved = resolveJsonPointer(root, schema.$ref);
    return resolved && typeof resolved === "object" && !Array.isArray(resolved)
      ? schemaProperties(resolved as SchemaNode, root)
      : {};
  }
  if (schema.allOf?.length) {
    return Object.assign({}, ...schema.allOf.map((part) => schemaProperties(part, root)));
  }
  const variant = schema.oneOf?.[0] ?? schema.anyOf?.[0];
  return variant ? { ...schemaProperties(variant, root), ...(schema.properties ?? {}) } : (schema.properties ?? {});
}

export function serializeQueryValue(value: string, schema?: SchemaNode): string[] {
  if (!value.trim()) return [];
  const effectiveType = Array.isArray(schema?.type) ? schema.type.find((item) => item !== "null") : schema?.type;
  if (effectiveType === "array") return value.split(",").map((item) => item.trim()).filter(Boolean);
  return [value.trim()];
}
