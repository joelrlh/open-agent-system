import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const bundle = await readFile("dist/cloudflare-worker/index.js", "utf8");
const excludedServerOnlyPackages = ["@hono/node-server", "serve-static", "sharp", "libvips"];

for (const packageName of excludedServerOnlyPackages) {
  assert.equal(
    bundle.includes(packageName),
    false,
    `deployed Worker bundle unexpectedly contains ${packageName}`,
  );
}

console.log("worker bundle audit: server-only advisory paths absent");
