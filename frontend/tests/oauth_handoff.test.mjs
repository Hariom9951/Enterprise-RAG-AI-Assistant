import test from "node:test";
import assert from "node:assert/strict";

// =============================================================================
// Mock Browser Environment & Helpers
// =============================================================================

class MockLocalStorage {
  constructor() {
    this.store = {};
  }
  getItem(key) {
    return this.store[key] ?? null;
  }
  setItem(key, value) {
    this.store[key] = String(value);
  }
  removeItem(key) {
    delete this.store[key];
  }
  clear() {
    this.store = {};
  }
}

class MockHistory {
  constructor() {
    this.history = [];
  }
  replaceState(state, title, url) {
    this.history.push({ state, title, url, timestamp: Date.now() });
  }
}

class MockLocation {
  constructor(pathname = "/settings", search = "") {
    this.pathname = pathname;
    this.search = search;
  }
}

function createAuthHelper(storage) {
  const ACCESS_TOKEN_KEY = "rag_access_token";
  const REFRESH_TOKEN_KEY = "rag_refresh_token";
  return {
    getAccessToken: () => storage.getItem(ACCESS_TOKEN_KEY),
    getRefreshToken: () => storage.getItem(REFRESH_TOKEN_KEY),
    setTokens: (access, refresh) => {
      storage.setItem(ACCESS_TOKEN_KEY, access);
      storage.setItem(REFRESH_TOKEN_KEY, refresh);
    },
    clearTokens: () => {
      storage.removeItem(ACCESS_TOKEN_KEY);
      storage.removeItem(REFRESH_TOKEN_KEY);
    },
    isAuthenticated: () => storage.getItem(ACCESS_TOKEN_KEY) !== null,
  };
}

/**
 * Pure simulation of the OAuth handoff logic implemented in SettingsPage.
 * Validates parameter parsing, immediate URL cleaning, duplicate submission
 * protection, authentication check, and backend callback invocation.
 */
async function executeOAuthHandoff({
  location,
  history,
  auth,
  oauthApi,
  callbackHandledRef,
  onToast,
  onRefreshConnections,
}) {
  if (callbackHandledRef.current) {
    return { skipped: true, reason: "duplicate_submission_prevented" };
  }

  const params = new URLSearchParams(location.search);
  const action = params.get("action");
  const provider = params.get("provider");
  const code = params.get("code");
  const state = params.get("state");
  const error = params.get("error");
  const errorDescription = params.get("error_description");

  const hasCallbackParams =
    action === "link" || Boolean(error) || (Boolean(code) && Boolean(state));

  if (!hasCallbackParams) {
    return { skipped: true, reason: "no_callback_parameters" };
  }

  // Prevent duplicate execution (React StrictMode / remount)
  callbackHandledRef.current = true;

  // Immediate URL cleanup: scrub parameters before any asynchronous network call
  const cleanUrl = location.pathname;
  history.replaceState({}, "Settings", cleanUrl);

  // 1. Handle provider-reported errors (e.g. consent denied)
  if (error) {
    const desc = errorDescription || error;
    onToast({
      type: "error",
      message: `OAuth authorization cancelled or denied: ${desc}`,
    });
    return { success: false, error: desc };
  }

  // 2. Validate action and provider
  if (action !== "link" || provider !== "github" || !code || !state) {
    onToast({
      type: "error",
      message: "Invalid or incomplete OAuth callback parameters received.",
    });
    return { success: false, error: "invalid_parameters" };
  }

  // 3. Authenticated check: Do NOT submit callback if unauthenticated
  if (!auth.isAuthenticated()) {
    onToast({
      type: "error",
      message:
        "You must be signed in to connect an application. Please log in and restart the authorization flow.",
    });
    return { success: false, error: "unauthenticated" };
  }

  // 4. Submit authenticated POST callback
  try {
    const res = await oauthApi.completeCallback("github", { code, state });
    onToast({
      type: "success",
      message: res.message || "Successfully connected GitHub application.",
    });
    if (onRefreshConnections) {
      await onRefreshConnections();
    }
    return { success: true, data: res };
  } catch (err) {
    const msg = err?.detail || err?.message || "Failed to connect GitHub application.";
    onToast({
      type: "error",
      message: `GitHub connection failed: ${msg}`,
    });
    return { success: false, error: msg };
  }
}


// =============================================================================
// Test Suites
// =============================================================================


test("Successful handoff: scrubs URL immediately, submits authenticated callback, and refreshes connections", async () => {
  const storage = new MockLocalStorage();
  const auth = createAuthHelper(storage);
  auth.setTokens("valid_user_jwt_access", "valid_refresh");

  const history = new MockHistory();
  const location = new MockLocation(
    "/settings",
    "?provider=github&code=gh_auth_code_123&state=gh_state_token_456&action=link"
  );

  let apiCalledWith = null;
  let connectionRefreshed = false;
  const toasts = [];

  const mockOAuthApi = {
    completeCallback: async (provider, payload) => {
      // Assert that URL was cleaned BEFORE or AT THE TIME the API call was made
      assert.equal(history.history.length, 1);
      assert.equal(history.history[0].url, "/settings");
      apiCalledWith = { provider, payload };
      return {
        success: true,
        provider: "github",
        message: "Successfully connected GitHub application.",
        redirect_url: "/settings",
      };
    },
  };

  const callbackHandledRef = { current: false };

  const result = await executeOAuthHandoff({
    location,
    history,
    auth,
    oauthApi: mockOAuthApi,
    callbackHandledRef,
    onToast: (toast) => toasts.push(toast),
    onRefreshConnections: async () => {
      connectionRefreshed = true;
    },
  });

  assert.equal(result.success, true);
  assert.equal(callbackHandledRef.current, true);
  assert.deepEqual(apiCalledWith, {
    provider: "github",
    payload: { code: "gh_auth_code_123", state: "gh_state_token_456" },
  });
  assert.equal(connectionRefreshed, true);
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].type, "success");
  assert.match(toasts[0].message, /Successfully connected/);

  // Assert URL was scrubbed
  assert.equal(history.history.length, 1);
  assert.equal(history.history[0].url, "/settings");
});


test("URL cleanup timing: URL parameters are scrubbed before API completes", async () => {
  const storage = new MockLocalStorage();
  const auth = createAuthHelper(storage);
  auth.setTokens("valid_jwt", "valid_refresh");

  const history = new MockHistory();
  const location = new MockLocation(
    "/settings",
    "?provider=github&code=secret_code&state=secret_state&action=link"
  );

  let urlCleanedAtCallTime = false;
  const mockOAuthApi = {
    completeCallback: async () => {
      urlCleanedAtCallTime =
        history.history.length > 0 && history.history[0].url === "/settings";
      return { success: true, provider: "github", message: "Connected." };
    },
  };

  const callbackHandledRef = { current: false };
  await executeOAuthHandoff({
    location,
    history,
    auth,
    oauthApi: mockOAuthApi,
    callbackHandledRef,
    onToast: () => {},
  });

  assert.equal(urlCleanedAtCallTime, true);
});


test("Unauthenticated user: scrubs URL, never submits callback, does not store credentials, and warns user", async () => {
  const storage = new MockLocalStorage();
  const auth = createAuthHelper(storage);
  // User is not authenticated
  assert.equal(auth.isAuthenticated(), false);

  const history = new MockHistory();
  const location = new MockLocation(
    "/settings",
    "?provider=github&code=unauthenticated_code&state=unauthenticated_state&action=link"
  );

  let apiCalled = false;
  const mockOAuthApi = {
    completeCallback: async () => {
      apiCalled = true;
      return { success: true };
    },
  };

  const toasts = [];
  const callbackHandledRef = { current: false };

  const result = await executeOAuthHandoff({
    location,
    history,
    auth,
    oauthApi: mockOAuthApi,
    callbackHandledRef,
    onToast: (toast) => toasts.push(toast),
  });

  assert.equal(result.success, false);
  assert.equal(result.error, "unauthenticated");
  assert.equal(apiCalled, false);

  // URL was scrubbed
  assert.equal(history.history.length, 1);
  assert.equal(history.history[0].url, "/settings");

  // User was notified to log in
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].type, "error");
  assert.match(toasts[0].message, /must be signed in/);

  // Zero OAuth parameters written to localStorage
  assert.equal(storage.getItem("code"), null);
  assert.equal(storage.getItem("state"), null);
  assert.equal(storage.getItem("github_token"), null);
  assert.deepEqual(storage.store, {});
});


test("Provider error (access_denied): scrubs URL and shows denial notification without API submission", async () => {
  const storage = new MockLocalStorage();
  const auth = createAuthHelper(storage);
  auth.setTokens("jwt", "refresh");

  const history = new MockHistory();
  const location = new MockLocation(
    "/settings",
    "?error=access_denied&error_description=The+user+has+denied+your+application+access."
  );

  let apiCalled = false;
  const mockOAuthApi = {
    completeCallback: async () => {
      apiCalled = true;
    },
  };

  const toasts = [];
  const callbackHandledRef = { current: false };

  const result = await executeOAuthHandoff({
    location,
    history,
    auth,
    oauthApi: mockOAuthApi,
    callbackHandledRef,
    onToast: (toast) => toasts.push(toast),
  });

  assert.equal(result.success, false);
  assert.equal(apiCalled, false);
  assert.equal(history.history[0].url, "/settings");
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].type, "error");
  assert.match(toasts[0].message, /cancelled or denied/);
});


test("Duplicate submission protection: React StrictMode / remount executes at most once", async () => {
  const storage = new MockLocalStorage();
  const auth = createAuthHelper(storage);
  auth.setTokens("jwt", "refresh");

  const history = new MockHistory();
  const location = new MockLocation(
    "/settings",
    "?provider=github&code=code_1&state=state_1&action=link"
  );

  let apiCallCount = 0;
  const mockOAuthApi = {
    completeCallback: async () => {
      apiCallCount += 1;
      return { success: true, provider: "github", message: "Connected" };
    },
  };

  const callbackHandledRef = { current: false };

  // First mount
  const res1 = await executeOAuthHandoff({
    location,
    history,
    auth,
    oauthApi: mockOAuthApi,
    callbackHandledRef,
    onToast: () => {},
  });
  assert.equal(res1.success, true);
  assert.equal(apiCallCount, 1);

  // Simulated StrictMode second invocation
  const res2 = await executeOAuthHandoff({
    location,
    history,
    auth,
    oauthApi: mockOAuthApi,
    callbackHandledRef,
    onToast: () => {},
  });
  assert.equal(res2.skipped, true);
  assert.equal(res2.reason, "duplicate_submission_prevented");
  // Crucially, API was NOT called a second time
  assert.equal(apiCallCount, 1);
});


test("Backend error handling: state mismatch or expiry displays error and does not retry", async () => {
  const storage = new MockLocalStorage();
  const auth = createAuthHelper(storage);
  auth.setTokens("jwt", "refresh");

  const history = new MockHistory();
  const location = new MockLocation(
    "/settings",
    "?provider=github&code=code_stolen&state=state_victim&action=link"
  );

  let callCount = 0;
  const mockOAuthApi = {
    completeCallback: async () => {
      callCount += 1;
      const err = new Error("Bad Request");
      err.detail = "OAuth state user binding mismatch. State belongs to another user session.";
      throw err;
    },
  };

  const toasts = [];
  const callbackHandledRef = { current: false };

  const result = await executeOAuthHandoff({
    location,
    history,
    auth,
    oauthApi: mockOAuthApi,
    callbackHandledRef,
    onToast: (toast) => toasts.push(toast),
  });

  assert.equal(result.success, false);
  assert.equal(callCount, 1);
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].type, "error");
  assert.match(toasts[0].message, /user binding mismatch/);
  // URL was still scrubbed
  assert.equal(history.history[0].url, "/settings");
});


test("Missing or invalid parameters: fails closed without API calls", async () => {
  const storage = new MockLocalStorage();
  const auth = createAuthHelper(storage);
  auth.setTokens("jwt", "refresh");

  const history = new MockHistory();
  // Missing code
  const location = new MockLocation("/settings", "?provider=github&state=xyz&action=link");

  let apiCalled = false;
  const mockOAuthApi = {
    completeCallback: async () => {
      apiCalled = true;
    },
  };

  const toasts = [];
  const callbackHandledRef = { current: false };

  const result = await executeOAuthHandoff({
    location,
    history,
    auth,
    oauthApi: mockOAuthApi,
    callbackHandledRef,
    onToast: (toast) => toasts.push(toast),
  });

  assert.equal(result.success, false);
  assert.equal(apiCalled, false);
  assert.equal(toasts[0].type, "error");
});


test("Unsupported provider: rejects non-github providers gracefully", async () => {
  const storage = new MockLocalStorage();
  const auth = createAuthHelper(storage);
  auth.setTokens("jwt", "refresh");

  const history = new MockHistory();
  const location = new MockLocation(
    "/settings",
    "?provider=malicious_provider&code=abc&state=xyz&action=link"
  );

  let apiCalled = false;
  const mockOAuthApi = {
    completeCallback: async () => {
      apiCalled = true;
    },
  };

  const toasts = [];
  const callbackHandledRef = { current: false };

  const result = await executeOAuthHandoff({
    location,
    history,
    auth,
    oauthApi: mockOAuthApi,
    callbackHandledRef,
    onToast: (toast) => toasts.push(toast),
  });

  assert.equal(result.success, false);
  assert.equal(apiCalled, false);
});


test("Storage hygiene: no OAuth parameters or tokens ever written to persistent storage", async () => {
  const storage = new MockLocalStorage();
  const auth = createAuthHelper(storage);
  auth.setTokens("my_jwt", "my_refresh");

  const history = new MockHistory();
  const location = new MockLocation(
    "/settings",
    "?provider=github&code=super_secret_code_123&state=state_456&action=link"
  );

  const mockOAuthApi = {
    completeCallback: async () => ({
      success: true,
      provider: "github",
      message: "Connected",
    }),
  };

  const callbackHandledRef = { current: false };
  await executeOAuthHandoff({
    location,
    history,
    auth,
    oauthApi: mockOAuthApi,
    callbackHandledRef,
    onToast: () => {},
  });

  // Verify storage only has JWT and refresh token; zero code, state, or provider tokens
  assert.equal(storage.getItem("code"), null);
  assert.equal(storage.getItem("state"), null);
  assert.equal(storage.getItem("super_secret_code_123"), null);
  assert.deepEqual(Object.keys(storage.store), ["rag_access_token", "rag_refresh_token"]);
});
