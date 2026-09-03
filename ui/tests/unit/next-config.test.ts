import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.resetModules();
  vi.unstubAllEnvs();
});

describe("Next.js backend proxy configuration", () => {
  it("uses the local API default and preserves the standalone build", async () => {
    vi.stubEnv("GLIO_API_URL", "");
    delete process.env.GLIO_API_URL;
    const { default: config } = await import("../../next.config");

    expect(config.output).toBe("standalone");
    expect(config.agentRules).toBe(false);
    expect(config.outputFileTracingRoot).toBeTypeOf("string");
    await expect(config.rewrites?.()).resolves.toEqual([{
      destination: "http://127.0.0.1:8000/:path*",
      source: "/backend/:path*",
    }]);
  });

  it("routes path and query suffixes to the configured linked API", async () => {
    vi.stubEnv("GLIO_API_URL", "http://glio-proteogen:8000");
    const { default: config } = await import("../../next.config");

    await expect(config.rewrites?.()).resolves.toEqual([{
      destination: "http://glio-proteogen:8000/:path*",
      source: "/backend/:path*",
    }]);
  });
});
