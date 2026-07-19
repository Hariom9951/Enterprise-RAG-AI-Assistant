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
  role: "USER" | "ADMIN";
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

export interface ChunkResponse {
  id: string;
  document_id: string;
  chunk_index: number;
  text: string;
  token_count: number;
  character_count: number;
  word_count: number;
  reading_time_estimate: number;
  page_number: number;
  section_title: string | null;
  heading_level: number | null;
  language: string;
  metadata: Record<string, unknown>;
  sha256_hash: string;
  version: string;
  created_at: string;
  updated_at: string;
}

export interface ChunkSummaryResponse {
  total_chunks: number;
  total_tokens: number;
  average_chunk_size: number;
  min_chunk_size: number;
  max_chunk_size: number;
  reading_time_estimate: number;
  languages: string[];
}

export interface ChunkEmbeddingResponse {
  id: string;
  embedding: number[] | null;
}

export interface DocumentEmbeddingStatusResponse {
  document_id: string;
  status: string;
  percentage_complete: number;
  processed_chunks: number;
  remaining_chunks: number;
  model_used: string;
  vector_dimension: number;
  processing_time_ms: number;
  error_message: string | null;
}

export interface DocumentEmbeddingSummaryResponse {
  document_id: string;
  total_embedded: number;
  vector_dimension: number;
  model_used: string;
  version: string;
  total_duration_ms: number;
}

export interface SearchFilters {
  document_ids?: string[];
  languages?: string[];
  start_date?: string;
  end_date?: string;
  metadata?: Record<string, unknown>;
}

export interface SearchRequest {
  query: string;
  top_k?: number;
  offset?: number;
  threshold?: number;
  search_type?: string;
  filters?: SearchFilters;
}

export interface SearchResultItem {
  chunk: ChunkResponse;
  document: DocumentResponse;
  score: number;
}

export interface SearchQueryResponse {
  id: string;
  query_text: string;
  search_type: string;
  top_k: number;
  similarity_threshold: number;
  total_results: number;
  response_time_ms: number;
  created_at: string;
}

export interface SearchStatisticsResponse {
  total_queries: number;
  average_latency_ms: number;
  search_type_distribution: Record<string, number>;
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

  /** Get paginated document chunks. */
  getChunks: (
    id: string,
    params: { limit?: number; offset?: number; search?: string } = {}
  ): Promise<ChunkResponse[]> => {
    const query = new URLSearchParams();
    if (params.limit !== undefined) query.append("limit", params.limit.toString());
    if (params.offset !== undefined) query.append("offset", params.offset.toString());
    if (params.search !== undefined) query.append("search", params.search);

    const queryString = query.toString();
    return request<ChunkResponse[]>(`/documents/${id}/chunks${queryString ? `?${queryString}` : ""}`);
  },

  /** Get summary of chunks for a document. */
  getChunkSummary: (id: string): Promise<ChunkSummaryResponse> =>
    request<ChunkSummaryResponse>(`/documents/${id}/chunk-summary`),

  /** Trigger vector embedding generation in the background. */
  embed: (id: string): Promise<{ message: string }> =>
    request<{ message: string }>(`/documents/${id}/embed`, {
      method: "POST",
    }),

  /** Get background embedding progress status. */
  getEmbeddingStatus: (id: string): Promise<DocumentEmbeddingStatusResponse> =>
    request<DocumentEmbeddingStatusResponse>(`/documents/${id}/embedding-status`),

  /** Get database embedding statistical summary. */
  getEmbeddingSummary: (id: string): Promise<DocumentEmbeddingSummaryResponse> =>
    request<DocumentEmbeddingSummaryResponse>(`/documents/${id}/embedding-summary`),

  /** Execute hybrid search scoped to a specific document. */
  search: (id: string, params: SearchRequest): Promise<SearchResultItem[]> =>
    request<SearchResultItem[]>(`/documents/${id}/search`, {
      method: "POST",
      body: JSON.stringify(params),
    }),
};

// =============================================================================
// Chunks API
// =============================================================================

export const chunksApi = {
  /** Get single chunk details. */
  get: (id: string): Promise<ChunkResponse> =>
    request<ChunkResponse>(`/chunks/${id}`),

  /** Delete a single chunk. */
  delete: (id: string): Promise<void> =>
    request<void>(`/chunks/${id}`, {
      method: "DELETE",
    }),

  /** Retrieve raw float vector array elements of a chunk. */
  getEmbedding: (id: string): Promise<ChunkEmbeddingResponse> =>
    request<ChunkEmbeddingResponse>(`/chunks/${id}/embedding`),
};

// =============================================================================
// Search API
// =============================================================================

export const searchApi = {
  /** Execute global hybrid search. */
  search: (params: SearchRequest): Promise<SearchResultItem[]> =>
    request<SearchResultItem[]>("/search", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  /** Retrieve user search query logs. */
  getHistory: (): Promise<SearchQueryResponse[]> =>
    request<SearchQueryResponse[]>("/search/history"),

  /** Retrieve user search statistics. */
  getStatistics: (): Promise<SearchStatisticsResponse> =>
    request<SearchStatisticsResponse>("/search/statistics"),
};

// =============================================================================
// RAG API
// =============================================================================

export interface RAGQueryRequest {
  question: string;
  top_k?: number;
  threshold?: number;
  filters?: SearchFilters;
  use_reranker?: boolean;
  provider?: string;
  model?: string;
}

export interface CitationItem {
  citation_index: number;
  chunk_id: string;
  document_id: string;
  document_title: string;
  page_number: number;
  section_title: string | null;
  text: string;
  score: number;
}

export interface RAGChunkItem {
  chunk_id: string;
  text: string;
  page_number: number;
  section_title: string | null;
  document_id: string;
  document_title: string;
  score: number;
}

export interface RAGLatencyInfo {
  total_ms: number;
  retrieval_ms: number;
  llm_ms: number;
}

export interface RAGTokenUsageInfo {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface RAGQueryResponse {
  answer: string;
  citations: CitationItem[];
  retrieved_chunks: RAGChunkItem[];
  confidence_score: number;
  latency: RAGLatencyInfo;
  tokens_used: RAGTokenUsageInfo;
  model_name: string;
  provider: string;
}

export interface RAGStatisticsResponse {
  total_queries: number;
  average_latency_ms: number;
  total_tokens_used: number;
  provider_distribution: Record<string, number>;
}

export interface RAGModelItem {
  provider: string;
  model_name: string;
  is_default: boolean;
}

export const ragApi = {
  /** Execute global RAG query. */
  query: (params: RAGQueryRequest): Promise<RAGQueryResponse> =>
    request<RAGQueryResponse>("/rag/query", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  /** Execute document-scoped RAG query. */
  queryDocument: (documentId: string, params: RAGQueryRequest): Promise<RAGQueryResponse> =>
    request<RAGQueryResponse>(`/rag/query/document/${documentId}`, {
      method: "POST",
      body: JSON.stringify(params),
    }),

  /** List available LLM models. */
  getModels: (): Promise<RAGModelItem[]> =>
    request<RAGModelItem[]>("/rag/models"),

  /** Get user RAG statistics. */
  getStatistics: (): Promise<RAGStatisticsResponse> =>
    request<RAGStatisticsResponse>("/rag/statistics"),
};

// =============================================================================
// Chat API (Phase 10)
// =============================================================================

export interface ChatSessionResponse {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessageResponse {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations?: CitationItem[];
  tokens?: RAGTokenUsageInfo;
  latency?: RAGLatencyInfo;
  created_at: string;
}

export interface ChatSessionDetailResponse {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessageResponse[];
}

export interface ChatMessageRequest {
  question: string;
  provider?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  use_reranker?: boolean;
  threshold?: number;
  top_k?: number;
}

export const chatApi = {
  /** Create a new chat session */
  createSession: (title?: string): Promise<ChatSessionResponse> =>
    request<ChatSessionResponse>("/chat/session", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),

  /** List all conversations for current user */
  listSessions: (): Promise<ChatSessionResponse[]> =>
    request<ChatSessionResponse[]>("/chat/sessions"),

  /** Get a session detail with full message thread */
  getSession: (sessionId: string): Promise<ChatSessionDetailResponse> =>
    request<ChatSessionDetailResponse>(`/chat/session/${sessionId}`),

  /** Rename conversation thread */
  renameSession: (sessionId: string, title: string): Promise<ChatSessionResponse> =>
    request<ChatSessionResponse>(`/chat/session/${sessionId}`, {
      method: "PUT",
      body: JSON.stringify({ title }),
    }),

  /** Delete conversation and its messages */
  deleteSession: (sessionId: string): Promise<void> =>
    request<void>(`/chat/session/${sessionId}`, {
      method: "DELETE",
    }),

  /** Send message stream - returns raw HTTP response to iterate over readable stream */
  sendMessageStream: async (sessionId: string, payload: ChatMessageRequest): Promise<Response> => {
    const token = getAccessToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return fetch(`${API_BASE}/chat/session/${sessionId}/message`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
  },
};

// =============================================================================
// Dashboard API (Phase 12)
// =============================================================================

export interface RecentUploadItem {
  id: string;
  original_filename: string;
  file_size: number;
  processing_status: string;
  created_at: string;
}

export interface RecentConversationItem {
  id: string;
  title: string;
  updated_at: string;
}

export interface RecentSearchItem {
  id: string;
  query_text: string;
  search_type: string;
  total_results: number;
  created_at: string;
}

export interface RecentAgentRunItem {
  id: string;
  question: string;
  success: boolean;
  total_latency_ms: number;
  created_at: string;
}

export interface DashboardData {
  total_documents: number;
  total_chunks: number;
  total_embeddings: number;
  total_conversations: number;
  todays_queries: number;
  average_latency_ms: number;
  average_similarity: number;
  most_used_llm: string;
  storage_usage_bytes: number;
  recent_uploads: RecentUploadItem[];
  recent_conversations: RecentConversationItem[];
  recent_searches: RecentSearchItem[];
  recent_agent_runs: RecentAgentRunItem[];
}

export const dashboardApi = {
  /** Get workspace aggregates and activity lists */
  getStatistics: (): Promise<DashboardData> =>
    request<DashboardData>("/dashboard/statistics"),
};


