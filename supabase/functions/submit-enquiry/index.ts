import postgres from "npm:postgres@3.4.5";

const MAX_BODY_BYTES = 10 * 1024;
const MAX_REQUESTS = 5;
const RATE_WINDOW_SECONDS = 15 * 60;
const TURNSTILE_ACTION = "vraelix_enquiry";
const TRUSTED_IP_HEADERS = new Set(["cf-connecting-ip", "x-real-ip", "x-forwarded-for"]);
let database: ReturnType<typeof postgres> | null = null;

const corsHeadersFor = (origin: string) => ({
  "access-control-allow-origin": origin,
  "access-control-allow-methods": "POST, OPTIONS",
  "access-control-allow-headers": "apikey, content-type",
  "access-control-max-age": "86400",
  "cache-control": "no-store",
  vary: "Origin",
});

function jsonResponse(
  status: number,
  body: Record<string, unknown>,
  corsHeaders: Record<string, string> = {},
) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...corsHeaders,
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function parseOrigin(value: string): string | null {
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password ||
        url.pathname !== "/" || url.search || url.hash) return null;
    return url.origin;
  } catch (_) {
    return null;
  }
}

function allowedOrigins(): Set<string> {
  const configured = (Deno.env.get("VRAELIX_ALLOWED_ORIGINS") || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (configured.length === 0) throw new Error("origin_configuration_missing");
  const normalized = configured.map(parseOrigin);
  if (normalized.some((origin) => !origin)) throw new Error("origin_configuration_invalid");
  return new Set(normalized as string[]);
}

async function readBodyLimited(request: Request): Promise<string> {
  const lengthHeader = request.headers.get("content-length");
  if (lengthHeader && Number(lengthHeader) > MAX_BODY_BYTES) throw new Error("body_too_large");
  if (!request.body) throw new Error("body_missing");

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_BODY_BYTES) {
      await reader.cancel();
      throw new Error("body_too_large");
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

function cleanText(value: unknown, name: string, limit: number, required = false, multiline = false): string {
  if (value === undefined && !required) return "";
  if (typeof value !== "string") throw new Error("field_invalid");
  const controls = multiline
    ? /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g
    : /[\u0000-\u001f\u007f]/g;
  const normalized = value.normalize("NFC").replace(controls, multiline ? "" : " ").trim();
  if (normalized.length > limit || (required && normalized.length === 0)) throw new Error("field_invalid");
  if (name === "full_name" && normalized.length < 2) throw new Error("field_invalid");
  if (name === "project_description" && normalized.length < 10) throw new Error("field_invalid");
  return normalized;
}

function normalizePayload(raw: unknown) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("payload_invalid");
  const payload = raw as Record<string, unknown>;
  const allowedFields = new Set([
    "full_name", "email", "phone_number", "company", "service",
    "project_description", "budget", "timeline", "contact_method",
    "source", "submitted_at", "turnstile_token",
  ]);
  if (Object.keys(payload).some((key) => !allowedFields.has(key))) throw new Error("payload_invalid");

  const full_name = cleanText(payload.full_name, "full_name", 100, true);
  const email = cleanText(payload.email, "email", 254, true).toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error("email_invalid");
  const phone_number = cleanText(payload.phone_number, "phone_number", 32, true);
  const digits = phone_number.replace(/\D/g, "");
  if (!/^[+0-9().\s-]+$/.test(phone_number) || digits.length < 7 || digits.length > 15) {
    throw new Error("phone_invalid");
  }
  const service = cleanText(payload.service, "service", 100, true);
  const project_description = cleanText(payload.project_description, "project_description", 2400, true, true);
  const contact_method = cleanText(payload.contact_method, "contact_method", 40, true);
  if (!["Email", "WhatsApp", "Instagram / Social", "Other"].includes(contact_method)) {
    throw new Error("contact_method_invalid");
  }
  const company = cleanText(payload.company, "company", 160);
  const budget = cleanText(payload.budget, "budget", 120);
  const timeline = cleanText(payload.timeline, "timeline", 120);
  const turnstileToken = cleanText(payload.turnstile_token, "turnstile_token", 2048, true);

  return {
    fields: { full_name, email, phone_number, company, service, project_description, budget, timeline, contact_method },
    turnstileToken,
  };
}

function clientIp(request: Request): string {
  const headerName = (Deno.env.get("VRAELIX_CLIENT_IP_HEADER") || "").trim().toLowerCase();
  if (!headerName || !TRUSTED_IP_HEADERS.has(headerName)) {
    throw new Error("ip_header_configuration_invalid");
  }
  const rawHeader = request.headers.get(headerName)?.trim() || "";
  const ip = headerName === "x-forwarded-for" ? rawHeader.split(",")[0].trim() : rawHeader;
  if (!ip || ip.length > 64 || /[^0-9a-f:.]/i.test(ip) ||
      !rawHeader) {
    throw new Error("client_ip_unavailable");
  }
  const ipv4 = ip.split(".");
  const validIpv4 = ipv4.length === 4 && ipv4.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255);
  let validIpv6 = false;
  if (ip.includes(":")) {
    try {
      new URL(`http://[${ip}]/`);
      validIpv6 = true;
    } catch (_) {}
  }
  if (!validIpv4 && !validIpv6) throw new Error("client_ip_unavailable");
  return ip;
}

async function hashRateLimitIdentity(ip: string, salt: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(salt),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const digest = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(ip));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function enforceRateLimit(request: Request): Promise<void> {
  const restUrl = Deno.env.get("UPSTASH_REDIS_REST_URL") || "";
  const restToken = Deno.env.get("UPSTASH_REDIS_REST_TOKEN") || "";
  const salt = Deno.env.get("VRAELIX_RATE_LIMIT_HASH_SECRET") || "";
  if (!restUrl || !restToken || salt.length < 32) throw new Error("rate_limit_not_configured");
  const parsed = new URL(restUrl);
  if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error("rate_limit_configuration_invalid");
  }

  const identity = await hashRateLimitIdentity(clientIp(request), salt);
  const script = "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],tonumber(ARGV[1])); end; return n";
  const response = await fetch(parsed.origin + parsed.pathname.replace(/\/$/, ""), {
    method: "POST",
    headers: {
      authorization: `Bearer ${restToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(["EVAL", script, 1, `vraelix:enquiry:${identity}`, RATE_WINDOW_SECONDS]),
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error("rate_limit_unavailable");
  const result = await response.json();
  if (typeof result?.result !== "number") throw new Error("rate_limit_unavailable");
  if (result.result > MAX_REQUESTS) throw new Error("rate_limit_exceeded");
}

async function verifyTurnstile(token: string, expectedHostname: string): Promise<void> {
  const secret = Deno.env.get("VRAELIX_TURNSTILE_SECRET_KEY") || "";
  if (!secret) throw new Error("turnstile_not_configured");
  const response = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ secret, response: token }),
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new Error("turnstile_unavailable");
  const result = await response.json();
  if (result?.success !== true || result?.action !== TURNSTILE_ACTION || result?.hostname !== expectedHostname) {
    throw new Error("turnstile_invalid");
  }
}

function getDatabase() {
  const connectionString = Deno.env.get("VRAELIX_ENQUIRY_DATABASE_URL") || "";
  if (!connectionString) throw new Error("database_configuration_missing");
  let parsed: URL;
  try {
    parsed = new URL(connectionString);
  } catch (_) {
    throw new Error("database_configuration_invalid");
  }
  if (!(["postgres:", "postgresql:"].includes(parsed.protocol)) ||
      !parsed.hostname || parsed.port !== "6543" ||
      !decodeURIComponent(parsed.username).startsWith("vraelix_enquiry_writer.")) {
    throw new Error("database_configuration_invalid");
  }
  if (!database) {
    database = postgres(connectionString, {
      ssl: "require",
      max: 1,
      idle_timeout: 5,
      connect_timeout: 5,
      prepare: false,
    });
  }
  return database;
}

Deno.serve(async (request: Request) => {
  const requestId = crypto.randomUUID();
  let origin = "";
  let corsHeaders: Record<string, string> = {};
  try {
    origin = request.headers.get("origin") || "";
    const normalizedOrigin = parseOrigin(origin);
    if (!normalizedOrigin || !allowedOrigins().has(normalizedOrigin)) {
      return jsonResponse(403, { error: "origin_not_allowed", request_id: requestId });
    }
    corsHeaders = corsHeadersFor(normalizedOrigin);
  } catch (_) {
    return jsonResponse(503, { error: "service_unavailable", request_id: requestId });
  }

  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders });
  if (request.method !== "POST") return jsonResponse(405, { error: "method_not_allowed", request_id: requestId }, corsHeaders);
  if (!request.headers.get("apikey")) {
    return jsonResponse(401, { error: "api_key_required", request_id: requestId }, corsHeaders);
  }
  if (!(request.headers.get("content-type") || "").toLowerCase().startsWith("application/json")) {
    return jsonResponse(415, { error: "unsupported_media_type", request_id: requestId }, corsHeaders);
  }

  let rawBody: string;
  try {
    rawBody = await readBodyLimited(request);
  } catch (error) {
    const tooLarge = error instanceof Error && error.message === "body_too_large";
    return jsonResponse(tooLarge ? 413 : 400, { error: tooLarge ? "request_too_large" : "invalid_request", request_id: requestId }, corsHeaders);
  }

  let normalized: ReturnType<typeof normalizePayload>;
  try {
    await enforceRateLimit(request);
  } catch (error) {
    const exceeded = error instanceof Error && error.message === "rate_limit_exceeded";
    const unconfigured = error instanceof Error && error.message.endsWith("not_configured");
    if (!exceeded && !unconfigured) console.error(JSON.stringify({ event: "rate_limit_service_error", request_id: requestId }));
    return jsonResponse(exceeded ? 429 : 503, {
      error: exceeded ? "rate_limited" : "protection_unavailable",
      request_id: requestId,
    }, corsHeaders);
  }

  try {
    normalized = normalizePayload(JSON.parse(rawBody));
  } catch (_) {
    return jsonResponse(400, { error: "invalid_enquiry", request_id: requestId }, corsHeaders);
  }

  try {
    await verifyTurnstile(normalized.turnstileToken, new URL(origin).hostname);
  } catch (error) {
    const unconfigured = error instanceof Error && error.message === "turnstile_not_configured";
    if (!unconfigured) console.error(JSON.stringify({ event: "turnstile_verification_failed", request_id: requestId }));
    return jsonResponse(403, { error: unconfigured ? "protection_unavailable" : "verification_failed", request_id: requestId }, corsHeaders);
  }

  if (!Deno.env.get("VRAELIX_ENQUIRY_DATABASE_URL")) {
    console.error(JSON.stringify({ event: "database_configuration_missing", request_id: requestId }));
    return jsonResponse(503, { error: "service_unavailable", request_id: requestId }, corsHeaders);
  }

  const submittedAt = new Date().toISOString();
  try {
    const sql = getDatabase();
    await sql`INSERT INTO public.enquiries (
      full_name, email, phone_number, company, service, project_description,
      budget, timeline, contact_method, source, submitted_at
    ) VALUES (
      ${normalized.fields.full_name},
      ${normalized.fields.email},
      ${normalized.fields.phone_number},
      ${normalized.fields.company || null},
      ${normalized.fields.service},
      ${normalized.fields.project_description},
      ${normalized.fields.budget || null},
      ${normalized.fields.timeline || null},
      ${normalized.fields.contact_method},
      ${"VRAELIX Website"},
      ${submittedAt}
    )`;
  } catch (_) {
    console.error(JSON.stringify({ event: "enquiry_insert_failed", request_id: requestId }));
    return jsonResponse(503, { error: "submission_failed", request_id: requestId }, corsHeaders);
  }

  return jsonResponse(201, { success: true, submitted_at: submittedAt, request_id: requestId }, corsHeaders);
});
