// vision/screenshotter.js — Deterministic Puppeteer screenshot capture.
//
// Usage:
//   node screenshotter.js [options]
//
// Options:
//   --url <url>          Page URL to capture (default: http://localhost:3000)
//   --routes <json>      JSON array of route paths, e.g. '["/","/about"]'
//   --output <dir>       Output directory for screenshots (default: ./screenshots)
//   --width  <px>        Viewport width  (default: 1280)
//   --height <px>        Viewport height (default: 800)
//   --delay  <ms>        Wait after navigation before capture (default: 500)
//   --prefix <string>    Filename prefix (default: "screen")
//
// All screenshots are saved as PNG files with deterministic names:
//   <prefix>_<route_slug>_<widthxheight>.png
//
// Exit codes:
//   0 — all routes captured successfully
//   1 — one or more routes failed

"use strict";

const path   = require("path");
const fs     = require("fs");
const crypto = require("crypto");

// ── Argument parsing ─────────────────────────────────────────────────────────

function parseArgs(argv) {
  const args = {
    url:    "http://localhost:3000",
    routes: ["/"],
    output: path.join(process.cwd(), "screenshots"),
    width:  1280,
    height: 800,
    delay:  500,
    prefix: "screen",
  };

  for (let i = 2; i < argv.length; i++) {
    switch (argv[i]) {
      case "--url":    args.url    = argv[++i]; break;
      case "--routes": args.routes = JSON.parse(argv[++i]); break;
      case "--output": args.output = argv[++i]; break;
      case "--width":  args.width  = parseInt(argv[++i], 10); break;
      case "--height": args.height = parseInt(argv[++i], 10); break;
      case "--delay":  args.delay  = parseInt(argv[++i], 10); break;
      case "--prefix": args.prefix = argv[++i]; break;
    }
  }
  return args;
}

// ── Filename helpers ─────────────────────────────────────────────────────────

function routeToSlug(route) {
  return route.replace(/^\//, "").replace(/\//g, "_").replace(/[^a-zA-Z0-9_-]/g, "") || "root";
}

function screenshotFilename(prefix, route, width, height) {
  const slug = routeToSlug(route);
  return `${prefix}_${slug}_${width}x${height}.png`;
}

// ── Core capture ─────────────────────────────────────────────────────────────

async function captureRoute(browser, baseUrl, route, opts) {
  const page = await browser.newPage();

  // Deterministic viewport — no randomness
  await page.setViewport({ width: opts.width, height: opts.height, deviceScaleFactor: 1 });

  // Disable animations for reproducible frames
  await page.evaluateOnNewDocument(() => {
    const style = document.createElement("style");
    style.textContent = "*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }";
    document.head.appendChild(style);
  });

  const url = baseUrl.replace(/\/$/, "") + route;
  try {
    await page.goto(url, { waitUntil: "networkidle2", timeout: 30000 });
  } catch (err) {
    // Fallback: wait for DOMContentLoaded if networkidle2 times out
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
  }

  if (opts.delay > 0) {
    await new Promise(r => setTimeout(r, opts.delay));
  }

  const outDir = opts.output;
  fs.mkdirSync(outDir, { recursive: true });

  const filename = screenshotFilename(opts.prefix, route, opts.width, opts.height);
  const filepath = path.join(outDir, filename);

  await page.screenshot({ path: filepath, fullPage: false, type: "png" });

  // Compute a deterministic hash of the screenshot bytes for change detection
  const hash = crypto.createHash("sha256").update(fs.readFileSync(filepath)).digest("hex").slice(0, 12);

  await page.close();

  return {
    route,
    filename,
    filepath,
    hash,
    width:  opts.width,
    height: opts.height,
    url,
    capturedAt: new Date().toISOString(),
  };
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  let puppeteer;
  try {
    puppeteer = require("puppeteer");
  } catch {
    console.error("ERROR: puppeteer is not installed — run: npm install puppeteer");
    process.exit(1);
  }

  const opts    = parseArgs(process.argv);
  const results = [];
  let   failures = 0;

  const browser = await puppeteer.launch({
    headless: "new",
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--deterministic-fetch",
    ],
  });

  for (const route of opts.routes) {
    try {
      const info = await captureRoute(browser, opts.url, route, opts);
      console.log(`✅  ${route}  →  ${info.filename}  (sha256: ${info.hash})`);
      results.push({ ok: true, ...info });
    } catch (err) {
      console.error(`❌  ${route}  →  ${err.message}`);
      results.push({ ok: false, route, error: err.message });
      failures++;
    }
  }

  await browser.close();

  // Write a manifest JSON next to the screenshots
  const manifest = {
    capturedAt: new Date().toISOString(),
    baseUrl:    opts.url,
    viewport:   { width: opts.width, height: opts.height },
    results,
  };
  const manifestPath = path.join(opts.output, `${opts.prefix}_manifest.json`);
  fs.mkdirSync(opts.output, { recursive: true });
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  console.log(`\nManifest written → ${manifestPath}`);

  process.exit(failures > 0 ? 1 : 0);
}

main().catch(err => {
  console.error("Fatal:", err);
  process.exit(1);
});
