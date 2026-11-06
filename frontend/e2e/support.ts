/**
 * E2E helpers: Mailpit (dev email), RFC 6238 TOTP for test authenticators, admin API session.
 * Test data only: synthetic `example.test` addresses and generated passwords.
 */
import { createHmac } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { type APIRequestContext, expect, type Page, request } from "@playwright/test";

export const MAILPIT_URL = process.env.MAILPIT_URL ?? "http://localhost:8025";
export const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:8080";
export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "e2e-admin@example.test";
const STATE_FILE = path.join(import.meta.dirname, ".state", "admin.json");

export interface AdminState {
  email: string;
  password: string;
  secret: string;
  recoveryCodes: string[];
}

export function saveAdmin(state: AdminState): void {
  mkdirSync(path.dirname(STATE_FILE), { recursive: true });
  writeFileSync(STATE_FILE, JSON.stringify(state), { mode: 0o600 });
}

export function loadAdmin(): AdminState {
  return JSON.parse(readFileSync(STATE_FILE, "utf8")) as AdminState;
}

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.test`;
}

export function strongPassword(): string {
  return `E2e-${Math.random().toString(36).slice(2)}-Pass-${Date.now() % 1000}`;
}

// ---------------------------------------------------------------- TOTP (RFC 6238, SHA-1, 6 digits)
function base32Decode(input: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of input.replace(/[\s=]/g, "").toUpperCase()) {
    bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  }
  const bytes = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

export function totp(secret: string, step = Math.floor(Date.now() / 30_000)): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(step));
  const digest = createHmac("sha1", base32Decode(secret)).update(counter).digest();
  const offset = digest[digest.length - 1]! & 0x0f;
  const value = (digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return value.toString().padStart(6, "0");
}

/** A code for a step not used before by this process (the server rejects replays). */
const usedSteps = new Set<number>();
export async function freshTotp(secret: string): Promise<string> {
  let step = Math.floor(Date.now() / 30_000);
  while (usedSteps.has(step)) {
    await new Promise((r) => setTimeout(r, 1_000));
    step = Math.floor(Date.now() / 30_000);
  }
  usedSteps.add(step);
  return totp(secret, step);
}

// ---------------------------------------------------------------- Mailpit
interface MailSummary {
  ID: string;
  Subject: string;
}

/** Wait for the newest email to `to` whose subject matches, and return its text body. */
export async function waitForMail(to: string, subject: RegExp, after = 0): Promise<string> {
  const api = await request.newContext({ baseURL: MAILPIT_URL });
  try {
    for (let attempt = 0; attempt < 40; attempt++) {
      const search = await api.get(`/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}`);
      const { messages } = (await search.json()) as { messages: MailSummary[] };
      const match = messages
        .slice(0, Math.max(0, messages.length - after))
        .find((m) => subject.test(m.Subject));
      if (match) {
        const message = await api.get(`/api/v1/message/${match.ID}`);
        return ((await message.json()) as { Text: string }).Text;
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    throw new Error(`No email to ${to} matching ${subject}`);
  } finally {
    await api.dispose();
  }
}

export async function mailCount(to: string): Promise<number> {
  const api = await request.newContext({ baseURL: MAILPIT_URL });
  const search = await api.get(`/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}`);
  const { messages } = (await search.json()) as { messages: MailSummary[] };
  await api.dispose();
  return messages.length;
}

/** The link path (without origin) from an email body, fragment included. */
export function linkFrom(body: string, page: string): string {
  const match = body.match(new RegExp(`https?://[^\\s]+(/(?:en|bn)/${page}#token=[\\w-]+)`));
  if (!match?.[1]) throw new Error(`No ${page} link in email`);
  return match[1];
}

// ---------------------------------------------------------------- admin API session
async function csrf(api: APIRequestContext): Promise<string> {
  await api.get("/api/v1/auth/csrf/");
  const cookie = (await api.storageState()).cookies.find((c) => c.name === "csrftoken");
  return cookie?.value ?? "";
}

/** API context signed in as the bootstrap admin (MFA verified). */
export async function adminApi(): Promise<{
  api: APIRequestContext;
  post: (url: string, data: object) => Promise<unknown>;
}> {
  const admin = loadAdmin();
  const api = await request.newContext({ baseURL: BASE_URL });
  const headers = async () => ({ "X-CSRFToken": await csrf(api), Referer: BASE_URL });
  const login = await api.post("/api/v1/auth/login/", {
    data: { email: admin.email, password: admin.password },
    headers: await headers(),
  });
  expect(login.status()).toBe(200);
  for (let attempt = 0; attempt < 3; attempt++) {
    const verify = await api.post("/api/v1/auth/mfa/verify/", {
      data: { code: await freshTotp(admin.secret) },
      headers: await headers(),
    });
    if (verify.ok()) break;
    if (attempt === 2) throw new Error(`admin MFA failed: ${verify.status()}`);
  }
  const post = async (url: string, data: object) => {
    const response = await api.post(url, { data, headers: await headers() });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  return { api, post };
}

// ---------------------------------------------------------------- CSP (security review M3)
/** Record every CSP violation the page reports; call before the first navigation. */
export async function trackCspViolations(page: Page): Promise<() => Promise<string[]>> {
  await page.addInitScript(() => {
    const w = window as unknown as { __cspViolations?: string[] };
    w.__cspViolations = [];
    document.addEventListener("securitypolicyviolation", (e) => {
      w.__cspViolations!.push(`${e.violatedDirective} ${e.blockedURI}`);
    });
  });
  return () =>
    page.evaluate(
      () => (window as unknown as { __cspViolations?: string[] }).__cspViolations ?? [],
    );
}
