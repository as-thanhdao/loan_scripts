#!/usr/bin/env node
/**
 * Add blacklist monitors to Hetrix from a CSV file.
 *
 * CSV format: a header row with a "domain" column and an optional "label"
 * column. If there's no "label" column, the domain itself is used as the label.
 *
 * Usage:
 *   node add_domain.js
 */

const fs = require("fs");
const path = require("path");

process.loadEnvFile(path.join(__dirname, ".env"));

// ============================================================
// CONFIGURATION
// ============================================================

const HETRIX_API_KEY = process.env.HETRIX_API_KEY;
const HETRIX_V2_BASE = "https://api.hetrixtools.com/v2";
const HETRIX_V3_BASE = "https://api.hetrixtools.com/v3";
const HETRIX_CONTACT_LIST_ID = process.env.HETRIX_CONTACT_LIST_ID;
const HETRIX_PER_PAGE = 1000;

// ============================================================
// LOGGING
// ============================================================

function timestamp() {
  return new Date().toISOString().replace("T", " ").slice(0, 19);
}

const log = {
  info:  (msg, ...args) => console.log(`${timestamp()}  INFO      ${fmt(msg, args)}`),
  warn:  (msg, ...args) => console.warn(`${timestamp()}  WARNING   ${fmt(msg, args)}`),
  debug: (msg, ...args) => process.env.DEBUG && console.log(`${timestamp()}  DEBUG     ${fmt(msg, args)}`),
  error: (msg, ...args) => console.error(`${timestamp()}  ERROR     ${fmt(msg, args)}`),
};

function fmt(msg, args) {
  if (!args.length) return msg;
  return msg.replace(/%[sdif%]/g, () => args.shift() ?? "");
}

// ============================================================
// CSV PARSING
// ============================================================

function parseCsvLine(line) {
  const fields = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (inQuotes) {
      if (c === '"' && line[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') {
        inQuotes = false;
      } else {
        field += c;
      }
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ",") {
      fields.push(field);
      field = "";
    } else {
      field += c;
    }
  }
  fields.push(field);
  return fields.map(f => f.trim());
}

function parseDomainsCsv(filePath) {
  const raw = fs.readFileSync(filePath, "utf8");
  const lines = raw.split(/\r?\n/).filter(line => line.trim() !== "");
  if (lines.length === 0) throw new Error(`CSV file is empty: ${filePath}`);

  const header = parseCsvLine(lines[0]).map(h => h.toLowerCase());
  const domainIdx = header.indexOf("domain");
  const labelIdx = header.indexOf("label");
  if (domainIdx === -1) {
    throw new Error(`CSV file must have a "domain" column — got header: ${header.join(", ")}`);
  }

  const rows = [];
  for (const line of lines.slice(1)) {
    const fields = parseCsvLine(line);
    const domain = fields[domainIdx];
    if (!domain) continue;
    const label = labelIdx !== -1 ? fields[labelIdx] || domain : domain;
    rows.push({ domain, label });
  }
  return rows;
}

// ============================================================
// HETRIX
// ============================================================

async function hetrixV3Request(reqPath, params = {}) {
  if (!HETRIX_API_KEY) throw new Error("HETRIX_API_KEY env var is not set");
  const url = new URL(`${HETRIX_V3_BASE}/${reqPath}`);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${HETRIX_API_KEY}` },
    signal: AbortSignal.timeout(30_000),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`Hetrix HTTP ${resp.status} — ${url}\n${text}`);
  }
  return resp.json();
}

async function getHetrixMonitors() {
  const result = {}; // { target: monitor_id }
  let page = 1;

  while (true) {
    const data = await hetrixV3Request("blacklist-monitors", { per_page: HETRIX_PER_PAGE, page });
    const monitors = data.monitors ?? [];
    for (const m of monitors) result[m.target] = m.id;

    const next = data.meta?.pagination?.next;
    log.debug("Hetrix page %d/%d — %d monitors so far", page, data.meta?.pagination?.last, Object.keys(result).length);
    if (!next) break;
    page = next;
  }

  log.info("Hetrix  → %d existing monitors loaded", Object.keys(result).length);
  return result;
}

async function addToHetrix(target, label) {
  log.info("  ADD    %s  (%s)", target, label);
  if (!HETRIX_API_KEY) throw new Error("HETRIX_API_KEY env var is not set");

  const form = new FormData();
  form.append("target", target);
  form.append("label", label);
  form.append("contact", HETRIX_CONTACT_LIST_ID);

  const url = `${HETRIX_V2_BASE}/${HETRIX_API_KEY}/blacklist/add/`;
  const resp = await fetch(url, { method: "POST", body: form, signal: AbortSignal.timeout(30_000) });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`Hetrix HTTP ${resp.status} — ${url}\n${text}`);
  }
  return resp.json();
}

// ============================================================
// MAIN
// ============================================================

async function main() {
  const csvPath = path.join(__dirname, "domains.csv");

  log.info("=== Step 1: Reading domains from CSV ===");
  const rows = parseDomainsCsv(path.resolve(csvPath));
  log.info("CSV → %d domains found", rows.length);

  log.info("=== Step 2: Fetching existing Hetrix monitors ===");
  const hetrixMonitors = await getHetrixMonitors();

  log.info("=== Step 3: Adding domains to Hetrix ===");
  let added = 0, skipped = 0, failed = 0;

  for (const { domain, label } of rows) {
    if (domain in hetrixMonitors) {
      skipped++; // already monitored
      continue;
    }
    try {
      await addToHetrix(domain, label);
      added++;
    } catch (err) {
      log.error("  FAILED %s — %s", domain, err.message);
      failed++;
    }
  }

  log.info("=== Done === added=%d  skipped=%d  failed=%d", added, skipped, failed);
}

main().catch(err => {
  log.error(err.message);
  process.exit(1);
});
