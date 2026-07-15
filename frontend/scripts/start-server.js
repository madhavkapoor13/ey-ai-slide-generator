#!/usr/bin/env node
/**
 * frontend/scripts/start-server.js
 * ==================================
 * Lightweight HTTPS static file server for the Office.js add-in task pane.
 *
 * Replaces the `http-server` dependency, which hangs on Node.js 25 because
 * of a compatibility issue in its startup code. This script uses only Node
 * built-in modules so it works across Node versions.
 */

const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");
const url = require("url");

const ROOT = path.resolve(__dirname, "..");
const PORT = parseInt(process.env.PORT || "3000", 10);
const HOST = process.env.HOST || "::";
const USE_HTTP = process.env.USE_HTTP === "true";

const CERT_DIR = path.join(process.env.HOME, ".office-addin-dev-certs");
const KEY_FILE = path.join(CERT_DIR, "localhost.key");
const CERT_FILE = path.join(CERT_DIR, "localhost.crt");

const MIME_TYPES = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".xml": "application/xml",
};

function log(method, statusCode, requestPath) {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] ${method} ${statusCode} ${requestPath}`);
}

function serveFile(filePath, res) {
  fs.readFile(filePath, (err, data) => {
    if (err) {
      log("GET", 500, filePath);
      res.writeHead(500, { "Content-Type": "text/plain" });
      res.end(`Server error: ${err.message}`);
      return;
    }

    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || "application/octet-stream";
    log("GET", 200, filePath);
    res.writeHead(200, {
      "Content-Type": contentType,
      "Cache-Control": "no-cache",
      "Access-Control-Allow-Origin": "*",
    });
    res.end(data);
  });
}

function requestListener(req, res) {
  const parsedUrl = url.parse(req.url, true);
  let requestPath = decodeURIComponent(parsedUrl.pathname);

  // Strip query-string cache-busters from the physical path.
  requestPath = requestPath.split("?")[0];

  // Security: prevent directory traversal.
  const safePath = path.normalize(requestPath).replace(/^(\.\.[\/\\])+/, "");
  let filePath = path.join(ROOT, safePath);

  // Default to index.html for directory requests.
  if (fs.existsSync(filePath) && fs.statSync(filePath).isDirectory()) {
    filePath = path.join(filePath, "index.html");
  }

  if (!fs.existsSync(filePath)) {
    log(req.method, 404, filePath);
    res.writeHead(404, { "Content-Type": "text/plain" });
    res.end("Not found");
    return;
  }

  serveFile(filePath, res);
}

function start() {
  let server;

  if (USE_HTTP) {
    server = http.createServer(requestListener);
    console.log(`EY AI Pitch add-in server running on http://${HOST}:${PORT}`);
  } else {
    if (!fs.existsSync(KEY_FILE) || !fs.existsSync(CERT_FILE)) {
      console.error(`Dev certificates not found at ${CERT_DIR}.`);
      console.error("Run: cd frontend && npx office-addin-dev-certs install");
      process.exit(1);
    }

    const options = {
      key: fs.readFileSync(KEY_FILE),
      cert: fs.readFileSync(CERT_FILE),
    };
    server = https.createServer(options, requestListener);
    console.log(`EY AI Pitch add-in server running on https://${HOST}:${PORT}`);
  }

  console.log(`Serving files from ${ROOT}`);

  server.listen(PORT, HOST, () => {
    const address = server.address();
    console.log(`Listening on ${address.address}:${address.port}`);
  });

  server.on("error", (err) => {
    console.error("Server error:", err);
    process.exit(1);
  });
}

start();
