/**
 * Enterprise RAG AI Assistant — Agent Dashboard
 * ===============================================
 * Phase 11: Enterprise AI Agent interface with tool execution timeline,
 * chunk viewer, and real-time observability.
 *
 * Features:
 * - Question input with provider/model override
 * - Tool selection and execution timeline
 * - Retrieved chunks with confidence scores
 * - Token usage and latency meters
 * - Agent statistics panel
 */

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI Agent",
  description:
    "Enterprise AI Agent — tool-augmented question answering with full execution traceability.",
};

export default function AgentPage() {
  return <AgentDashboard />;
}

// =============================================================================
// Client Component (wraps all interactive logic)
// =============================================================================

import AgentDashboardClient from "./AgentDashboardClient";

function AgentDashboard() {
  return <AgentDashboardClient />;
}
