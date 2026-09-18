const fs = await import("node:fs/promises");
const DIR = (process.env.OUT || "/tmp/bug-hunter-demo") + "/frames";
await fs.mkdir(DIR, { recursive: true });
const t = await taskSpace("bug-hunter demo"); const p = t.page("p1");
await p.goto("http://localhost:3458/");
await p.cdp("Emulation.setDeviceMetricsOverride", { width: 1280, height: 720, deviceScaleFactor: 2, mobile: false });
await p.waitForFunction(() => document.querySelectorAll('.row.hot, .row.pending').length === 0 && document.querySelectorAll('.row').length >= 8 && document.getElementById('src').value.includes('except ValueError'), undefined, { timeout: 30000 });
await p.evaluate(() => { document.getElementById('sound').style.display = 'none'; });
await p.waitForTimeout(800);

const stamps = []; let n = 0, on = true;
await p.events();
await p.cdp("Page.startScreencast", { format: "jpeg", quality: 90, maxWidth: 2560, maxHeight: 1440, everyNthFrame: 1 });
const rec = (async () => {
  while (on) {
    const evs = await p.events();
    for (const e of evs) {
      if (e.method !== "Page.screencastFrame") continue;
      n++;
      await fs.writeFile(`${DIR}/f${String(n).padStart(5, "0")}.jpg`, Buffer.from(e.params.data, "base64"));
      stamps.push(e.params.metadata.timestamp);
      await p.cdp("Page.screencastFrameAck", { sessionId: e.params.sessionId });
    }
    await new Promise(r => setTimeout(r, 15));
  }
})();

const sleep = ms => new Promise(r => setTimeout(r, ms));
// Put the caret after `needle`, scroll it to mid-screen, delete it key by key, type the replacement, save.
async function replace(needle, text) {
  const len = await p.evaluate((needle) => {
    const t = document.getElementById('src'); const a = t.value.indexOf(needle);
    if (a < 0) throw new Error("needle not found: " + needle);
    const line = t.value.slice(0, a).split('\n').length - 1;
    t.scrollTop = Math.max(0, line * 24 - t.getBoundingClientRect().height / 2 + 12);
    t.focus(); t.setSelectionRange(a + needle.length, a + needle.length);
    t.dispatchEvent(new Event('scroll'));
    return needle.length;
  }, needle);
  await sleep(900);
  // Chrome re-scrolls the caret to the top edge on the first edit; put the line back mid-screen after it.
  await p.keyboard.press("Backspace");
  await p.evaluate((needle) => {
    const t = document.getElementById('src'); const a = t.value.indexOf(needle.slice(0, -1));
    const line = t.value.slice(0, a).split('\n').length - 1;
    t.scrollTop = Math.max(0, line * 24 - t.getBoundingClientRect().height / 2 + 12);
    t.dispatchEvent(new Event('scroll'));
  }, needle);
  for (let i = 1; i < len; i++) { await p.keyboard.press("Backspace"); }
  await sleep(350);
  await p.keyboard.type(text, { delay: 65 });
  await sleep(900);
  await p.keyboard.press("Meta+s");
}

await sleep(2500);
await replace("return low <= value <= high", "return low <= value < high");          await sleep(3600);
await replace("except ValueError:\n        return default", "except:\n        pass"); await sleep(3600);
await replace("tags=None):\n    tags = [] if tags is None else list(tags)\n", "tags=[]):\n"); await sleep(3600);
await replace('"SELECT * FROM users WHERE name = ?", (name,)', 'f"SELECT * FROM users WHERE name = \'{name}\'"'); await sleep(3800);
await replace("return low <= value < high", "return low <= value <= high");           await sleep(3600);
await sleep(2500);

on = false; await rec;
await p.cdp("Page.stopScreencast", {});
await fs.writeFile(`${DIR}/stamps.json`, JSON.stringify(stamps));
console.log({ frames: n, seconds: (stamps[stamps.length - 1] - stamps[0]).toFixed(1) });
console.log(await p.evaluate(() => document.getElementById('stats').textContent));
