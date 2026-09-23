"use strict";

const path = require("path");
const { parseArgs } = require("node:util");

// ============================================================
// CONFIGURATION
// ============================================================

process.loadEnvFile(path.join(__dirname, "ga", ".env"));

const SYSTEMS = {
  pluto: {
    host: "plutomailsystem",
    envPrefix: "PLUTO",
    mailIp: "193.107.76.1",
    clickIp: "193.107.76.2",
  },
  charon: {
    host: "charonmail",
    envPrefix: "CHARON",
    mailIp: "45.81.231.1",
    clickIp: "45.81.231.2",
  },
};

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is missing from ga/.env`);
  }
  return value;
}

// Set by configureSystem() once the sending_system argument is known.
let BASE_URL;
let GA_AUTH;
let CLICK_IP;
let MAIL_IP;

function configureSystem(sendingSystem) {
  const system = SYSTEMS[sendingSystem];
  if (!system) {
    throw new Error(`Unknown --system "${sendingSystem}" — expected ${Object.keys(SYSTEMS).join(" or ")}`);
  }
  const user = requireEnv(`${system.envPrefix}_USERNAME`);
  const pass = requireEnv(`${system.envPrefix}_PASSWORD`);
  BASE_URL = `https://${system.host}.com/ga/api/v3/eng`;
  GA_AUTH = "Basic " + Buffer.from(`${user}:${pass}`).toString("base64");
  CLICK_IP = system.clickIp;
  MAIL_IP = system.mailIp;
}

const CLOUDFLARE_URL = "https://api.cloudflare.com/client/v4";
const CLOUDFLARE_TOKEN = requireEnv("CLOUDFLARE_TOKEN");

const FORWARD_MAILBOXES = [
  { local: "dmarc_reports", forward_to: "dmarc_reports@audienceserv.com" },
  { local: "feedbackloop", forward_to: "feedbackloop@audienceserv.com" },
  { local: "postmaster",   forward_to: "feedbackloop@audienceserv.com" },
  { local: "reply",        forward_to: "kontakt@buncha.org" },
];
const SPAM_MAILBOXES = ["abuse", "feedback"];

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
// PLUTO ENGINE API
// ============================================================

async function plutoRequest(method, endpoint, body) {
  const resp = await fetch(`${BASE_URL}${endpoint}`, {
    method,
    headers: { Authorization: GA_AUTH, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(30_000),
  });
  const json = await resp.json();
  if (!json.success) {
    throw new Error(`Pluto ${method} ${endpoint} failed: ${json.error_messages?.[0] ?? JSON.stringify(json)}`);
  }
  return json;
}

async function createIncomingDomain(domain) {
  log.info("Adding %s as an incoming domain in Pluto...", domain);
  const res = await plutoRequest("POST", "/incoming_email_domains", {
    domain: { domain, email_status: "normal" },
  });
  const domainId = String(res.data.domain.id);
  log.info("  domain_id=%s", domainId);
  return domainId;
}

async function createBounceMailbox(domainId) {
  await plutoRequest("POST", `/incoming_email_domains/${domainId}/bounce_mailboxes`, {
    mailbox: { localpart: "return" },
  });
  log.info("  Bounce mailbox created");
}

async function createSpamMailboxes(domainId) {
  for (const local of SPAM_MAILBOXES) {
    await plutoRequest("POST", `/incoming_email_domains/${domainId}/spam_complaint_mailboxes`, {
      mailbox: { localpart: local },
    });
    log.info("  Spam mailbox created: %s", local);
  }
}

async function createForwardMailboxes(domainId) {
  for (const box of FORWARD_MAILBOXES) {
    await plutoRequest("POST", `/incoming_email_domains/${domainId}/forwarding_mailboxes`, {
      mailbox: { localpart: box.local, forward_to: [box.forward_to], is_wildcard: false },
    });
    log.info("  Forward mailbox created: %s -> %s", box.local, box.forward_to);
  }
}

async function createClickUrl(clickSubDomain) {
  const res = await plutoRequest("POST", "/url_domains", {
    url_domain: { domain: clickSubDomain, ssl: true },
  });
  log.info("  Click URL created for %s", clickSubDomain);
  return String(res.data.url_domain.id);
}

// ============================================================
// CLOUDFLARE
// ============================================================

async function cloudflareRequest(method, endpoint, body) {
  const resp = await fetch(`${CLOUDFLARE_URL}${endpoint}`, {
    method,
    headers: { Authorization: `Bearer ${CLOUDFLARE_TOKEN}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(30_000),
  });
  const json = await resp.json();
  if (!json.success) {
    throw new Error(`Cloudflare ${method} ${endpoint} failed: ${JSON.stringify(json.errors)}`);
  }
  return json.result;
}

async function getZoneId(domain) {
  const zones = await cloudflareRequest("GET", `/zones?name=${encodeURIComponent(domain)}`);
  if (!zones.length) {
    throw new Error(`No Cloudflare zone found for ${domain} — add the domain to Cloudflare first`);
  }
  return zones[0].id;
}

function createDnsRecord(zoneId, record) {
  return cloudflareRequest("POST", `/zones/${zoneId}/dns_records`, record);
}

// ============================================================
// SET UP
// ============================================================

function dmarcRecord(domain) {
  return `"v=DMARC1\\; p=none\\; pct=100\\; rua=mailto:dmarc-reports@${domain}\\;"`;
}

async function setUpDomain(domain, subDomain, zoneId) {
  log.info("=== Infobip domain setup: %s ===", domain);

  const domainId = await createIncomingDomain(domain);
  await createForwardMailboxes(domainId);
  await createSpamMailboxes(domainId);

  const subDomainId = await createIncomingDomain(subDomain);
  await createForwardMailboxes(subDomainId);
  await createBounceMailbox(subDomainId);

  const clickSubDomain = `click.${domain}`;
  await createClickUrl(clickSubDomain);

  log.info("Adding click record...");
  await createDnsRecord(zoneId, { name: clickSubDomain, type: "A", content: CLICK_IP });

  log.info("Adding default records (mail, dmarc, mx)...");
  await createDnsRecord(zoneId, { name: `mail.${domain}`, type: "A", content: MAIL_IP });
  await createDnsRecord(zoneId, { name: domain, type: "MX", content: `mail.${domain}`, priority: 10 });
  await createDnsRecord(zoneId, { name: subDomain, type: "MX", content: `mail.${domain}`, priority: 10 });

  log.info("=== Done: %s is set up in Pluto ===", domain);
}

// ============================================================
// ENTRY POINT
// ============================================================

const USAGE = `Usage: node infobip.js --domain <domain> [options]

  --domain      <domain>   sending domain, e.g. example.com       (required)
  --system      <name>     ${Object.keys(SYSTEMS).join(" | ")}    (default: charon)
  --sub-domain  <domain>   default: email.<domain>
  --zone-id     <id>       Cloudflare zone id; looked up from --domain when omitted
  --help                   show this message`;

function parseCliArgs() {
  const { values } = parseArgs({
    options: {
      domain: { type: "string" },
      system: { type: "string", default: "charon" },
      "sub-domain": { type: "string" },
      "zone-id": { type: "string" },
      help: { type: "boolean", default: false },
    },
  });

  if (values.help) {
    console.log(USAGE);
    process.exit(0);
  }
  if (!values.domain) {
    console.error("error: --domain is required\n\n" + USAGE);
    process.exit(1);
  }

  const system = values.system.toLowerCase();
  if (!SYSTEMS[system]) {
    console.error(`error: unknown --system "${values.system}" — expected ${Object.keys(SYSTEMS).join(" or ")}`);
    process.exit(1);
  }

  return {
    domain: values.domain,
    system,
    subDomain: values["sub-domain"] ?? `email.${values.domain}`,
    zoneId: values["zone-id"],
  };
}

async function main() {
  const { domain, system, subDomain, zoneId } = parseCliArgs();

  try {
    configureSystem(system);
    // Looking the zone up beats passing it by hand: the Cloudflare account id
    // is the same shape and gets mistaken for it.
    const zone = zoneId ?? (await getZoneId(domain));
    log.info("Using Cloudflare zone %s for %s", zone, domain);
    await setUpDomain(domain, subDomain, zone);
  } catch (err) {
    log.error("%s setup failed: %s", domain, err.message);
    process.exit(1);
  }
}

main();
