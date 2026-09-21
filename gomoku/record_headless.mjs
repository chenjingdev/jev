// Headless takes: Playwright's video recorder, no screen involved - other windows on
// this Mac cannot get into the frame. Records one full game per take and keeps going
// until a take ends with a white (Jev) win. Needs the server on :3460 and playwright
// resolvable from this file (a node_modules symlink beside it, or copy it next to one).
//
//   node record_headless.mjs [maxTakes=6] [maxSecs=150]            # bot black
//   BLACK=opus FF=8 node record_headless.mjs 4 900                  # Opus black, mark its turns for 8x
//
// Writes takeN.webm and takeN.json (the page's phase timeline: opus / jev / idle, in
// video seconds). speedup.py turns a take into demo.mp4 with the Opus turns sped up.
import { chromium } from "playwright";
import fs from "node:fs";
const exe = process.env.HOME + "/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing";
const maxTakes = +(process.argv[2] || 6), maxSecs = +(process.argv[3] || 150);
const black = process.env.BLACK || "bot", ff = process.env.FF || "";
const url = `http://localhost:3460/?demo=1&black=${black}&scale=1.5` + (ff ? `&ff=${ff}` : "");
const b = await chromium.launch({ headless: true, executablePath: exe });
for (let take = 1; take <= maxTakes; take++) {
  const ctxStart = Date.now();
  const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1, recordVideo: { dir: "rec", size: { width: 1920, height: 1080 } } });
  const p = await ctx.newPage();
  const t0 = Date.now();
  await p.goto(url);
  let s;
  while (Date.now() - t0 < maxSecs * 1000) {
    s = await p.evaluate(() => ({ games: window.__jev.games || 0, result: window.__jev.result, moves: window.__jev.moves, agree: window.__jev.agree, stones: window.__jev.history.length }));
    if (s.games >= 1) break;
    await p.waitForTimeout(250);
  }
  const end = (Date.now() - t0) / 1000;
  await p.waitForTimeout(3000);
  const tl = await p.evaluate(() => ({ t0wall: window.__jev.t0wall, timeline: window.__jev.timeline }));
  const offset = (tl.t0wall - ctxStart) / 1000;  // page clock -> video clock
  const timeline = tl.timeline.map(e => ({ t: +(e.t + offset).toFixed(2), phase: e.phase }));
  const path = await p.video().path();
  await ctx.close();
  const out = `take${take}.webm`; fs.renameSync(path, out);
  fs.writeFileSync(`take${take}.json`, JSON.stringify({ take, out, black, ff, end: +end.toFixed(1), ...s, timeline }));
  console.log(JSON.stringify({ take, out, end: +end.toFixed(1), ...s }));
  if (s.result === "white") break;
}
await b.close();
