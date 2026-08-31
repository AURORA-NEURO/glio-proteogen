import type { JsonObject, JsonValue } from "./research-state";

const SHA256_CONSTANTS = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

const SHA256_INITIAL = new Uint32Array([
  0x6a09e667,
  0xbb67ae85,
  0x3c6ef372,
  0xa54ff53a,
  0x510e527f,
  0x9b05688c,
  0x1f83d9ab,
  0x5be0cd19,
]);

function rotateRight(value: number, places: number): number {
  return (value >>> places) | (value << (32 - places));
}

export function sha256Hex(source: string): string {
  const input = new TextEncoder().encode(source);
  const paddedLength = Math.ceil((input.length + 9) / 64) * 64;
  const bytes = new Uint8Array(paddedLength);
  bytes.set(input);
  bytes[input.length] = 0x80;
  const bitLength = input.length * 8;
  const view = new DataView(bytes.buffer);
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x1_0000_0000), false);
  view.setUint32(paddedLength - 4, bitLength >>> 0, false);

  const hash = new Uint32Array(SHA256_INITIAL);
  const words = new Uint32Array(64);
  for (let offset = 0; offset < bytes.length; offset += 64) {
    for (let index = 0; index < 16; index += 1) words[index] = view.getUint32(offset + index * 4, false);
    for (let index = 16; index < 64; index += 1) {
      const before15 = words[index - 15];
      const before2 = words[index - 2];
      const sigma0 = rotateRight(before15, 7) ^ rotateRight(before15, 18) ^ (before15 >>> 3);
      const sigma1 = rotateRight(before2, 17) ^ rotateRight(before2, 19) ^ (before2 >>> 10);
      words[index] = (words[index - 16] + sigma0 + words[index - 7] + sigma1) >>> 0;
    }

    let [a, b, c, d, e, f, g, h] = hash;
    for (let index = 0; index < 64; index += 1) {
      const sum1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const choice = (e & f) ^ (~e & g);
      const temporary1 = (h + sum1 + choice + SHA256_CONSTANTS[index] + words[index]) >>> 0;
      const sum0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temporary2 = (sum0 + majority) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temporary1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temporary1 + temporary2) >>> 0;
    }
    hash[0] = (hash[0] + a) >>> 0;
    hash[1] = (hash[1] + b) >>> 0;
    hash[2] = (hash[2] + c) >>> 0;
    hash[3] = (hash[3] + d) >>> 0;
    hash[4] = (hash[4] + e) >>> 0;
    hash[5] = (hash[5] + f) >>> 0;
    hash[6] = (hash[6] + g) >>> 0;
    hash[7] = (hash[7] + h) >>> 0;
  }
  return [...hash].map((value) => value.toString(16).padStart(8, "0")).join("");
}

function isObject(value: JsonValue | undefined): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function canonicalJson(value: JsonValue, parentKey = ""): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") {
    if (parentKey === "weight" && Number.isInteger(value)) return `${value}.0`;
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key], key)}`).join(",")}}`;
}

function canonicalTopology(request: JsonObject): JsonObject | null {
  if (!Array.isArray(request.nodes)) return null;
  const requestEdges = request.edges === undefined ? [] : request.edges;
  if (!Array.isArray(requestEdges)) return null;
  const nodes = request.nodes.flatMap((value) => {
    if (!isObject(value) || typeof value.node_id !== "string" || typeof value.kind !== "string") return [];
    if (value.display_name !== undefined && value.display_name !== null && typeof value.display_name !== "string") return [];
    return [{
      display_name: value.display_name ?? null,
      kind: value.kind,
      node_id: value.node_id,
    } satisfies JsonObject];
  });
  const edges = requestEdges.flatMap((value) => {
    if (
      !isObject(value) ||
      typeof value.edge_id !== "string" ||
      typeof value.source_id !== "string" ||
      typeof value.target_id !== "string" ||
      typeof value.kind !== "string" ||
      typeof value.sign !== "number" ||
      typeof value.weight !== "number"
    ) return [];
    if (value.essential !== undefined && typeof value.essential !== "boolean") return [];
    return [{
      edge_id: value.edge_id,
      essential: value.essential ?? false,
      kind: value.kind,
      sign: value.sign,
      source_id: value.source_id,
      target_id: value.target_id,
      weight: value.weight,
    } satisfies JsonObject];
  });
  if (nodes.length !== request.nodes.length || edges.length !== requestEdges.length) return null;
  const compare = (left: JsonObject, right: JsonObject, key: string) => {
    const leftValue = String(left[key]);
    const rightValue = String(right[key]);
    return leftValue < rightValue ? -1 : leftValue > rightValue ? 1 : 0;
  };
  nodes.sort((left, right) => compare(left, right, "node_id"));
  edges.sort((left, right) => compare(left, right, "edge_id"));
  return { edges, nodes };
}

export function graphTopologyDigest(request: JsonObject): string | null {
  const topology = canonicalTopology(request);
  return topology ? `sha256:${sha256Hex(canonicalJson(topology))}` : null;
}
