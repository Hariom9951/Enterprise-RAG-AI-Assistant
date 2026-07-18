/**
 * Enterprise RAG AI Assistant — Agent API Client
 * ================================================
 * Typed client for the Phase 11 Agent endpoints.
 */

import { getAccessToken } from "@/lib/auth";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// =============================================================================
// Type Definitions
// =============================================================================

export interface AgentToolCallResponse {
  tool_id: string;
  tool_name: string;
  parameters: Record<string, unknown> | null;
  success: boolean;
  latency_ms: number;
  retries: number;
  error: string | null;
  result_summary: string | null;
}

export interface AgentChatResponse {
  run_id: string;
  question: string;
  final_answer: string;
  tool_calls: AgentToolCallResponse[];
  total_tool_calls: number;
  total_latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  provider: string | null;
  model_name: string | null;
  success: boolean;
  error_message: string | null;
}

export interface ToolParameter {
  type: string;
  description: string;
  enum?: string[];
  minimum?: number;
  maximum?: number;
  default?: unknown;
}

export interface ToolListItem {
  id: string;
  name: string;
  description: string;
  permission_level: string;
  parameters: {
    type: string;
    properties: Record<string, ToolParameter>;
    required: string[];
  };
}

export interface ToolListResponse {
  tools: ToolListItem[];
  total: number;
}

export interface ToolTestResponse {
  tool_id: string;
  success: boolean;
  output: unknown;
  metadata: Record<string, unknown>;
  latency_ms: number;
  error: string | null;
}

export interface ToolStatItem {
  tool_id: string;
  tool_name: string;
  total_calls: number;
  successful_calls: number;
  failed_calls: number;
  avg_latency_ms: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
}

export interface AgentStatisticsResponse {
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  total_tool_calls: number;
  avg_tools_per_run: number;
  avg_run_latency_ms: number;
  avg_prompt_tokens: number;
  avg_completion_tokens: number;
  tool_stats: ToolStatItem[];
  period_days: number;
}

export interface AgentChatRequest {
  question: string;
  session_id?: string;
  provider?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  top_k?: number;
  threshold?: number;
}

// =============================================================================
// HTTP Helper
// =============================================================================

async function agentFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAccessToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string>),
  };

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Agent API ${res.status}: ${body}`);
  }

  return res.json() as Promise<T>;
}

// =============================================================================
// Agent API Functions
// =============================================================================

/** Run the agent on a question. */
export async function agentChat(
  request: AgentChatRequest
): Promise<AgentChatResponse> {
  return agentFetch<AgentChatResponse>("/agent/chat", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

/** List all registered agent tools visible to the current user. */
export async function listAgentTools(): Promise<ToolListResponse> {
  return agentFetch<ToolListResponse>("/agent/tools");
}

/** Test a specific tool with given parameters. */
export async function testAgentTool(
  toolId: string,
  parameters: Record<string, unknown>
): Promise<ToolTestResponse> {
  return agentFetch<ToolTestResponse>("/agent/tools/test", {
    method: "POST",
    body: JSON.stringify({ tool_id: toolId, parameters }),
  });
}

/** Retrieve agent run statistics for the current user. */
export async function getAgentStatistics(
  periodDays: number = 30
): Promise<AgentStatisticsResponse> {
  return agentFetch<AgentStatisticsResponse>(
    `/agent/statistics?period_days=${periodDays}`
  );
}
