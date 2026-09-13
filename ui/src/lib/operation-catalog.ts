import type { OpenApiDocument, SchemaNode } from "@/lib/openapi";

export const operationMethods = [
  "get",
  "post",
  "put",
  "patch",
  "delete",
  "options",
  "head",
  "trace",
] as const;

export type OperationMethod = (typeof operationMethods)[number];

export type CatalogOperation = {
  operation_id: string;
  method: string;
  path: string;
  summary?: string | null;
  tags: string[];
  request_media_types: string[];
  response_media_types: string[];
  parameter_locations: string[];
  request_max_bytes: number | null;
  result_max_bytes: number | null;
  safety_class: string;
  mutability_class: string;
  validated_example_status: "validated" | "abstained";
  validated_example_id: string | null;
  validated_example_abstention_reason: string | null;
};

export type OperationCatalog = {
  catalog_version: number;
  environment: string;
  version: string;
  operation_count: number;
  operations: CatalogOperation[];
  catalog_digest: string;
};

export type OpenApiParameter = {
  name: string;
  in: string;
  required?: boolean;
  description?: string;
  schema?: SchemaNode;
};

export type OpenApiOperation = {
  summary?: string;
  description?: string;
  operationId?: string;
  parameters?: OpenApiParameter[];
  requestBody?: {
    required?: boolean;
    content?: Record<string, { schema?: SchemaNode }>;
  };
};

export type OpenApiPathItem = {
  parameters?: OpenApiParameter[];
  get?: OpenApiOperation;
  post?: OpenApiOperation;
  put?: OpenApiOperation;
  patch?: OpenApiOperation;
  delete?: OpenApiOperation;
  options?: OpenApiOperation;
  head?: OpenApiOperation;
  trace?: OpenApiOperation;
};

export type OperationOpenApiDocument = OpenApiDocument & {
  paths: Record<string, OpenApiPathItem>;
};

export type ResolvedCatalogOperation = {
  key: string;
  catalog: CatalogOperation;
  path: string;
  method: OperationMethod;
  operation: OpenApiOperation;
  parameters: OpenApiParameter[];
};

export function catalogOperationKey(operation: Pick<CatalogOperation, "method" | "path">): string {
  return `${operation.method.toUpperCase()} ${operation.path}`;
}

export function preferredRequestMediaType(operation: OpenApiOperation): string | null {
  const mediaTypes = Object.keys(operation.requestBody?.content ?? {});
  if (mediaTypes.includes("application/json")) return "application/json";
  if (mediaTypes.includes("application/octet-stream")) return "application/octet-stream";
  return mediaTypes[0] ?? null;
}

export function filterCatalogOperations(
  operations: readonly CatalogOperation[],
  search: string,
): CatalogOperation[] {
  const normalized = search.trim().toLowerCase();
  if (!normalized) return [...operations];
  return operations.filter((operation) => [
    operation.operation_id,
    operation.method,
    operation.path,
    operation.summary ?? "",
    operation.safety_class,
    operation.mutability_class,
    operation.validated_example_status,
    operation.validated_example_id ?? "",
    operation.validated_example_abstention_reason ?? "",
    ...operation.tags,
    ...operation.request_media_types,
    ...operation.response_media_types,
    ...operation.parameter_locations,
  ].some((value) => value.toLowerCase().includes(normalized)));
}

function isOperationMethod(value: string): value is OperationMethod {
  return operationMethods.some((method) => method === value);
}

export function resolveCatalogOperation(
  catalog: CatalogOperation,
  openapi: OperationOpenApiDocument,
): ResolvedCatalogOperation | null {
  const method = catalog.method.toLowerCase();
  if (!isOperationMethod(method)) return null;
  const pathItem = openapi.paths[catalog.path];
  const operation = pathItem?.[method];
  if (!operation) return null;
  return {
    key: catalogOperationKey(catalog),
    catalog,
    path: catalog.path,
    method,
    operation,
    parameters: [...(pathItem.parameters ?? []), ...(operation.parameters ?? [])],
  };
}
