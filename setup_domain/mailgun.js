"use strict";

const fs = require("fs");
const path = require("path");

// ============================================================
// CONFIGURATION
// ============================================================

const { pluto_cred, charon_cred } = JSON.parse(
  fs.readFileSync(path.join(__dirname, "ga", "credentials.json"), "utf8")
);
process.loadEnvFile(path.join(__dirname, "ga", ".env"));

const SYSTEMS = {
  pluto: {
    host: "plutomailsystem",
    cred: pluto_cred,
    mailIp: "193.107.76.1",
    clickIp: "193.107.76.2",
    relaySourceIp: "193.107.76.1",
    relaySourceHostname: "smtp1-0.pluto-relay.de",
  },
  charon: {
    host: "charonmail",
    cred: charon_cred,
    mailIp: "45.81.231.1",
    clickIp: "45.81.231.2",
    relaySourceIp: "45.81.231.2",
    relaySourceHostname: "smtp9-1.charonmail.com",
  },
};

// Set by configureSystem() once the sending_system argument is known.
let BASE_URL;
let GA_AUTH;
let CLICK_IP;
let MAIL_IP;
let RELAY_SOURCE_IP;
let RELAY_SOURCE_HOSTNAME;
let SENDING_SYSTEM_LABEL;

function configureSystem(sendingSystem) {
  const system = SYSTEMS[sendingSystem];
  if (!system) {
    throw new Error(`Unknown sending_system "${sendingSystem}" — expected "Pluto" or "Charon"`);
  }
  const [user, pass] = system.cred;
  BASE_URL = `https://${system.host}.com/ga/api/v3/eng`;
  GA_AUTH = "Basic " + Buffer.from(`${user}:${pass}`).toString("base64");
  CLICK_IP = system.clickIp;
  MAIL_IP = system.mailIp;
  RELAY_SOURCE_IP = system.relaySourceIp;
  RELAY_SOURCE_HOSTNAME = system.relaySourceHostname;
  SENDING_SYSTEM_LABEL = sendingSystem === 'pluto' ? 'GreeenArrow' : 'Charon';
}

const CLOUDFLARE_URL = "https://api.cloudflare.com/client/v4";
const CLOUDFLARE_TOKEN = process.env.CLOUDFLARE_TOKEN;

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

async function createMailgunRelay(domain, username, password) {
  const relayName = `${SENDING_SYSTEM_LABEL}_Mailgun_mg.${domain}`;
  log.info("Adding relay server %s...", relayName);
  await plutoRequest("POST", "/relay_servers", {
    relay_server: {
      name: relayName,
      source_ip: { ip: RELAY_SOURCE_IP, hostname: RELAY_SOURCE_HOSTNAME },
      destination: {
        hostname: "smtp.mailgun.org",
        port: 587,
        username,
        password,
      },
      throttle_limits: { max_concurrent_connections: 10, max_messages_per_hour: 500000 },
    },
  });
  log.info("  Relay server created: %s", relayName);
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

function createDnsRecord(zoneId, record) {
  return cloudflareRequest("POST", `/zones/${zoneId}/dns_records`, record);
}

// ============================================================
// SET UP
// ============================================================

async function setUpDomain(domain, zoneId, mailgunUsername, mailgunPassword) {
  log.info("=== Mailgun domain setup: %s ===", domain);

  // const domainId = await createIncomingDomain(domain);
  // await createForwardMailboxes(domainId);
  // await createSpamMailboxes(domainId);
  // await createBounceMailbox(domainId);

  // const clickSubDomain = `click.${domain}`;
  // await createClickUrl(clickSubDomain);

  // log.info("Adding click record...");
  // await createDnsRecord(zoneId, { name: clickSubDomain, type: "A", content: CLICK_IP });

  // log.info("Adding default records (mail, dmarc, mx)...");
  // await createDnsRecord(zoneId, { name: `mail.${domain}`, type: "A", content: MAIL_IP });
  // await createDnsRecord(zoneId, { name: domain, type: "MX", content: `mail.${domain}`, priority: 10 });

  await createMailgunRelay(domain, mailgunUsername, mailgunPassword);

  log.info("=== Done: %s is set up in Pluto ===", domain);
}

// ============================================================
// ENTRY POINT
// ============================================================

async function main() {
  const domain = 'zustellzugang.de';
  const sendingSystem = 'pluto';
  const zoneId = '87a0e7f6a2381a1a9542a455988b18a0';
  const mailgunUsername = 'as@mg.zustellzugang.de';
  const mailgunPassword = '505315bfa65c669506a45b2a95ffeb39-994959c8-69d6194f';

  try {
    configureSystem(sendingSystem);
    await setUpDomain(domain, zoneId, mailgunUsername, mailgunPassword);
  } catch (err) {
    log.error("%s setup failed: %s", domain, err.message);
    process.exit(1);
  }
}

main();
