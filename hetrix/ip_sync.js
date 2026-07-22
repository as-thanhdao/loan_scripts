#!/usr/bin/env node
/**
 * Sync Charon/Pluto IPs with Hetrix blacklist monitoring.
 *
 * Logic:
 *   - IPs active within the last 30 days → ensure they are ON Hetrix
 *   - IPs inactive for 30+ days         → ensure they are OFF Hetrix
 */

const path = require("path");

process.loadEnvFile(path.join(__dirname, ".env"));

// ============================================================
// CONFIGURATION
// ============================================================

const CHARON_API_BASE = "https://charonmail.com/ga/api/v3/eng";
const CHARON_AUTH = { user: "admin", pass: process.env.CHARON_PASSWORD };

const PLUTO_API_BASE = "https://plutomailsystem.com/ga/api/v3/eng";
const PLUTO_AUTH = { user: "admin", pass: process.env.PLUTO_PASSWORD };

const UNIVERSE_API_BASE = "https://universe.audienceserv.com/v1";
const UNIVERSE_TOKEN = process.env.UNIVERSE_TOKEN;

const HETRIX_API_KEY = process.env.HETRIX_API_KEY;
const HETRIX_V2_BASE = "https://api.hetrixtools.com/v2";
const HETRIX_V3_BASE = "https://api.hetrixtools.com/v3";
const HETRIX_CONTACT_LIST_ID = process.env.HETRIX_CONTACT_LIST_ID;
const HETRIX_PER_PAGE = 1000;

const ACTIVITY_DAYS = 30;
const BIGQUERY_PROJECT_ID = "as-axe";

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
// HELPERS
// ============================================================

function basicAuthHeader({ user, pass }) {
  return "Basic " + Buffer.from(`${user}:${pass}`).toString("base64");
}

async function getJson(url, options = {}) {
  const resp = await fetch(url, { ...options, signal: AbortSignal.timeout(30_000) });
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`HTTP ${resp.status} ${resp.statusText} — ${url}\n${body}`);
  }
  return resp.json();
}

// ============================================================
// STEP 1: Fetch IPs from Charon / Pluto
// ============================================================

async function fetchAllIpsFromSystem(baseUrl, auth, systemName) {
  const allIps = [];
  let page = 1;

  while (true) {
    const url = `${baseUrl}/ip_addresses?page=${page}`;
    const body = await getJson(url, {
      headers: { Authorization: basicAuthHeader(auth) },
    });

    if (!body.success) {
      throw new Error(`${systemName} API error on page ${page}: ${JSON.stringify(body)}`);
    }

    const batch = body.data.ip_addresses;
    allIps.push(...batch);

    const { num_pages } = body.data.pagination;
    log.debug("%s page %d/%d — %d IPs so far", systemName, page, num_pages, allIps.length);

    if (page >= num_pages) break;
    page++;
  }

  log.info("%-8s → %d IPs fetched", systemName, allIps.length);
  return allIps; // [{id, name: "smtp1-1"}, ...]
}

// ============================================================
// STEP 2: Fetch Charon/Pluto IPs from Universe
// ============================================================

async function fetchUniverseIps() {
  if (!UNIVERSE_TOKEN) throw new Error("UNIVERSE_TOKEN env var is not set");

  const headers = { "x-access-token": UNIVERSE_TOKEN };
  const body = await getJson(`${UNIVERSE_API_BASE}/ipaddress`, { headers });

  const allIps = (body.ipaddress ?? []).filter(
    record => record.mailing_system === "Charon" || record.mailing_system === "Pluto"
  );

  log.info("Universe → %d Charon/Pluto IPs found", allIps.length);
  return allIps;
}

// ============================================================
// STEP 3: Check IP activity via BigQuery (PLACEHOLDER)
// ============================================================

async function getActiveIpsFromBigquery() {
  const query = `
    SELECT DISTINCT sending_ip, sending_system
    FROM \`audienceservwarehouse.staging.ga_charon_sendid_event\`
    WHERE send_date >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @activity_days DAY)
  `;

  const { BigQuery } = await import("@google-cloud/bigquery");
  const bq = new BigQuery({ projectId: BIGQUERY_PROJECT_ID });
  const [rows] = await bq.query({
    query,
    params: { activity_days: ACTIVITY_DAYS },
    types: { activity_days: "INT64" },
  });
  return new Map(rows.map(r => [r.sending_ip, r.sending_system]));
}

// ============================================================
// STEP 4: Hetrix management
// ============================================================

async function hetrixV3Request(path, params = {}) {
  if (!HETRIX_API_KEY) throw new Error("HETRIX_API_KEY env var is not set");
  const url = new URL(`${HETRIX_V3_BASE}/${path}`);
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
  const result = {}; // { ip_address: monitor_id }
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

async function addToHetrix(ipAddress, label = "", dryRun = false) {
  log.info("  ADD    %s  (%s)", ipAddress, label);
  if (dryRun) return;
  if (!HETRIX_API_KEY) throw new Error("HETRIX_API_KEY env var is not set");

  const form = new FormData();
  form.append("target", ipAddress);
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

async function removeFromHetrix(monitorId, ipAddress, dryRun = false) {
  log.info("  REMOVE %s  (monitor_id=%s)", ipAddress, monitorId);
  if (dryRun) return;
  if (!HETRIX_API_KEY) throw new Error("HETRIX_API_KEY env var is not set");

  const form = new FormData();
  form.append("target", ipAddress);

  const url = `${HETRIX_V2_BASE}/${HETRIX_API_KEY}/blacklist/delete/`;
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
  const dryRun = process.argv.includes("--dry-run");
  if (dryRun) log.warn("DRY RUN — no changes will be made to Hetrix");

  // --- Step 1 ---
  log.info("=== Step 1: Fetching IPs from Charon and Pluto ===");
  const [charonIps, plutoIps] = await Promise.all([
    fetchAllIpsFromSystem(CHARON_API_BASE, CHARON_AUTH, "Charon"),
    fetchAllIpsFromSystem(PLUTO_API_BASE, PLUTO_AUTH, "Pluto"),
  ]);

  const charonNames = new Set(charonIps.map(ip => ip.name));
  const plutoNames  = new Set(plutoIps.map(ip => ip.name));

  // --- Step 2 ---
  log.info("=== Step 2: Fetching IP details from Universe ===");
  const universeIps = await fetchUniverseIps();

  const relevant = universeIps.filter(r =>
    (r.mailing_system === "Charon" && charonNames.has(r.mta_name)) ||
    (r.mailing_system === "Pluto"  && plutoNames.has(r.mta_name))
  );
  log.info("Cross-matched: %d IPs from Universe match Charon/Pluto registries", relevant.length);

  // --- Step 3 ---
  log.info("=== Step 3: Checking activity in BigQuery ===");
  const activeIps = await getActiveIpsFromBigquery();

  // Join the active IPs (from BigQuery) back onto their full Universe records
  // so downstream steps have mta_name/mailing_system/etc, not just bare addresses.
  const activeRecords = relevant
    .filter(r => activeIps.has(r.ip_address))
    .map(r => ({ ...r, sending_system: activeIps.get(r.ip_address) }));
  const activeIpSet = new Set(activeRecords.map(r => r.ip_address));

  log.info("Active IPs (last %d days): %d", ACTIVITY_DAYS, activeRecords.length);
  log.info("Inactive IPs: %d", relevant.length - activeRecords.length);

  // --- Step 4 ---
  log.info("=== Step 4: Syncing with Hetrix ===");
  const hetrixMonitors = await getHetrixMonitors(); // { ip: monitor_id }

  let added = 0, removed = 0, skipped = 0;

  for (const record of relevant) {
    const ip    = record.ip_address;
    const label = record.host_name ? `${record.mta_name}.${record.host_name}` : record.mta_name ?? "";

    if (activeIpSet.has(ip)) {
      if (!(ip in hetrixMonitors)) {
        await addToHetrix(ip, label, dryRun);
        added++;
      } else {
        skipped++; // already monitored
      }
    } else {
      if (ip in hetrixMonitors) {
        await removeFromHetrix(hetrixMonitors[ip], ip, dryRun);
        removed++;
      } else {
        skipped++; // not on Hetrix and inactive
      }
    }
  }

  log.info("=== Done === added=%d  removed=%d  unchanged=%d", added, removed, skipped);
}

main().catch(err => {
  log.error(err.message);
  process.exit(1);
});
