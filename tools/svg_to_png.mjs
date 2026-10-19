// Render an SVG file to PNG with the Chromium that Playwright ships.
//   node tools/svg_to_png.mjs in.svg out.png [scale]
// Dev-only helper (not a project dependency). Finds Playwright via PLAYWRIGHT_MODULE, or NODE_PATH, or /opt/node-tools.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const [, , input, output, scaleArg] = process.argv;
if (!input || !output) {
  console.error("usage: node tools/svg_to_png.mjs in.svg out.png [scale]");
  process.exit(2);
}
const require = createRequire(import.meta.url);
const candidates = [process.env.PLAYWRIGHT_MODULE, "playwright", "/opt/node-tools/node_modules/playwright"].filter(Boolean);
let playwright;
for (const c of candidates) {
  try { playwright = require(c); break; } catch { /* try next */ }
}
if (!playwright) { console.error("playwright module not found"); process.exit(3); }

const svg = readFileSync(input, "utf8");
const m = svg.match(/width="(\d+)"\s+height="(\d+)"/);
const w = m ? Number(m[1]) : 1600, h = m ? Number(m[2]) : 1000;
const browser = await playwright.chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: Number(scaleArg || 1.5) });
await page.setContent(`<html><body style="margin:0;background:#fff">${svg}</body></html>`);
await page.screenshot({ path: output, clip: { x: 0, y: 0, width: w, height: h } });
await browser.close();
console.log(`wrote ${output} (${w}x${h} @${scaleArg || 1.5}x)`);
