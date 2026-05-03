#!/usr/bin/env node
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = Number(process.env.OCR_BACKEND_PORT || 8787);
const OCR_SPACE_URL = "https://api.ocr.space/parse/image";
function getApiKey() {
  return process.env.OCR_SPACE_API_KEY || "";
}

function sendJson(res, status, payload) {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Cache-Control": "no-store"
  });
  res.end(body);
}

function sendText(res, status, contentType, body) {
  res.writeHead(status, {
    "Content-Type": contentType,
    "Cache-Control": "no-store"
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function parseMultipart(body, contentType) {
  const boundaryMatch = /boundary=(?:"([^"]+)"|([^;]+))/i.exec(contentType || "");
  if (!boundaryMatch) throw new Error("Missing multipart boundary");
  const boundary = Buffer.from(`--${boundaryMatch[1] || boundaryMatch[2]}`);
  const parts = [];
  let offset = 0;

  while (offset < body.length) {
    const start = body.indexOf(boundary, offset);
    if (start < 0) break;
    const next = body.indexOf(boundary, start + boundary.length);
    if (next < 0) break;
    let part = body.slice(start + boundary.length, next);
    if (part.slice(0, 2).toString() === "\r\n") part = part.slice(2);
    if (part.slice(-2).toString() === "\r\n") part = part.slice(0, -2);
    const headerEnd = part.indexOf(Buffer.from("\r\n\r\n"));
    if (headerEnd >= 0) {
      const rawHeaders = part.slice(0, headerEnd).toString("utf8");
      const data = part.slice(headerEnd + 4);
      const name = /name="([^"]+)"/i.exec(rawHeaders)?.[1] || "";
      const filename = /filename="([^"]*)"/i.exec(rawHeaders)?.[1] || "";
      const type = /content-type:\s*([^\r\n]+)/i.exec(rawHeaders)?.[1]?.trim() || "application/octet-stream";
      parts.push({ name, filename, type, data });
    }
    offset = next;
  }

  return parts;
}

function parseDataUrl(value) {
  const match = /^data:([^;,]+)?;base64,(.+)$/i.exec(String(value || ""));
  if (!match) return null;
  return {
    type: match[1] || "image/png",
    data: Buffer.from(match[2], "base64")
  };
}

async function getIncomingImage(req, body) {
  const contentType = req.headers["content-type"] || "";

  if (contentType.includes("application/json")) {
    console.log(`received JSON body length ${body.length}`);
    const json = JSON.parse(body.toString("utf8") || "{}");
    const parsed = parseDataUrl(json.image || json.imageBase64 || json.dataUrl);
    if (parsed) return { filename: "upload.png", type: parsed.type, data: parsed.data, language: json.language, ocrEngine: json.ocrEngine };
    if (json.base64) {
      return {
        filename: json.filename || "upload.png",
        type: json.contentType || "image/png",
        data: Buffer.from(String(json.base64), "base64"),
        language: json.language,
        ocrEngine: json.ocrEngine
      };
    }
  }

  if (contentType.includes("multipart/form-data")) {
    const parts = parseMultipart(body, contentType);
    const file = parts.find((part) => part.filename || part.name === "image" || part.name === "file");
    if (file?.data?.length) {
      return {
        filename: file.filename || "upload.png",
        type: file.type || "image/png",
        data: file.data
      };
    }
  }

  throw new Error("Expected multipart image file or JSON base64 image");
}

function normalizeNumber(value) {
  const cleaned = String(value || "").replace(/\s+/g, "").replace(/,/g, "");
  const match = cleaned.match(/\d+/);
  return match ? parseInt(match[0], 10) : null;
}

function normalizeNick(value) {
  return String(value || "")
    .replace(/[^\p{L}0-9_\-\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function cleanNick(value) {
  return normalizeNick(value);
}

function parseStatsTextLegacyUnused(text) {
  const rows = String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  const parsed = [];
  const headerPattern = /член\s+группы|member|kills|deaths|pvp|pve/i;

  for (const row of rows) {
    if (headerPattern.test(row)) continue;
    const tokens = row.split(/\s+/).filter(Boolean);
    const numberIndexes = [];
    tokens.forEach((token, index) => {
      if (/\d/.test(token)) numberIndexes.push(index);
    });

    if (numberIndexes.length < 4) {
      parsed.push({ source: row, nick: cleanNick(row), kills: null, deaths: null, pvp: null, pve: null, parse_error: "less_than_4_numbers" });
      continue;
    }

    const firstNumber = numberIndexes[0];
    const nick = cleanNick(tokens.slice(0, firstNumber).join(" "));
    const nums = numberIndexes.slice(0, 4).map((index) => normalizeNumber(tokens[index]));
    parsed.push({
      source: row,
      nick,
      kills: nums[0],
      deaths: nums[1],
      pvp: nums[2],
      pve: nums[3],
      parse_error: nick && nums.every((num) => num != null) ? null : "incomplete_row"
    });
  }

  return { rows, parsed };
}

function isHeaderOrNoise(line) {
  const value = String(line || "").trim();
  if (!value) return true;
  if (/^\W+$/.test(value)) return true;
  if (/^(?:[|/\\_.\-:;()[\]{}]+|\d?[|/\\_.\-:;()[\]{}]+)$/u.test(value)) return true;
  return /(?:\u0427\u043b\u0435\u043d\s+\u0433\u0440\u0443\u043f\u043f\u044b|\u0413\u0440\u0443\u043f\u043f\u044b|\u0443\u0440\u043e\u043d|PvP|PvE|kills|deaths|member)/iu.test(value);
}

function tokenizeLine(line) {
  return String(line || "")
    .trim()
    .split(/\s+/)
    .map((token) => token.replace(/^[^\p{L}\d,]+|[^\p{L}\d,]+$/gu, ""))
    .filter(Boolean);
}

function isNumericToken(token) {
  return /^[\d,\s]+$/.test(String(token || ""));
}

function parseRepairedLine(line, repairedFrom = null) {
  const tokens = tokenizeLine(line);
  const numeric = [];
  tokens.forEach((token, index) => {
    if (isNumericToken(token)) numeric.push({ token, index, value: normalizeNumber(token) });
  });

  let stats = numeric.slice(-4);
  let parseStatus = "ok";
  let parseError = null;
  let inferredTrailingZero = false;

  if (numeric.length === 3) {
    parseStatus = "parse_error_missing_number";
    parseError = "provider_missed_number";
  } else if (numeric.length < 4) {
    parseStatus = "parse_error";
    parseError = "less_than_4_numbers";
  }

  const firstStatIndex = stats.length >= 4 ? stats[0].index : (numeric[0]?.index ?? tokens.length);
  let rawNickTokens = tokens.slice(0, firstStatIndex);

  if (rawNickTokens.length === 1 && isNumericToken(rawNickTokens[0]) && stats.length >= 4) {
    rawNickTokens = [];
    parseStatus = "artifact_removed";
  }

  const rawNick = rawNickTokens.join(" ").trim();
  const normalizedNick = normalizeNick(rawNick);
  if (!normalizedNick && stats.length >= 4) {
    parseStatus = "parse_error";
    parseError = "missing_nick";
  }

  return {
    source: line,
    rawLine: line,
    repairedFrom,
    rawNick,
    normalizedNick,
    nick: normalizedNick,
    numbersFound: numeric.map((item) => item.value).filter((value) => value != null),
    kills: stats[0]?.value ?? null,
    deaths: stats[1]?.value ?? null,
    pvp: stats[2]?.value ?? null,
    pve: stats[3]?.value ?? null,
    parseStatus,
    parse_error: parseError,
    inferredTrailingZero
  };
}

function parseStatsText(text) {
  const rawLines = String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const rows = rawLines.filter((line) => !isHeaderOrNoise(line));
  const repairedRows = [];

  for (const row of rows) {
    const tokens = tokenizeLine(row);
    const numericCount = tokens.filter(isNumericToken).length;
    const lettersCount = tokens.filter((token) => /\p{L}/u.test(token)).length;
    const previous = repairedRows[repairedRows.length - 1];

    if (previous && lettersCount === 0 && numericCount > 0) {
      const previousNumericCount = tokenizeLine(previous.value).filter(isNumericToken).length;
      if (previousNumericCount < 4) {
        previous.value = `${previous.value} ${row}`;
        previous.repairedFrom.push(row);
        continue;
      }
    }

    if (previous && lettersCount > 0 && numericCount > 0) {
      const parsedPrevious = parseRepairedLine(previous.value, previous.repairedFrom);
      if (parsedPrevious.parse_error && parsedPrevious.numbersFound.length === 0) {
        previous.value = `${previous.value} ${row}`;
        previous.repairedFrom.push(row);
        continue;
      }
    }

    repairedRows.push({ value: row, repairedFrom: [] });
  }

  const parsed = repairedRows
    .map((row) => parseRepairedLine(row.value, row.repairedFrom.length ? row.repairedFrom : null))
    .filter((row) => row.normalizedNick || row.numbersFound.length > 0);

  return { rows, parsed, rawLines };
}

async function callOcrSpace(image) {
  const apiKey = getApiKey();
  if (!apiKey) {
    return {
      ok: false,
      providerStatus: null,
      providerRaw: null,
      parsedText: "",
      text: "",
      rows: [],
      rawLines: [],
      parsed: [],
      error: "OCR_SPACE_API_KEY missing"
    };
  }

  const engine = String(image.ocrEngine || "2").replace(/[^\d]/g, "") || "2";
  const form = new FormData();
  form.append("file", new Blob([image.data], { type: image.type }), image.filename);
  form.append("OCREngine", engine);
  form.append("scale", "true");
  form.append("isTable", "true");
  form.append("isOverlayRequired", "true");
  form.append("detectOrientation", "false");
  form.append("language", image.language === "eng" ? "eng" : "rus");

  console.log("OCR.space request started");
  const response = await fetch(OCR_SPACE_URL, {
    method: "POST",
    headers: { apikey: apiKey },
    body: form
  });
  console.log(`OCR.space response status ${response.status}`);
  const responseText = await response.text();
  console.log(`OCR.space raw response length ${Buffer.byteLength(responseText)}`);
  let json;
  try {
    json = JSON.parse(responseText);
  } catch {
    return {
      ok: false,
      providerStatus: response.status,
      providerRaw: responseText,
      parsedText: "",
      text: "",
      rows: [],
      rawLines: [],
      parsed: [],
      error: `OCR.space returned non-JSON status=${response.status}`
    };
  }

  if (!response.ok || json.IsErroredOnProcessing) {
    const message = Array.isArray(json.ErrorMessage) ? json.ErrorMessage.join("; ") : json.ErrorMessage || response.statusText;
    return {
      ok: false,
      providerStatus: response.status,
      providerRaw: json,
      parsedText: "",
      text: "",
      rows: [],
      rawLines: [],
      parsed: [],
      error: `OCR.space error: ${message}`
    };
  }

  const result = json.ParsedResults?.[0] || {};
  const text = String(result.ParsedText || "");
  const overlay = result.TextOverlay || null;
  const overlayLines = Array.isArray(overlay?.Lines) ? overlay.Lines : [];
  const firstOverlayLine = overlayLines[0] || null;
  const firstOverlayWords = Array.isArray(firstOverlayLine?.Words) ? firstOverlayLine.Words.slice(0, 10) : [];
  const overlayWordsCount = overlayLines.reduce((sum, line) => sum + (Array.isArray(line?.Words) ? line.Words.length : 0), 0);
  console.log(`ParsedText length ${text.length}`);
  const parsedRows = parseStatsText(text);
  console.log(`parsed rows count ${parsedRows.parsed.length}`);
  return {
    ok: true,
    providerStatus: response.status,
    providerRaw: json,
    textOverlay: overlay,
    hasOverlay: overlayWordsCount > 0,
    overlayLinesCount: overlayLines.length,
    overlayWordsCount,
    firstOverlayLine,
    firstOverlayWords,
    parsedText: text,
    text,
    rows: parsedRows.rows,
    rawLines: parsedRows.rawLines,
    parsed: parsedRows.parsed,
    error: null,
    provider: {
      status: response.status,
      processingTimeMs: json.ProcessingTimeInMilliseconds ?? null,
      fileParseExitCode: result.FileParseExitCode ?? null
    }
  };
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || `localhost:${PORT}`}`);

  if (req.method === "OPTIONS") {
    sendJson(res, 204, {});
    return;
  }

  if (req.method === "GET" && url.pathname === "/health") {
    console.log("GET /health");
    sendJson(res, 200, { ok: true });
    return;
  }

  if (req.method === "GET" && (url.pathname === "/" || url.pathname === "/ocr_backend_test.html")) {
    console.log("GET /ocr_backend_test.html");
    const filePath = path.join(__dirname, "ocr_backend_test.html");
    try {
      const html = fs.readFileSync(filePath);
      sendText(res, 200, "text/html; charset=utf-8", html);
    } catch (error) {
      console.error("static file error", error.stack || error);
      sendJson(res, 500, { error: "Failed to read ocr_backend_test.html" });
    }
    return;
  }

  if (req.method !== "POST" || url.pathname !== "/ocr-read") {
    sendJson(res, 404, { error: "Use GET /ocr_backend_test.html, GET /health, or POST /ocr-read" });
    return;
  }

  try {
    console.log("POST /ocr-read received");
    const body = await readBody(req);
    const image = await getIncomingImage(req, body);
    console.log(`image bytes size ${image.data.length}`);
    const result = await callOcrSpace(image);
    sendJson(res, result.ok ? 200 : 500, result);
  } catch (error) {
    console.error("POST /ocr-read failed", error.stack || error);
    sendJson(res, error.statusCode || 500, {
      ok: false,
      providerStatus: null,
      providerRaw: null,
      parsedText: "",
      error: String(error.message || error),
      text: "",
      rows: [],
      parsed: []
    });
  }
});

server.listen(PORT, () => {
  console.log(`server started http://localhost:${PORT}`);
  console.log(`OCR endpoint http://localhost:${PORT}/ocr-read`);
  console.log(`Test page http://localhost:${PORT}/ocr_backend_test.html`);
});
