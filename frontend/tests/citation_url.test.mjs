import test from "node:test";
import assert from "node:assert/strict";
import { getSafeCitationUrl, isSafeCitationUrl } from "../src/lib/citationUrl.ts";

test("Safe HTTPS URLs: valid absolute HTTPS URLs pass validation", () => {
  const safeUrls = [
    "https://github.com/org/repo/pull/42",
    "https://drive.google.com/file/d/abc123xyz/view",
    "https://mail.google.com/mail/u/0/#inbox/msg123",
    "https://www.linkedin.com/in/verified-profile",
    "https://corp.internal.net:8443/path?query=val#hash",
  ];

  for (const url of safeUrls) {
    assert.strictEqual(
      isSafeCitationUrl(url),
      true,
      `Expected ${url} to be safe`
    );
    assert.strictEqual(
      getSafeCitationUrl(url),
      url,
      `Expected ${url} to match parsed href`
    );
  }

  // Handles leading/trailing whitespace
  assert.strictEqual(
    getSafeCitationUrl("  https://example.com/doc.pdf  "),
    "https://example.com/doc.pdf"
  );
});

test("Malformed URLs: malformed inputs are rejected", () => {
  const malformed = [
    "not-a-valid-url",
    "https://",
    "https://:8080",
    "ht tps://space-in-protocol",
    "://missing-scheme.com",
    "https//missing-colon.com",
  ];

  for (const url of malformed) {
    assert.strictEqual(
      isSafeCitationUrl(url),
      false,
      `Expected ${url} to be rejected as malformed`
    );
    assert.strictEqual(getSafeCitationUrl(url), null);
  }
});

test("Missing URLs: null, undefined, empty, or non-string inputs are rejected", () => {
  const missingInputs = [
    null,
    undefined,
    "",
    "   ",
    "\t\n",
    12345,
    {},
    [],
    true,
  ];

  for (const input of missingInputs) {
    assert.strictEqual(
      isSafeCitationUrl(input),
      false,
      `Expected ${JSON.stringify(input)} to be rejected`
    );
    assert.strictEqual(getSafeCitationUrl(input), null);
  }
});

test("Protocol-relative URLs: leading // is strictly rejected", () => {
  const protocolRelative = [
    "//attacker.com",
    "//attacker.com/exploit",
    "//https://example.com",
    "  //evil.corp/payload  ",
  ];

  for (const url of protocolRelative) {
    assert.strictEqual(
      isSafeCitationUrl(url),
      false,
      `Expected protocol-relative ${url} to be rejected`
    );
    assert.strictEqual(getSafeCitationUrl(url), null);
  }
});

test("Unsafe schemes: javascript, data, file, and non-https schemes are rejected", () => {
  const unsafeSchemes = [
    "javascript:alert(1)",
    "javascript:void(0)",
    "JAVASCRIPT:alert(document.cookie)",
    "data:text/html,<script>alert('xss')</script>",
    "data:application/json;base64,eyJhIjoxfQ==",
    "file:///etc/passwd",
    "file:///C:/Windows/System32/calc.exe",
    "vbscript:msgbox(1)",
    "ftp://ftp.example.com/file.txt",
    "blob:https://example.com/uuid-blob",
  ];

  for (const url of unsafeSchemes) {
    assert.strictEqual(
      isSafeCitationUrl(url),
      false,
      `Expected unsafe scheme ${url} to be rejected`
    );
    assert.strictEqual(getSafeCitationUrl(url), null);
  }
});

test("HTTP scheme: unencrypted http:// URLs are rejected by default", () => {
  const httpUrls = [
    "http://example.com",
    "http://insecure.internal/docs",
    "http://localhost:8000/api",
  ];

  for (const url of httpUrls) {
    assert.strictEqual(
      isSafeCitationUrl(url),
      false,
      `Expected unencrypted HTTP ${url} to be rejected`
    );
    assert.strictEqual(getSafeCitationUrl(url), null);
  }
});
