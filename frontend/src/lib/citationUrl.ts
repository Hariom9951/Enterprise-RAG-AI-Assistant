/**
 * Enterprise RAG AI Assistant — Safe Citation URL Validation Helper
 * ================================================================
 * Validates external citation links against malicious schemes and malformed inputs.
 *
 * Rules:
 * - Only absolute https:// URLs are allowed.
 * - http:// is rejected (no documented requirement for unencrypted external links).
 * - javascript:, data:, file:, and other unsafe schemes are rejected.
 * - Protocol-relative URLs (e.g. //attacker.com) are rejected.
 * - Malformed, blank, or non-string values are rejected.
 */

export function getSafeCitationUrl(rawUrl?: string | null): string | null {
  if (!rawUrl || typeof rawUrl !== "string") {
    return null;
  }

  const trimmed = rawUrl.trim();
  if (!trimmed || trimmed.startsWith("//")) {
    return null;
  }

  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol === "https:" && parsed.hostname) {
      return parsed.href;
    }
    return null;
  } catch {
    return null;
  }
}

export function isSafeCitationUrl(rawUrl?: string | null): boolean {
  return getSafeCitationUrl(rawUrl) !== null;
}
