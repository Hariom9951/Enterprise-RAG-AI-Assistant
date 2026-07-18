/**
 * Enterprise RAG AI Assistant — Typed API Client
 * ===============================================
 * Centralised HTTP client that automatically injects the JWT
 * Authorization header and handles token expiry.
 */

import { clearTokens, getAccessToken } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// =============================================================================
// Response Types
// =============================================================================

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserResponse {
  id: string;
  full_name: string;
  email: string;
  role: "user" | "admin";
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
}

export interface DocumentResponse {
  id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  processing_status: string;
  created_at: string;
  updated_at: string;
}

export interface ProcessedDocumentResponse {
  id: string;
  document_id: string;
  raw_text: string;
  clean_text: string;
  language: string;
  page_count: number;
  word_count: number;
  character_count: number;
  processing_time: number;
  preview: string;
  is_truncated: boolean;
  created_at: string;
  updated_at: string;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    detail: unknown;
  };
}

// =============================================================================
// Request Helpers
// =============================================================================

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAccessToken();
  const headers: Record<string, string> = {
    ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    // Token expired — clear and redirect to login.
    clearTokens();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }

  // Handle empty or 204 No Content responses gracefully
  if (response.status === 204) {
    return {} as T;
  }

  const data = await response.json();

  if (!response.ok) {
    throw data as ApiError;
  }

  return data as T;
}

// =============================================================================
// Auth API
// =============================================================================

export const authApi = {
  /** Register a new user account. */
  register: (payload: {
    full_name: string;
    email: string;
    password: string;
  }): Promise<UserResponse> =>
    request<UserResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  /** Login and receive a JWT token pair. */
  login: (payload: { email: string; password: string }): Promise<TokenResponse> =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  /** Exchange a refresh token for a new access token. */
  refresh: (refreshToken: string): Promise<TokenResponse> =>
    request<TokenResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    }),
};

// =============================================================================
// User API
// =============================================================================

export const userApi = {
  /** Fetch the authenticated user's profile. */
  me: (): Promise<UserResponse> => request<UserResponse>("/users/me"),
};

// =============================================================================
// Document API
// =============================================================================

export const documentsApi = {
  /** Upload a document to the knowledge base. */
  upload: (file: File): Promise<DocumentResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    return request<DocumentResponse>("/documents/upload", {
      method: "POST",
      body: formData,
    });
  },

  /** List user documents with query parameters. */
  list: (params: {
    limit?: number;
    offset?: number;
    search?: string;
  } = {}): Promise<DocumentResponse[]> => {
    const query = new URLSearchParams();
    if (params.limit !== undefined) query.append("limit", params.limit.toString());
    if (params.offset !== undefined) query.append("offset", params.offset.toString());
    if (params.search !== undefined) query.append("search", params.search);
    
    const queryString = query.toString();
    return request<DocumentResponse[]>(`/documents${queryString ? `?${queryString}` : ""}`);
  },

  /** Get document details. */
  get: (id: string): Promise<DocumentResponse> =>
    request<DocumentResponse>(`/documents/${id}`),

  /** Rename document. */
  rename: (id: string, originalFilename: string): Promise<DocumentResponse> =>
    request<DocumentResponse>(`/documents/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ original_filename: originalFilename }),
    }),

  /** Delete document. */
  delete: (id: string): Promise<void> =>
    request<void>(`/documents/${id}`, {
      method: "DELETE",
    }),

  /** Get document status. */
  status: (id: string): Promise<{ id: string; status: string }> =>
    request<{ id: string; status: string }>(`/documents/${id}/status`),

  /** Get extracted document text and statistics. Returns null if 202 (still processing). */
  getText: async (id: string): Promise<ProcessedDocumentResponse | null> => {
    const token = getAccessToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const response = await fetch(`${API_BASE}/documents/${id}/text`, { headers });
    if (response.status === 202) return null;  // still processing
    if (!response.ok) throw await response.json();
    return response.json() as Promise<ProcessedDocumentResponse>;
  },
};
