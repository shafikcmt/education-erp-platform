/**
 * Content-Security-Policy (security review M3). Nonce-based scripts: Next.js reads the nonce
 * from the request's CSP header and stamps it on its own <script> tags; 'strict-dynamic' lets
 * those scripts load the app's chunks, and no inline or eval'd script runs without the nonce.
 *
 * - `img-src data:` is needed for the server-rendered MFA QR code (an SVG data URI).
 * - `style-src 'unsafe-inline'`: Radix UI's dialog scroll-lock injects <style> elements and style
 *   attributes at runtime without a nonce. This affects CSS only; scripts stay nonce-only, with
 *   no 'unsafe-inline' or 'unsafe-eval' (zod runs jitless, see lib/zod-config.ts).
 * - Development adds 'unsafe-eval' for React Refresh; production builds never do.
 */
export function buildCsp(nonce: string, { dev = false }: { dev?: boolean } = {}): string {
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "script-src": [
      "'self'",
      `'nonce-${nonce}'`,
      "'strict-dynamic'",
      ...(dev ? ["'unsafe-eval'"] : []),
    ],
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:"],
    "font-src": ["'self'"],
    "connect-src": ["'self'", ...(dev ? ["ws:"] : [])],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
  };
  return Object.entries(directives)
    .map(([name, values]) => `${name} ${values.join(" ")}`)
    .join("; ");
}

/** 128-bit random nonce, base64 (Web Crypto: available in the Next.js proxy runtime). */
export function createNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}
