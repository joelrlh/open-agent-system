import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:net";
import { resolve } from "node:path";

const token = "fixture-smoke-token-with-enough-entropy";
const protocolVersion = "2025-11-25";

async function availablePort() {
  const server = createServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const { port } = address;
  server.close();
  await once(server, "close");
  return port;
}

const port = await availablePort();
const origin = `http://127.0.0.1:${port}`;
const wrangler = spawn(
  resolve("node_modules/.bin/wrangler"),
  [
    "dev",
    "--config",
    "deploy/cloudflare-worker/wrangler.jsonc",
    "--ip",
    "127.0.0.1",
    "--port",
    String(port),
    "--var",
    `RESEARCH_FIXTURE_TOKEN:${token}`,
  ],
  { stdio: ["ignore", "pipe", "pipe"] },
);

let logs = "";
for (const stream of [wrangler.stdout, wrangler.stderr]) {
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    logs = `${logs}${chunk}`.slice(-8000);
  });
}

async function waitUntilReady() {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (wrangler.exitCode !== null) {
      throw new Error(`wrangler exited before readiness\n${logs}`);
    }
    try {
      const response = await fetch(`${origin}/health`);
      if (response.status === 200) return;
    } catch {
      // Startup connection failures are expected until the local listener binds.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 250));
  }
  throw new Error(`worker did not become ready\n${logs}`);
}

async function rpc(id, method, params = {}) {
  const response = await fetch(`${origin}/mcp`, {
    body: JSON.stringify({ id, jsonrpc: "2.0", method, params }),
    headers: {
      accept: "application/json, text/event-stream",
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "mcp-protocol-version": protocolVersion,
    },
    method: "POST",
  });
  assert.equal(response.status, 200);
  return response.json();
}

try {
  await waitUntilReady();

  const health = await fetch(`${origin}/health`);
  assert.equal(health.status, 200);
  assert.equal(health.headers.get("cache-control"), "no-store");
  assert.equal(health.headers.get("x-content-type-options"), "nosniff");
  assert.deepEqual(await health.json(), { schema_version: 1, status: "ok" });

  const missing = await fetch(`${origin}/missing`);
  assert.equal(missing.status, 404);
  assert.deepEqual(await missing.json(), { error: "not_found" });

  const unauthorized = await fetch(`${origin}/mcp`, {
    body: JSON.stringify({ id: 1, jsonrpc: "2.0", method: "ping" }),
    headers: { "content-type": "application/json" },
    method: "POST",
  });
  assert.equal(unauthorized.status, 401);

  const initialized = await rpc(2, "initialize", {
    capabilities: {},
    clientInfo: { name: "worker-smoke", version: "1.0.0" },
    protocolVersion,
  });
  assert.equal(initialized.result.protocolVersion, protocolVersion);
  assert.equal(initialized.result.serverInfo.name, "Open Agent Research Fixture");

  const tools = await rpc(3, "tools/list");
  assert.deepEqual(tools.result.tools.map(({ name }) => name).sort(), [
    "research.fetch",
    "research.search",
  ]);

  const search = await rpc(4, "tools/call", {
    arguments: { limit: 1, query: "five layers energy applications" },
    name: "research.search",
  });
  assert.equal(search.result.structuredContent.results[0].source_id, "five-layer-stack");
  assert.equal(
    search.result.structuredContent.results[0].uri,
    "https://research.fixture.test/sources/five-layer-stack",
  );

  const malformed = await rpc(5, "tools/call", {
    arguments: { extra: true, uri: "https://169.254.169.254/latest" },
    name: "research.fetch",
  });
  assert.equal(malformed.result.isError, true);

  const methodDenied = await fetch(`${origin}/mcp`, {
    headers: { authorization: `Bearer ${token}` },
  });
  assert.equal(methodDenied.status, 405);

  const duplicateHeaders = new Headers({ "content-type": "application/json" });
  duplicateHeaders.append("authorization", `Bearer ${token}`);
  duplicateHeaders.append("authorization", `Bearer ${token}`);
  const duplicateDenied = await fetch(`${origin}/mcp`, {
    body: JSON.stringify({ id: 6, jsonrpc: "2.0", method: "ping" }),
    headers: duplicateHeaders,
    method: "POST",
  });
  assert.equal(duplicateDenied.status, 401);

  console.log("worker smoke: ok");
} finally {
  wrangler.kill("SIGTERM");
  await Promise.race([
    once(wrangler, "exit"),
    new Promise((resolveDelay) => setTimeout(resolveDelay, 3000)),
  ]);
  if (wrangler.exitCode === null) wrangler.kill("SIGKILL");
}
