// server.js — static files for the browser game + a single /api/decide endpoint
// that asks Jev where to put the current piece. The API key never leaves this process.

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { choice, noul, score, APIError, TypeSafeClient } from "@typesafe-ai/sdk";

const PORT = 3456;
const MODEL = "jev-latest";
const ROOT = fileURLToPath(new URL("./public/", import.meta.url));
const MAX_BODY_BYTES = 4 * 1024 * 1024;

if (!process.env.TYPESAFE_API_KEY || !process.env.TYPESAFE_API_KEY.trim()) {
  console.error(
    "TYPESAFE_API_KEY is not set.\n" +
      "Start the server through 1Password so the key is injected and masked:\n" +
      "  op run --env-file=.env.tpl -- npm start",
  );
  process.exit(1);
}

// One retry with exponential backoff on 408/429/5xx and connection errors,
// which is exactly the SDK's retry policy with maxRetries lowered to 1.
const client = new TypeSafeClient({
  defaultModel: MODEL,
  timeout: 15000,
  retry: { maxRetries: 1, backoffInitialMs: 500 },
});

const PLACEMENT_INSTRUCTIONS =
  "The player typed the instruction in `instruction`. Choose the placement of the current piece " +
  "(`current_piece`) that best follows that instruction, using each candidate's summary and its " +
  "resulting board in `candidates`. Each option key is a candidate id; its description tells you " +
  "where the piece lands and what the board looks like afterwards. `board_now` is the board before " +
  "the piece is placed and `next_piece` is the piece that arrives after this one. Follow the " +
  "instruction literally, even when it is bad Tetris. If the instruction is empty or does not apply " +
  "to this piece, choose the placement a strong Tetris player would make: clear lines, avoid " +
  "creating holes, and keep the stack low and flat.";

const SELF_DESTRUCTIVE_INSTRUCTIONS =
  "Does the player's instruction in `instruction` ask for play that will make the game end quickly " +
  "(for example building the stack tall, deliberately making holes, or filling only one side of the " +
  "board)?";

const INSTRUCTION_FIT_INSTRUCTIONS =
  "How well does the current board in `board_now` already match the player's instruction in " +
  "`instruction`? Judge the stack that is already there, not the move about to be made.";

const FIT_LEVELS = [
  "Not at all: the board shows no sign of the instruction, or it directly contradicts it — the " +
    "stack sits where the instruction said not to build, or the requested shape is nowhere on the board.",
  "Slightly: one or two blocks hint at the instruction but most of the stack ignores it — a couple of " +
    "pieces on the requested side while the rest is spread elsewhere.",
  "Mostly: the stack clearly follows the instruction with some stray blocks — the requested side, " +
    "shape or well is recognisable, with a few pieces out of place.",
  "Fully: the whole board obeys the instruction with nothing out of place — every block is where the " +
    "instruction asks and the requested shape, side or well is unmistakable.",
];

const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
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

function validateDecideRequest(body) {
  if (!body || typeof body !== "object") return "body must be a JSON object";
  if (typeof body.boardAscii !== "string") return "boardAscii must be a string";
  if (typeof body.pieceType !== "string") return "pieceType must be a string";
  if (!Array.isArray(body.candidates) || body.candidates.length === 0) {
    return "candidates must be a non-empty array";
  }
  if (body.candidates.length > 255) return "at most 255 candidates are allowed";
  for (const c of body.candidates) {
    if (!c || typeof c.id !== "string" || typeof c.summary !== "string") {
      return "each candidate needs a string id and summary";
    }
  }
  return null;
}

async function handleDecide(req, res) {
  let body;
  try {
    body = JSON.parse(await readBody(req));
  } catch (err) {
    sendJson(res, 400, { error: "invalid JSON body: " + err.message });
    return;
  }

  const problem = validateDecideRequest(body);
  if (problem) {
    sendJson(res, 400, { error: problem });
    return;
  }

  const instruction = typeof body.instruction === "string" ? body.instruction.trim() : "";
  const candidates = body.candidates;

  const state = {
    instruction,
    board_now: body.boardAscii,
    current_piece: body.pieceType,
    next_piece: typeof body.nextType === "string" ? body.nextType : "unknown",
    candidates: Object.fromEntries(
      candidates.map((c) => [
        c.id,
        { summary: c.summary, board_after: c.boardAfterAscii ?? "" },
      ]),
    ),
  };

  const criteria = Object.fromEntries(candidates.map((c) => [c.id, c.summary]));

  const started = Date.now();
  let result;
  try {
    // All three questions ride in one request; they see the same state and cannot see
    // each other's answers.
    result = await client.systemOne({
      state,
      model: MODEL,
      questions: {
        placement: choice(PLACEMENT_INSTRUCTIONS, criteria),
        self_destructive: noul(SELF_DESTRUCTIVE_INSTRUCTIONS, {
          true: "The instruction pushes toward a quick loss.",
          false: "The instruction is harmless or asks for solid play.",
        }),
        instruction_fit: score(INSTRUCTION_FIT_INSTRUCTIONS, FIT_LEVELS),
      },
    });
  } catch (err) {
    const status = err instanceof APIError ? err.status : "network";
    console.error(`decide failed status=${status} msg=${err.message}`);
    sendJson(res, 502, {
      error: "TypeSafe request failed after one retry",
      detail: err.message,
      status: err instanceof APIError ? err.status : undefined,
    });
    return;
  }
  const latencyMs = Date.now() - started;

  const placement = result.answers.placement;
  const fit = result.answers.instruction_fit;
  const { score: fitScore, ...fitRest } = fit;

  const payload = {
    choice: placement.choice,
    probabilities: placement.probabilities,
    confidence: placement.confidence,
    selfDestructive: result.answers.self_destructive.noul,
    instructionFit: { value: fitScore, ...fitRest },
    latencyMs,
    usage: result.usage,
  };

  console.log(
    `pieces=${state.current_piece}>${state.next_piece} latency=${latencyMs}ms ` +
      `tokens=${result.usage.input_tokens}in/${result.usage.output_tokens}out ` +
      `choice=${placement.choice} cands=${candidates.length} conf=${placement.confidence.toFixed(2)}`,
  );

  sendJson(res, 200, payload);
}

const server = createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  const path = decodeURIComponent(url.pathname);

  if (req.method === "POST" && path === "/api/decide") {
    handleDecide(req, res).catch((err) => {
      console.error("unhandled decide error:", err.message);
      if (!res.headersSent) sendJson(res, 500, { error: "internal error" });
    });
    return;
  }

  if (req.method === "GET" || req.method === "HEAD") {
    if (path === "/" || path === "/index.html" || path.startsWith("/public/")) {
      serveStatic(res, path).catch(() => {
        res.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
        res.end("internal error");
      });
      return;
    }
  }

  res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
  res.end("not found");
});

server.listen(PORT, () => {
  console.log(`Jev Tetris on http://localhost:${PORT}  (model ${MODEL})`);
});
