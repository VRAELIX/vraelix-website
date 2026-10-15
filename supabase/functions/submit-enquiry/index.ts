import postgres from "npm:postgres@3.4.5";

const MAX_BODY_BYTES = 10 * 1024;
const MAX_REQUESTS = 5;
const RATE_WINDOW_SECONDS = 15 * 60;
const TURNSTILE_ACTION = "vraelix_enquiry";
const ALLOWED_SERVICES = new Set([
  "Website Development",
  "Business & Corporate Websites",
  "E-commerce Solutions",
  "Landing Pages & Conversion Experiences",
  "SEO & Performance",
  "Website Maintenance & Optimization",
  "Business Automation",
  "Custom Digital Solutions",
  "Other",
  "Not sure yet",
]);
// These names are supported by the code, but are not inherently trustworthy.
// Keep rate limiting unavailable until staging confirms the Supabase ingress
// overwrites the configured header and callers cannot spoof its client value.
const SUPPORTED_CLIENT_IP_HEADERS = new Set(["cf-connecting-ip", "x-real-ip", "x-forwarded-for"]);
const RATE_LIMIT_DIAGNOSTIC_CODES = new Set([
  "rate_limit_not_configured",
  "rate_limit_configuration_invalid",
  "ip_header_configuration_invalid",
  "client_ip_unavailable",
  "rate_limit_unavailable",
]);
const TURNSTILE_ERROR_CODES = new Set([
  "missing-input-secret",
  "invalid-input-secret",
  "missing-input-response",
  "invalid-input-response",
  "bad-request",
  "timeout-or-duplicate",
  "internal-error",
]);
let database: ReturnType<typeof postgres> | null = null;

class TurnstileVerificationError extends Error {
  constructor(
    readonly httpStatus: 403 | 503,
    readonly reason: string,
    readonly providerErrorCodes: string[] = [],
    readonly providerStatus?: number,
  ) {
    super(reason);
  }
}

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
  if (!/^\+?[0-9][0-9\s().-]*$/.test(phone_number) || digits.length < 7 || digits.length > 15) {
    throw new Error("phone_invalid");
  }
  const service = cleanText(payload.service, "service", 100, true);
  if (!ALLOWED_SERVICES.has(service)) throw new Error("service_invalid");
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
  if (!headerName || !SUPPORTED_CLIENT_IP_HEADERS.has(headerName)) {
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

function activeProjectRef(): string {
  const configuredUrl = Deno.env.get("SUPABASE_URL") || "";
  let hostname = "";
  try {
    const parsed = new URL(configuredUrl);
    if (parsed.protocol !== "https:" || parsed.username || parsed.password ||
        parsed.pathname !== "/" || parsed.search || parsed.hash) {
      throw new Error("project_configuration_invalid");
    }
    hostname = parsed.hostname.toLowerCase();
  } catch (_) {
    throw new Error("project_configuration_invalid");
  }
  const match = hostname.match(/^([a-z0-9]+)\.supabase\.co$/);
  if (!match) throw new Error("project_configuration_invalid");
  return match[1];
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
  if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.search || parsed.hash ||
      (parsed.port && parsed.port !== "443") || !parsed.hostname.toLowerCase().endsWith(".upstash.io")) {
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

function maskedRateLimitDiagnostic(error: unknown): string {
  if (error instanceof Error && RATE_LIMIT_DIAGNOSTIC_CODES.has(error.message)) {
    return error.message;
  }
  return "unexpected_rate_limit_error";
}

async function verifyTurnstile(token: string, expectedHostname: string): Promise<void> {
  const secret = Deno.env.get("VRAELIX_TURNSTILE_SECRET_KEY") || "";
  if (!secret) throw new TurnstileVerificationError(503, "secret_not_configured");

  let response: Response;
  try {
    response = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ secret, response: token }),
      signal: AbortSignal.timeout(8000),
    });
  } catch (_) {
    throw new TurnstileVerificationError(503, "provider_unreachable");
  }
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new TurnstileVerificationError(503, "provider_http_error", [], response.status);
  }

  let result: Record<string, unknown>;
  try {
    const parsed = await response.json();
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid_provider_response");
    result = parsed as Record<string, unknown>;
  } catch (_) {
    throw new TurnstileVerificationError(503, "provider_response_invalid");
  }

  const providerErrorCodes = Array.isArray(result["error-codes"])
    ? result["error-codes"].filter((code): code is string => typeof code === "string" && TURNSTILE_ERROR_CODES.has(code)).slice(0, 5)
    : [];
  if (result.success !== true) {
    const secretRejected = providerErrorCodes.includes("missing-input-secret") || providerErrorCodes.includes("invalid-input-secret");
    throw new TurnstileVerificationError(secretRejected ? 503 : 403, secretRejected ? "secret_rejected" : "token_rejected", providerErrorCodes);
  }
  if (result.action !== TURNSTILE_ACTION) throw new TurnstileVerificationError(403, "action_mismatch");
  if (result.hostname !== expectedHostname) throw new TurnstileVerificationError(403, "hostname_mismatch");
}

function getDatabase() {
  // Bind the private writer URL to this function's project so a staging
  // deployment fails closed if its database secret accidentally points at prod.
  const connectionString = Deno.env.get("VRAELIX_ENQUIRY_DATABASE_URL") || "";
  if (!connectionString) throw new Error("database_configuration_missing");
  let parsed: URL;
  let username = "";
  try {
    parsed = new URL(connectionString);
    username = decodeURIComponent(parsed.username);
  } catch (_) {
    throw new Error("database_configuration_invalid");
  }
  const projectRef = activeProjectRef();
  if (!( ["postgres:", "postgresql:"].includes(parsed.protocol)) ||
      !parsed.hostname.toLowerCase().endsWith(".pooler.supabase.com") || parsed.port !== "6543" ||
      username !== `vraelix_enquiry_writer.${projectRef}` || parsed.pathname !== "/postgres") {
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

function maskedDatabaseDiagnostic(error: unknown): { category: string; sqlstate?: string } {
  const knownConfigurationErrors = new Set([
    "database_configuration_missing",
    "database_configuration_invalid",
    "project_configuration_invalid",
  ]);
  if (error instanceof Error && knownConfigurationErrors.has(error.message)) {
    return { category: error.message };
  }

  const candidate = error && typeof error === "object" && "code" in error
    ? (error as { code?: unknown }).code
    : undefined;
  const sqlstate = typeof candidate === "string" && /^[0-9A-Z]{5}$/.test(candidate)
    ? candidate
    : "";
  if (!sqlstate) return { category: "connection_or_client_error" };

  const knownCategories: Record<string, string> = {
    "23502": "not_null_violation",
    "23503": "foreign_key_violation",
    "23505": "unique_violation",
    "23514": "check_violation",
    "28P01": "authentication_failed",
    "3D000": "database_not_found",
    "42501": "permission_denied",
    "42703": "column_not_found",
    "42P01": "relation_not_found",
  };
  const category = knownCategories[sqlstate] || (sqlstate.startsWith("08")
    ? "connection_error"
    : "database_error");
  return { category, sqlstate };
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
  const mediaType = (request.headers.get("content-type") || "").split(";", 1)[0].trim().toLowerCase();
  if (mediaType !== "application/json") {
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
    if (!exceeded && !unconfigured) {
      console.error(JSON.stringify({
        event: "rate_limit_service_error",
        reason: maskedRateLimitDiagnostic(error),
        request_id: requestId,
      }));
    }
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
    const failure = error instanceof TurnstileVerificationError
      ? error
      : new TurnstileVerificationError(503, "provider_unavailable");
    console.error(JSON.stringify({
      event: "turnstile_verification_failed",
      reason: failure.reason,
      provider_error_codes: failure.providerErrorCodes,
      ...(failure.providerStatus ? { provider_status: failure.providerStatus } : {}),
      request_id: requestId,
    }));
    return jsonResponse(failure.httpStatus, {
      error: failure.httpStatus === 403 ? "verification_failed" : "protection_unavailable",
      request_id: requestId,
    }, corsHeaders);
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
  } catch (error) {
    console.error(JSON.stringify({
      event: "enquiry_insert_failed",
      ...maskedDatabaseDiagnostic(error),
      request_id: requestId,
    }));
    return jsonResponse(503, { error: "submission_failed", request_id: requestId }, corsHeaders);
  }

  return jsonResponse(201, { success: true, submitted_at: submittedAt, request_id: requestId }, corsHeaders);
});
