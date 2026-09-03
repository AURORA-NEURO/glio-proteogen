import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    include: ["tests/unit/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: [
        "src/lib/**/*.ts",
        "src/app/api/**/route.ts",
        "src/app/healthz/route.ts",
        "next.config.ts",
      ],
      reporter: ["text", "json-summary", "lcov"],
      reportsDirectory: "coverage",
      thresholds: {
        branches: 95,
        functions: 95,
        lines: 95,
        statements: 95,
        "next.config.ts": { 100: true },
        "src/app/api/**/route.ts": { 100: true },
        "src/app/healthz/route.ts": { 100: true },
      },
    },
  },
});
