#!/usr/bin/env node
/**
 * Daily BE campaign stats from Pluto → Google Sheet
 * Usage: node be.js [YYYY-MM-DD]   (defaults to today)
 */

"use strict";

const path = require("path");
const { google } = require("googleapis");
const schedule = require("node-schedule");

process.loadEnvFile(path.join(__dirname, ".env"));

// ============================================================
// CONFIGURATION
// ============================================================

const GOOGLE_CLIENT_ID     = process.env.GOOGLE_CLIENT_ID;
const GOOGLE_CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET;
const GOOGLE_REFRESH_TOKEN = process.env.GOOGLE_REFRESH_TOKEN;

const PLUTO_API_BASE = "https://plutomailsystem.com/ga/api/v2";
const PLUTO_API_KEY = process.env.PLUTO_API_KEY_NL;

const SPREADSHEET_ID = "1dwZXWaQsFth-hIfRrt8jMnrqP3lc008pPdyi511d42s";
const SHEET_NAME = "NL July26";
const SHEET_START_DATE = "2026-07-01"; // Day 0 → columns G-N
const DATA_START_COL = 7;             // Column G (1-indexed)
const COLS_PER_DAY = 8;              // targeted, accepted, open, or, click, cr, bounce, br

function domainRow(domain_segment) {
  switch (domain_segment) {
    case "huizennieuws.nl_Active_6M_Apple":   return 3;

    case "pannenkoekenhis.nl_Click_6M_Apple":  return 5;
    case "pannenkoekenhis.nl_Active_1M_Microsoft":  return 23;

    case "koeienweide.nl_Active_1M_Apple":   return 6;
    case "koeienweide.nl_Inactive_Apple":   return 7;
    case "koeienweide.nl_Active_6M_Ziggo":   return 11;
    case "koeienweide.nl_Active_1M_Yahoo":   return 17;
    case "koeienweide.nl_Active_1M_Microsoft":   return 24;

    case "bloemenggeur.nl_Active_6M_Ziggo":   return 9;
    case "bloemenggeur.nl_Ziggo_exclude_6M":   return 10;

    case "tulpenveeld.nl_Active_6M_Ziggo":   return 13;
    case "tulpenveeld.nl_Ziggo_exclude_6M":   return 14;
    case "tulpenveeld.nl_Active_1M_Yahoo":   return 20;
    case "tulpenveeld.nl_Yahoo_exclude_6M":   return 21;
    case "tulpenveeld.nl_Active_1M_Microsoft":   return 25;

    case "mijnwooninfo.nl_Active_1M_Yahoo":   return 15;
    case "winactieonline.nl_Active_6M_Yahoo":   return 22;
    case "flappyvogelverzenden.com_Active_1M_Microsoft":   return 26;

    default: return null;
  }
}

const DOMAINS = [
  { 
    name: "huizennieuws.nl",
    list_id: 745,
    segments: ["Active_6M_Apple"]
  },
  { 
    name: "pannenkoekenhis.nl",
    list_id: 745,
    segments: ["Click_6M_Apple", "Active_1M_Microsoft"]
  },
  { 
    name: "koeienweide.nl",
    list_id: 745,
    segments: ["Active_1M_Apple", "Inactive_Apple", "Active_6M_Ziggo", "Active_1M_Yahoo", 'Active_1M_Microsoft']
  },
  { 
    name: "bloemenggeur.nl",
    list_id: 745,
    segments: ["Active_6M_Ziggo", 'Ziggo_exclude_6M']
  },
  { 
    name: "tulpenveeld.nl",
    list_id: 745,
    segments: ["Active_6M_Ziggo", 'Ziggo_exclude_6M', 'Active_1M_Yahoo', 'Yahoo_exclude_6M', 'Active_1M_Microsoft']
  },
  { 
    name: "mijnwooninfo.nl",
    list_id: 745,
    segments: ["Active_1M_Yahoo"]
  },
  {
    name: "winactieonline.nl",
    list_id: 745,
    segments: ["Active_6M_Yahoo"]
  },
  { 
    name: "flappyvogelverzenden.com",
    list_id: 745,
    segments: ["Active_1M_Microsoft"]
  }
];

// ============================================================
// LOGGING
// ============================================================

function ts() {
  return new Date().toISOString().replace("T", " ").slice(0, 19);
}

const log = {
  info:  (msg, ...a) => console.log(`${ts()}  INFO   ${fmt(msg, a)}`),
  warn:  (msg, ...a) => console.warn(`${ts()}  WARN   ${fmt(msg, a)}`),
  error: (msg, ...a) => console.error(`${ts()}  ERROR  ${fmt(msg, a)}`),
};

function fmt(msg, args) {
  if (!args.length) return msg;
  return msg.replace(/%[-\d]*[sdif%]/g, () => String(args.shift() ?? ""));
}

// ============================================================
// HELPERS
// ============================================================

async function getJson(url) {
  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${PLUTO_API_KEY}` },
    signal: AbortSignal.timeout(30_000),
  });
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`HTTP ${resp.status} ${resp.statusText} — ${url}\n${body}`);
  }
  return resp.json();
}

// 1-based column number → letter(s), e.g. 7 → "G", 27 → "AA"
function colLetter(n) {
  let result = "";
  while (n > 0) {
    n--;
    result = String.fromCharCode(65 + (n % 26)) + result;
    n = Math.floor(n / 26);
  }
  return result;
}

function dayOffset(dateStr) {
  const start = new Date(SHEET_START_DATE + "T00:00:00Z");
  const target = new Date(dateStr + "T00:00:00Z");
  return Math.round((target - start) / 86_400_000);
}

// ============================================================
// PLUTO API
// ============================================================

async function fetchCampaigns(listId, fromDate, toDate) {
  const url =
    `${PLUTO_API_BASE}/mailing_lists/${listId}/campaigns` +
    `?started_at__start=${fromDate}&started_at__end=${toDate}`;
  const body = await getJson(url);
  if (!body.success) throw new Error(`Campaigns API error: ${JSON.stringify(body)}`);
  return body.data; // array of campaign objects
}

async function fetchCampaignStats(campaignId) {
  const body = await getJson(`${PLUTO_API_BASE}/campaigns/${campaignId}`);
  if (!body.success) throw new Error(`Stats API error for campaign ${campaignId}: ${JSON.stringify(body)}`);
  return body.data?.stat_summary ?? {};
}

function aggregateStats(statsList) {
  return statsList.reduce(
    (acc, s) => ({
      targeted:  acc.targeted  + (s.messages_sent  || 0),
      accepted:  acc.accepted  + (s.accepted        || 0),
      open:      acc.open      + (s.opens_total     || 0),
      click:     acc.click     + (s.clicks_total    || 0),
      bounce:    acc.bounce    + (s.bounces_total   || 0),
    }),
    { targeted: 0, accepted: 0, open: 0, click: 0, bounce: 0 }
  );
}

function statsToRow(s) {
  return {
    targeted: s.targeted,
    accepted: s.accepted,
    open:     s.open,
    or:       s.targeted ? parseFloat((s.open / s.targeted).toFixed(4)) : 0,
    click:    s.click,
    cr:       s.accepted ? parseFloat((s.click  / s.accepted).toFixed(4)) : 0,
    bounce:   s.bounce,
    br:       s.targeted ? parseFloat((s.bounce / s.targeted).toFixed(4)) : 0,
  };
}

function rowToArray(r) {
  return [r.targeted, r.accepted, r.open, r.or, r.click, r.cr, r.bounce, r.br];
}

// ============================================================
// COLLECT STATS
// ============================================================

async function collectStats(fromDate, toDate) {
  const rows = []; // { domain: 'domain_segment', report: { targeted, accepted, open, or, click, cr, bounce, br } }

  for (const domain of DOMAINS) {
    log.info("Domain %s  (list_id=%d)", domain.name, domain.list_id);

    let campaigns;
    try {
      campaigns = await fetchCampaigns(domain.list_id, fromDate, toDate);
    } catch (err) {
      log.error("Cannot fetch campaigns for %s: %s", domain.name, err.message);
      for (const seg of domain.segments) {
        rows.push({ domain: `${domain.name}_${seg}`, report: statsToRow({ targeted: 0, accepted: 0, open: 0, click: 0, bounce: 0 }) });
      }
      continue;
    }

    // Campaigns that belong to this domain
    const domainCampaigns = campaigns.filter(c => c.name.includes(domain.name));
    log.info("  %d/%d campaigns match domain name", domainCampaigns.length, campaigns.length);

    for (const segment of domain.segments) {
      const segCampaigns = domainCampaigns.filter(c => c.name.includes(segment));

      if (!segCampaigns.length) {
        log.warn("  No campaigns for %s / %s", domain.name, segment);
        rows.push({ domain: `${domain.name}_${segment}`, report: statsToRow({ targeted: 0, accepted: 0, open: 0, click: 0, bounce: 0 }) });
        continue;
      }

      // Fetch stats for each campaign in parallel
      const statsList = (
        await Promise.all(
          segCampaigns.map(c =>
            fetchCampaignStats(c.id).catch(err => {
              log.error("  Campaign %d: %s", c.id, err.message);
              return null;
            })
          )
        )
      ).filter(Boolean);

      const agg = aggregateStats(statsList);
      const domain_segment = `${domain.name}_${segment}`;
      rows.push({ domain: domain_segment, report: statsToRow(agg) });
      log.info(
        "  %-40s  targeted=%d  accepted=%d  open=%d  click=%d  bounce=%d",
        domain_segment, agg.targeted, agg.accepted, agg.open, agg.click, agg.bounce
      );
    }
  }

  return rows;
}

// ============================================================
// GOOGLE SHEETS
// ============================================================

async function writeToSheet(date, rows) {
  const oAuth2 = new google.auth.OAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET);
  oAuth2.setCredentials({ refresh_token: GOOGLE_REFRESH_TOKEN });
  const sheets = google.sheets({ version: "v4", auth: oAuth2 });

  const offset = dayOffset(date);
  if (offset < 0) {
    throw new Error(`Date ${date} is before sheet start date ${SHEET_START_DATE}`);
  }

  const startCol = DATA_START_COL + offset * COLS_PER_DAY; // 1-based

  // Resolve sheet ID from name so we can use updateCells (value-only, no format touch)
  const meta = await sheets.spreadsheets.get({ spreadsheetId: SPREADSHEET_ID });
  const sheetMeta = meta.data.sheets.find(s => s.properties.title === SHEET_NAME);
  if (!sheetMeta) throw new Error(`Sheet "${SHEET_NAME}" not found`);
  const sheetId = sheetMeta.properties.sheetId;

  const requests = [];
  for (const row of rows) {
    const rowNum = domainRow(row.domain);
    if (rowNum === null) {
      log.warn("No row mapping for %s — skipped", row.domain);
      continue;
    }
    requests.push({
      updateCells: {
        rows: [{ values: rowToArray(row.report).map(v => ({ userEnteredValue: { numberValue: v } })) }],
        fields: "userEnteredValue", // only write value, never touch formatting
        start: { sheetId, rowIndex: rowNum - 1, columnIndex: startCol - 1 },
      },
    });
    log.info("  %s → row %d", row.domain, rowNum);
  }

  if (!requests.length) {
    log.warn("Nothing mapped to write.");
    return;
  }

  log.info("Writing %d rows to sheet  (day offset=%d)", requests.length, offset);

  await sheets.spreadsheets.batchUpdate({
    spreadsheetId: SPREADSHEET_ID,
    requestBody: { requests },
  });

  log.info("Sheet updated: %d rows written", requests.length);
}

// ============================================================
// ENTRY POINT
// ============================================================

async function main() {
  const fromDate = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  const toDate   = new Date().toISOString().slice(0, 10);
  
  log.info("=== BE Daily Report  date=%s ===", fromDate);

  if (!DOMAINS.length) {
    log.warn("DOMAINS list is empty — populate the DOMAINS array in the config section.");
    return;
  }

  const rows = await collectStats(fromDate, toDate);
  log.info("Collected %d segment rows", rows.length);

  if (!rows.length) {
    log.warn("Nothing to write.");
    return;
  }

  await writeToSheet(fromDate, rows);
  log.info("=== Done ===");
}

// Run once immediately if a date arg is passed, otherwise schedule at 09:30 daily
if (process.argv.slice(2).find(a => /^\d{4}-\d{2}-\d{2}$/.test(a))) {
  main().catch(err => { log.error(err.message); process.exit(1); });
} else {
  log.info("Scheduler started — will run daily at 09:28");
  schedule.scheduleJob("28 9 * * *", () => {
    main().catch(err => log.error(err.message));
  });
}
