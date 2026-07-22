#!/usr/bin/env node
"use strict";

const { google } = require("googleapis");
const http = require("http");
const path = require("path");

process.loadEnvFile(path.join(__dirname, ".env"));

const CLIENT_ID     = process.env.GOOGLE_CLIENT_ID;
const CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET;
const REDIRECT_URI  = "http://localhost:3000";

const oAuth2 = new google.auth.OAuth2(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI);

const authUrl = oAuth2.generateAuthUrl({
  access_type: "offline",
  prompt: "consent",
  scope: ["https://www.googleapis.com/auth/spreadsheets"],
});

console.log("\nOpen this URL in your browser:\n");
console.log(authUrl);
console.log("\nWaiting for Google to redirect back...\n");

const server = http.createServer(async (req, res) => {
  const code = new URL(req.url, REDIRECT_URI).searchParams.get("code");
  if (!code) {
    res.end("No code found.");
    return;
  }

  res.end("<h2>Done! You can close this tab and check the terminal.</h2>");
  server.close();

  try {
    const { tokens } = await oAuth2.getToken(code);
    console.log("Success! Add this to daily_report/.env:\n");
    console.log(`GOOGLE_REFRESH_TOKEN=${tokens.refresh_token}`);
  } catch (err) {
    console.error("Error exchanging code:", err.message);
  }
});

server.listen(3000);
