import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      exclude: ["**/index.ts"],
      include: ["deploy/cloudflare-worker/src/core.ts"],
      provider: "v8",
      reporter: ["text"],
      thresholds: {
        branches: 85,
        functions: 95,
        lines: 95,
        statements: 95,
      },
    },
    include: ["deploy/cloudflare-worker/test/**/*.test.ts"],
  },
});
