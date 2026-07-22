#!/usr/bin/env node
/**
 * Remove Sparkpost relay servers from Charon/Pluto (GA Engine).
 *
 * Lists relay servers via GET /ga/api/v3/eng/relay_servers, finds any whose
 * name contains "Sparkpost" (case-insensitive), and deletes them via
 * DELETE /ga/api/v3/eng/relay_servers/:id.
 *
 * Usage:
 *   node remove_sparkpost_relays.js
 *   (runs for both Charon and Pluto, deletes immediately)
 */

"use strict";

const fs = require("fs");
const path = require("path");

const { pluto_cred, charon_cred } = JSON.parse(
  fs.readFileSync(path.join(__dirname, "setup_domain", "ga", "credentials.json"), "utf8")
);

const SYSTEMS = {
  // charon: { host: "charonmail", cred: charon_cred },
  pluto: { host: "plutomailsystem", cred: pluto_cred },
};

const NAME_FILTER = "_sparkpost";

const IGNORE_IDS = {
  charon: [1500, 1554, 1564, 1577, 1718, 1740, 2070, 2071, 2072, 2073, 2074, 2101, 2102, 2130],
  pluto: [763, 4487, 4656, 4979]
};

// ============================================================
// LOGGING
// ============================================================

function ts() {
  return new Date().toISOString().replace("T", " ").slice(0, 19);
}

const log = {
  info: (msg, ...a) => console.log(`${ts()}  INFO   ${fmt(msg, a)}`),
  warn: (msg, ...a) => console.warn(`${ts()}  WARN   ${fmt(msg, a)}`),
  error: (msg, ...a) => console.error(`${ts()}  ERROR  ${fmt(msg, a)}`),
};

function fmt(msg, args) {
  if (!args.length) return msg;
  return msg.replace(/%[-\d]*[sdif%]/g, () => String(args.shift() ?? ""));
}

// ============================================================
// GA ENGINE API
// ============================================================

function authHeader(cred) {
  const [user, pass] = cred;
  return "Basic " + Buffer.from(`${user}:${pass}`).toString("base64");
}

async function gaRequest(host, auth, method, endpoint) {
  const resp = await fetch(`https://${host}.com/ga/api/v3/eng${endpoint}`, {
    method,
    headers: { Authorization: auth, "Content-Type": "application/json" },
    signal: AbortSignal.timeout(30_000),
  });
  const json = await resp.json();
  if (!json.success) {
    throw new Error(`${method} ${endpoint} failed: ${json.error_messages?.[0] ?? JSON.stringify(json)}`);
  }
  return json;
}

async function getRelayServers(host, auth) {
  const relayServers = [];
  let endpoint = "/relay_servers";
  let prevToken = null;

  for (;;) {
    const res = await gaRequest(host, auth, "GET", endpoint);
    relayServers.push(...res.data.relay_servers);

    const { next_page_token, num_records } = res.data.pagination ?? {};
    if (!next_page_token) break;
    if (next_page_token === prevToken) {
      log.warn("pagination token did not advance — stopping early with %d/%d records", relayServers.length, num_records);
      break;
    }
    if (relayServers.length >= num_records) break;

    prevToken = next_page_token;
    endpoint = `/relay_servers?page_token=${encodeURIComponent(next_page_token)}`;
  }

  return relayServers;
}

async function deleteRelayServer(host, auth, id) {
  await gaRequest(host, auth, "DELETE", `/relay_servers/${id}`);
}

// ============================================================
// SYSTEM RUN
// ============================================================

async function processSystem(systemName) {
  const system = SYSTEMS[systemName];
  const auth = authHeader(system.cred);

  log.info("=== %s: fetching relay servers ===", systemName);
  const relayServers = await getRelayServers(system.host, auth);

  const ignoreIds = IGNORE_IDS[systemName] ?? [];
  const toRemove = relayServers.filter(
    (rs) => rs.name.toLowerCase().includes(NAME_FILTER) && !ignoreIds.includes(rs.id)
  );

  if (!toRemove.length) {
    log.info("%s: no Sparkpost relay servers found", systemName);
    return;
  }

  console.log(toRemove)

  for (const rs of toRemove) {
    log.info("%s: deleting relay server id=%s name=%s", systemName, rs.id, rs.name);
    await deleteRelayServer(system.host, auth, rs.id);
  }
}

// ============================================================
// ENTRY POINT
// ============================================================

async function main() {
  try {
    for (const name of Object.keys(SYSTEMS)) {
      await processSystem(name);
    }
  } catch (err) {
    log.error("Failed: %s", err.message);
    process.exit(1);
  }
}

main();
