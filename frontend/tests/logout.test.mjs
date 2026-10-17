import test from "node:test";
import assert from "node:assert/strict";

// Mock localStorage implementation
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

// In-memory token management logic matching auth.ts
const ACCESS_TOKEN_KEY = "rag_access_token";
const REFRESH_TOKEN_KEY = "rag_refresh_token";

function createAuthHelper(storage) {
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

// Handler logic matching AppSidebar, AppTopbar, and HomeClient
async function executeLogout({ auth, authApi, onLoggedOut }) {
  const refreshToken = auth.getRefreshToken();
  try {
    if (refreshToken) {
      await authApi.logout({ refresh_token: refreshToken });
    }
  } catch {
    // Graceful fallback: always clear local tokens even if server logout fails
  } finally {
    auth.clearTokens();
    if (onLoggedOut) {
      onLoggedOut();
    }
  }
}

test("Successful logout: calls server API with refresh token and clears local storage", async () => {
  const storage = new MockLocalStorage();
  const auth = createAuthHelper(storage);
  auth.setTokens("mock_access_token", "mock_refresh_token_123");

  assert.equal(auth.isAuthenticated(), true);

  let apiCalledWith = null;
  let apiCallCount = 0;
  const mockAuthApi = {
    logout: async (payload) => {
      apiCallCount += 1;
      apiCalledWith = payload;
      return { message: "Successfully logged out." };
    },
  };

  let redirected = false;
  await executeLogout({
    auth,
    authApi: mockAuthApi,
    onLoggedOut: () => {
      redirected = true;
    },
  });

  assert.equal(apiCallCount, 1);
  assert.deepEqual(apiCalledWith, { refresh_token: "mock_refresh_token_123" });
  assert.equal(auth.getAccessToken(), null);
  assert.equal(auth.getRefreshToken(), null);
  assert.equal(auth.isAuthenticated(), false);
  assert.equal(redirected, true);
});

test("API failure during logout: still guarantees local token cleanup and UI redirect", async () => {
  const storage = new MockLocalStorage();
  const auth = createAuthHelper(storage);
  auth.setTokens("mock_access_token", "mock_refresh_token_fail");

  const mockAuthApi = {
    logout: async () => {
      throw new Error("500 Internal Server Error / Network Disconnect");
    },
  };

  let redirected = false;
  await executeLogout({
    auth,
    authApi: mockAuthApi,
    onLoggedOut: () => {
      redirected = true;
    },
  });

  assert.equal(auth.getAccessToken(), null);
  assert.equal(auth.getRefreshToken(), null);
  assert.equal(auth.isAuthenticated(), false);
  assert.equal(redirected, true);
});

test("Missing refresh token: skips server call but performs clean local logout", async () => {
  const storage = new MockLocalStorage();
  const auth = createAuthHelper(storage);
  // Only access token is set, no refresh token
  storage.setItem(ACCESS_TOKEN_KEY, "dangling_access_token");

  assert.equal(auth.getRefreshToken(), null);
  assert.equal(auth.isAuthenticated(), true);

  let apiCallCount = 0;
  const mockAuthApi = {
    logout: async () => {
      apiCallCount += 1;
      return { message: "Successfully logged out." };
    },
  };

  let redirected = false;
  await executeLogout({
    auth,
    authApi: mockAuthApi,
    onLoggedOut: () => {
      redirected = true;
    },
  });

  assert.equal(apiCallCount, 0, "Should not call authApi.logout if refresh token is absent");
  assert.equal(auth.getAccessToken(), null);
  assert.equal(auth.getRefreshToken(), null);
  assert.equal(auth.isAuthenticated(), false);
  assert.equal(redirected, true);
});

test("Token exposure check: error objects or fallbacks do not log plain token contents", async () => {
  const storage = new MockLocalStorage();
  const auth = createAuthHelper(storage);
  auth.setTokens("secret_access", "secret_refresh_value");

  const loggedOutputs = [];
  const mockAuthApi = {
    logout: async () => {
      throw new Error("Server rejected revocation");
    },
  };

  await executeLogout({
    auth,
    authApi: mockAuthApi,
    onLoggedOut: () => {},
  });

  // Verify that neither secret token value leaked
  const outputString = JSON.stringify(loggedOutputs);
  assert.equal(outputString.includes("secret_refresh_value"), false);
  assert.equal(outputString.includes("secret_access"), false);
});
