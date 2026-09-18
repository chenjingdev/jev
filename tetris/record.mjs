// Records the recording-mode page (?clean=1) at 2x device pixels via the CDP screencast.
// Needs a running server on :3456 and playwright resolvable (NODE_PATH=<dir with playwright>).
//   node record.mjs <name> [seconds=75] [width=1080] [height=900]
// Writes rec-<name>/ (jpeg frames + list.txt) and rec-<name>.json (phase/stats every 100ms);
// encode a segment with:
//   cd rec-<name> && ffmpeg -f concat -safe 0 -i list.txt -ss 32 -t 45 -r 30 -c:v libx264 -crf 18 -pix_fmt yuv420p -movflags +faststart ../demo.mp4
import { chromium } from "playwright";
import fs from "node:fs";
const exe = process.env.HOME + "/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing";
const [,, name = "take", secs = "75", W = "1080", H = "900"] = process.argv;
const viewport = { width: +W, height: +H };
const dir = `rec-${name}`; fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir);
const b = await chromium.launch({ executablePath: exe, headless: true, args: ["--force-device-scale-factor=2"] });
const ctx = await b.newContext({ viewport, colorScheme: "dark" });
const p = await ctx.newPage();
const cdp = await ctx.newCDPSession(p);
let n = 0; const frames = [];
cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
  const f = `${dir}/f${String(n++).padStart(5, "0")}.jpg`;
  fs.writeFileSync(f, Buffer.from(data, "base64"));
  frames.push({ f, t: metadata.timestamp });
  await cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
});
await p.goto("http://localhost:3456/?clean=1");
await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: viewport.width * 2, maxHeight: viewport.height * 2, everyNthFrame: 1 });
const log = []; const t0 = Date.now();
while (Date.now() - t0 < +secs * 1000) {
  const s = await p.evaluate(() => ({ phase: window.__jev.phase, over: window.__jev.over, stats: window.__jev.stats, pieces: window.__jev.log.length }));
  log.push({ t: (Date.now() - t0) / 1000, ...s });
  if (s.over) { await p.waitForTimeout(1500); break; }
  await p.waitForTimeout(100);
}
await cdp.send("Page.stopScreencast");
await ctx.close(); await b.close();
// concat list with per-frame durations
const lines = [];
for (let i = 0; i < frames.length; i++) {
  const d = i + 1 < frames.length ? frames[i + 1].t - frames[i].t : 0.04;
  lines.push(`file '${frames[i].f.split("/")[1]}'`, `duration ${Math.max(d, 0.001).toFixed(4)}`);
}
lines.push(`file '${frames.at(-1).f.split("/")[1]}'`);
fs.writeFileSync(`${dir}/list.txt`, lines.join("\n"));
fs.writeFileSync(`rec-${name}.json`, JSON.stringify({ log, frames: frames.length, span: frames.at(-1).t - frames[0].t }));
console.log("frames", frames.length, "span", (frames.at(-1).t - frames[0].t).toFixed(1), "last", JSON.stringify(log.at(-1)));
