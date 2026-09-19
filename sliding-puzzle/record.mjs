// Headless recording, for when the main display is busy (record.sh needs the screen).
// Playwright recordVideo is 1x, so the viewport is 2560×1440 and the page is zoomed 2x:
// same pixels as a 1280×720 retina window, with the even frame timing recordVideo gives.
//   NODE_PATH=<dir with playwright> node sliding-puzzle/record.mjs <name> [depth=12] [maxSeconds=70]
// Needs the server on :3459 (SIF_CACHE=0). Writes rec-<name>.webm and rec-<name>.json (title every 200ms);
// encode with:
//   ffmpeg -y -ss 1.0 -to 45 -i rec-<name>.webm -vf "format=yuv420p" -r 30 -c:v libx264 -preset slow -crf 18 -movflags +faststart sliding-puzzle/demo.mp4
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
const exe = process.env.HOME + "/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing";
const [,, name = "take", depth = "12", maxSecs = "70"] = process.argv;
const out = process.env.OUT || ".";
const b = await chromium.launch({ executablePath: exe, headless: true });
const ctx = await b.newContext({ viewport: { width: 2560, height: 1440 }, colorScheme: "dark", recordVideo: { dir: out, size: { width: 2560, height: 1440 } } });
const p = await ctx.newPage();
await p.addInitScript(() => { document.addEventListener("DOMContentLoaded", () => { document.body.style.zoom = "2"; }); });
await p.goto(`http://127.0.0.1:3459/?demo=1&depth=${depth}`);
await p.evaluate(() => { document.body.style.zoom = "2"; dispatchEvent(new Event("resize")); });
const log = []; const t0 = Date.now();
while (Date.now() - t0 < +maxSecs * 1000) {
  const s = await p.evaluate(() => ({ title: document.title, moves: window.__jev.moves, solved: window.__jev.solved, requests: window.__jev.requests }));
  log.push({ t: (Date.now() - t0) / 1000, ...s });
  if (s.solved && s.moves > 0) { await p.waitForTimeout(2500); break; }
  await p.waitForTimeout(200);
}
const video = p.video();
await ctx.close(); await b.close();
const file = await video.path();
fs.renameSync(file, path.join(out, `rec-${name}.webm`));
fs.writeFileSync(path.join(out, `rec-${name}.json`), JSON.stringify(log));
const last = log.at(-1);
console.log(`rec-${name}.webm`, "seconds", last.t.toFixed(1), "moves", last.moves, "requests", last.requests, "solved", last.solved);
