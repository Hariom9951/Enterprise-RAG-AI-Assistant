/**
 * Enterprise RAG AI Assistant — API Error Message Extraction Helper
 * =================================================================
 * Safely extracts human-readable error messages from diverse error payloads,
 * including custom error envelopes, FastAPI HTTPExceptions ({ detail: string }),
 * and Pydantic validation error lists ({ detail: [{ msg: string }] }).
 */

export function getApiErrorMessage(
  err: unknown,
  fallback: string = "An error occurred."
): string {
  if (!err || typeof err !== "object") return fallback;
  const anyErr = err as Record<string, unknown>;
  const innerError = anyErr.error as Record<string, unknown> | undefined;
  if (innerError && typeof innerError.message === "string") {
    return innerError.message;
  }
  if (typeof anyErr.detail === "string") {
    return anyErr.detail;
  }
  if (Array.isArray(anyErr.detail) && anyErr.detail[0]?.msg) {
    const raw = String(anyErr.detail[0].msg);
    return raw.replace(/^Value error,\s*/i, "");
  }
  if (typeof anyErr.message === "string") {
    return anyErr.message;
  }
  return fallback;
}
