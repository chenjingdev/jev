// server.js — static files for the browser game + one Jev endpoint, POST /api/move.
// The browser enumerates the legal slides with the engine's numbers; Jev picks one. The API key
// never leaves this process.

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { APIError, TypeSafeClient } from "@typesafe-ai/sdk";
import { buildMove, validateMove } from "./questions.js";

const PORT = Number(process.env.PORT ?? 3462);
const MODEL = "jev-latest";
const ROOT = fileURLToPath(new URL("./public/", import.meta.url));
const MAX_BODY_BYTES = 256 * 1024;

if (!process.env.TYPESAFE_API_KEY || !process.env.TYPESAFE_API_KEY.trim()) {
  console.error(
    "TYPESAFE_API_KEY is not set.\n" +
      "Start the server through 1Password so the key is injected and masked:\n" +
      "  op run --env-file=.env.tpl -- npm start",
  );
  process.exit(1);
}

const client = new TypeSafeClient({
  defaultModel: MODEL,
  timeout: 15000,
  retry: { maxRetries: 1, backoffInitialMs: 500 },
});

const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
};

function sendJson(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
    "cache-control": "no-store",
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error("request body too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

async function serveStatic(res, urlPath) {
  const relative = urlPath === "/" ? "index.html" : urlPath.replace(/^\/(public\/)?/, "");
  const safe = normalize(relative);
  if (safe.startsWith("..") || safe.startsWith(sep) || safe.includes("\0")) {
    res.writeHead(403, { "content-type": "text/plain; charset=utf-8" });
    res.end("forbidden");
    return;
  }
  try {
    const data = await readFile(join(ROOT, safe));
    res.writeHead(200, {
      "content-type": CONTENT_TYPES[extname(safe).toLowerCase()] ?? "application/octet-stream",
      "content-length": data.length,
      "cache-control": "no-store",
    });
    res.end(data);
  } catch {
    res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    res.end("not found");
  }
}

async function handleMove(req, res) {
  let body;
  try {
    body = JSON.parse(await readBody(req));
  } catch (err) {
    sendJson(res, 400, { error: "invalid JSON body: " + err.message });
    return;
  }
  const problem = validateMove(body);
  if (problem) {
    sendJson(res, 400, { error: problem });
    return;
  }

  const { state, questions } = buildMove(body);
  const started = Date.now();
  let result;
  try {
    // Both questions ride in one request; they see the same state and not each other's answer.
    result = await client.systemOne({ state, model: MODEL, questions });
  } catch (err) {
    const status = err instanceof APIError ? err.status : "network";
    console.error(`move failed status=${status} msg=${err.message}`);
    sendJson(res, 502, {
      error: "TypeSafe request failed after one retry",
      detail: err.message,
      status: err instanceof APIError ? err.status : undefined,
    });
    return;
  }
  const latencyMs = Date.now() - started;
  const mv = result.answers.move;
  const payload = {
    choice: mv.choice,
    probabilities: mv.probabilities,
    confidence: mv.confidence,
    danger: result.answers.danger.noul,
    latencyMs,
    usage: result.usage,
    model: result.model,
  };
  const probs = Object.entries(mv.probabilities)
    .map(([k, v]) => `${k}:${v.toFixed(2)}`)
    .join(" ");
  console.log(
    `t=${(Date.now() / 1000).toFixed(3)} move#${body.moveNo ?? "?"} max=${body.facts?.max ?? "?"} ${probs} → ${mv.choice} ` +
      `danger=${payload.danger.toFixed(2)} latency=${latencyMs}ms ` +
      `tokens=${result.usage.input_tokens}in/${result.usage.output_tokens}out`,
  );
  sendJson(res, 200, payload);
}

const server = createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  const path = decodeURIComponent(url.pathname);

  if (req.method === "POST" && path === "/api/move") {
    handleMove(req, res).catch((err) => {
      console.error("unhandled move error:", err.message);
      if (!res.headersSent) sendJson(res, 500, { error: "internal error" });
    });
    return;
  }
  if (req.method === "GET" || req.method === "HEAD") {
    serveStatic(res, path).catch(() => {
      res.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
      res.end("internal error");
    });
    return;
  }
  res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
  res.end("not found");
});

server.listen(PORT, () => {
  console.log(`Jev 2048 on http://localhost:${PORT}  (model ${MODEL})`);
});
