import { describe, expect, it } from "vitest";

import {
  isAbortError,
  publicHttpError,
  readBoundedJsonObject,
  readBoundedResponseText,
  ResponseLimitError,
} from "../../src/lib/http";

describe("bounded browser HTTP responses", () => {
  it("reads a bounded JSON object", async () => {
    const response = new Response(JSON.stringify({ status: "ok" }), {
      headers: { "Content-Type": "application/json" },
    });
    await expect(readBoundedJsonObject(response, 1_024)).resolves.toEqual({ status: "ok" });
  });

  it("rejects declared and streamed bodies beyond the limit", async () => {
    const declared = new Response("ignored", { headers: { "Content-Length": "2048" } });
    await expect(readBoundedResponseText(declared, 1_024)).rejects.toBeInstanceOf(ResponseLimitError);

    const streamed = new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new Uint8Array(700));
        controller.enqueue(new Uint8Array(700));
        controller.close();
      },
    }));
    await expect(readBoundedResponseText(streamed, 1_024)).rejects.toThrow("1 KiB limit");
  });

  it("handles byte and MiB limits, empty bodies, and untrusted length headers", async () => {
    expect(new ResponseLimitError(7).message).toContain("7 byte limit");
    expect(new ResponseLimitError(1_048_576).message).toContain("1 MiB limit");
    await expect(readBoundedResponseText(new Response(null), 7)).resolves.toBe("");
    await expect(readBoundedResponseText(new Response("ok", {
      headers: { "Content-Length": "9007199254740992" },
    }), 7)).resolves.toBe("ok");
    await expect(readBoundedResponseText(new Response("ok"), 1.5)).rejects.toThrow(TypeError);
  });

  it("cancels malformed UTF-8 streams and rejects unsuccessful or shapeless JSON", async () => {
    await expect(readBoundedResponseText(new Response(Uint8Array.of(0xff)), 7)).rejects.toBeInstanceOf(TypeError);
    await expect(readBoundedJsonObject(new Response(JSON.stringify({ detail: "bounded rejection" }), {
      status: 422,
    }), 1_024)).rejects.toThrow("bounded rejection");
    await expect(readBoundedJsonObject(new Response(null), 1_024)).rejects.toThrow(
      "The service returned an unexpected JSON shape.",
    );
  });

  it("never reflects non-JSON proxy bodies while retaining bounded JSON details", () => {
    const response = new Response(null, { status: 502 });
    const canary = "private-upstream-stack-canary";
    expect(publicHttpError(response, `<html>${canary}</html>`).message).toBe(
      "The service rejected the request (HTTP 502).",
    );
    expect(publicHttpError(response, JSON.stringify({ detail: "bounded contract rejection" })).message)
      .toBe("bounded contract rejection");
    expect(publicHttpError(response, JSON.stringify({ detail: canary.repeat(100) })).message)
      .not.toContain(canary);
    expect(publicHttpError(response, "").message).toBe("The service rejected the request (HTTP 502).");
  });

  it("recognizes cross-realm-shaped abort errors without relying on Error inheritance", () => {
    expect(isAbortError({ name: "AbortError" })).toBe(true);
    expect(isAbortError(new Error("network failed"))).toBe(false);
    expect(isAbortError(null)).toBe(false);
  });
});
