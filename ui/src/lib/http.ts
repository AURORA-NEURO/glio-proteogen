import { isJsonObject, type JsonObject } from "./research-state";

const HTTP_DETAIL_MAX_CHARACTERS = 1_000;

export class ResponseLimitError extends Error {
  constructor(maxBytes: number) {
    super(`The service response exceeded the ${formatByteLimit(maxBytes)} limit.`);
    this.name = "ResponseLimitError";
  }
}

function formatByteLimit(value: number): string {
  if (value % (1024 * 1024) === 0) return `${value / (1024 * 1024)} MiB`;
  if (value % 1024 === 0) return `${value / 1024} KiB`;
  return `${value} byte`;
}

function declaredContentLength(response: Response): number | null {
  const raw = response.headers.get("content-length");
  if (raw === null || !/^\d+$/.test(raw)) return null;
  const value = Number(raw);
  return Number.isSafeInteger(value) ? value : null;
}

export async function readBoundedResponseText(response: Response, maxBytes: number): Promise<string> {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1) throw new TypeError("maxBytes must be a positive safe integer");
  const declared = declaredContentLength(response);
  if (declared !== null && declared > maxBytes) {
    await response.body?.cancel();
    throw new ResponseLimitError(maxBytes);
  }
  if (response.body === null) return "";

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let received = 0;
  let text = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.byteLength;
      if (received > maxBytes) {
        await reader.cancel();
        throw new ResponseLimitError(maxBytes);
      }
      text += decoder.decode(value, { stream: true });
    }
    text += decoder.decode();
    return text;
  } catch (error) {
    if (!(error instanceof ResponseLimitError)) await reader.cancel().catch(() => undefined);
    throw error;
  } finally {
    reader.releaseLock();
  }
}

function safeDetail(payload: unknown): string | null {
  if (!isJsonObject(payload) || typeof payload.detail !== "string") return null;
  const detail = payload.detail.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, " ").trim();
  return detail.length > 0 && detail.length <= HTTP_DETAIL_MAX_CHARACTERS ? detail : null;
}

export function publicHttpError(response: Response, text: string): Error {
  let payload: unknown;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }
  return new Error(safeDetail(payload) ?? `The service rejected the request (HTTP ${response.status}).`);
}

export async function readBoundedJsonObject(response: Response, maxBytes: number): Promise<JsonObject> {
  const text = await readBoundedResponseText(response, maxBytes);
  if (!response.ok) throw publicHttpError(response, text);
  let payload: unknown;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    throw new Error("The service returned invalid JSON.");
  }
  if (!isJsonObject(payload)) throw new Error("The service returned an unexpected JSON shape.");
  return payload;
}

export function isAbortError(error: unknown): boolean {
  if (error === null || typeof error !== "object" || !("name" in error)) return false;
  return error.name === "AbortError";
}
