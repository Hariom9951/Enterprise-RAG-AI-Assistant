"use client";

/**
 * Enterprise RAG AI Assistant — Agent Execution Timeline
 * =======================================================
 * Displays each tool call as a step in the agent's execution trace.
 */

import type { AgentToolCallResponse } from "@/lib/agentApi";

interface AgentTimelineProps {
  toolCalls: AgentToolCallResponse[];
  totalLatencyMs: number;
  isLoading?: boolean;
}

const TOOL_ICONS: Record<string, string> = {
  semantic_search: "🔍",
  document_lookup: "📄",
  citation: "📝",
  conversation_history: "💬",
};

const TOOL_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  semantic_search: {
    bg: "rgba(99,102,241,0.12)",
    border: "rgba(99,102,241,0.35)",
    text: "#a5b4fc",
  },
  document_lookup: {
    bg: "rgba(16,185,129,0.12)",
    border: "rgba(16,185,129,0.35)",
    text: "#6ee7b7",
  },
  citation: {
    bg: "rgba(245,158,11,0.12)",
    border: "rgba(245,158,11,0.35)",
    text: "#fcd34d",
  },
  conversation_history: {
    bg: "rgba(236,72,153,0.12)",
    border: "rgba(236,72,153,0.35)",
    text: "#f9a8d4",
  },
};

function LatencyBar({
  latencyMs,
  maxMs,
}: {
  latencyMs: number;
  maxMs: number;
}) {
  const pct = maxMs > 0 ? Math.min((latencyMs / maxMs) * 100, 100) : 0;
  return (
    <div
      style={{
        height: "4px",
        background: "rgba(255,255,255,0.08)",
        borderRadius: "2px",
        marginTop: "6px",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          height: "100%",
          width: `${pct}%`,
          background:
            "linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%)",
          borderRadius: "2px",
          transition: "width 0.6s ease",
        }}
      />
    </div>
  );
}

export default function AgentTimeline({
  toolCalls,
  totalLatencyMs,
  isLoading = false,
}: AgentTimelineProps) {
  const maxLatency = Math.max(...toolCalls.map((t) => t.latency_ms), 1);

  if (isLoading) {
    return (
      <div style={{ padding: "16px 0" }}>
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            style={{
              display: "flex",
              gap: "12px",
              marginBottom: "12px",
              animation: "pulse 1.5s ease-in-out infinite",
              animationDelay: `${i * 0.2}s`,
            }}
          >
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "50%",
                background: "rgba(255,255,255,0.06)",
                flexShrink: 0,
              }}
            />
            <div style={{ flex: 1 }}>
              <div
                style={{
                  height: "12px",
                  borderRadius: "6px",
                  background: "rgba(255,255,255,0.06)",
                  marginBottom: "8px",
                  width: "60%",
                }}
              />
              <div
                style={{
                  height: "8px",
                  borderRadius: "4px",
                  background: "rgba(255,255,255,0.04)",
                  width: "40%",
                }}
              />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (toolCalls.length === 0) {
    return (
      <div
        style={{
          textAlign: "center",
          color: "rgba(255,255,255,0.3)",
          padding: "24px 0",
          fontSize: "14px",
        }}
      >
        No tool calls in this run
      </div>
    );
  }

  return (
    <div style={{ position: "relative" }}>
      {/* Vertical line */}
      <div
        style={{
          position: "absolute",
          left: "17px",
          top: "18px",
          bottom: "18px",
          width: "2px",
          background:
            "linear-gradient(180deg, rgba(99,102,241,0.6) 0%, rgba(139,92,246,0.2) 100%)",
          borderRadius: "1px",
        }}
      />

      {toolCalls.map((call, idx) => {
        const colors = TOOL_COLORS[call.tool_id] ?? {
          bg: "rgba(255,255,255,0.06)",
          border: "rgba(255,255,255,0.12)",
          text: "#e2e8f0",
        };
        const icon = TOOL_ICONS[call.tool_id] ?? "🔧";

        return (
          <div
            key={idx}
            style={{
              display: "flex",
              gap: "14px",
              marginBottom: "14px",
              position: "relative",
            }}
          >
            {/* Node */}
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "50%",
                background: colors.bg,
                border: `2px solid ${colors.border}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "16px",
                flexShrink: 0,
                zIndex: 1,
                position: "relative",
              }}
            >
              {icon}
            </div>

            {/* Content card */}
            <div
              style={{
                flex: 1,
                background: "rgba(255,255,255,0.04)",
                border: `1px solid ${colors.border}`,
                borderRadius: "10px",
                padding: "12px 14px",
                minWidth: 0,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "4px",
                  flexWrap: "wrap",
                  gap: "6px",
                }}
              >
                <span
                  style={{
                    fontSize: "13px",
                    fontWeight: 600,
                    color: colors.text,
                  }}
                >
                  {call.tool_name}
                </span>
                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  {call.retries > 0 && (
                    <span
                      style={{
                        fontSize: "11px",
                        color: "#fbbf24",
                        background: "rgba(251,191,36,0.12)",
                        border: "1px solid rgba(251,191,36,0.3)",
                        padding: "1px 6px",
                        borderRadius: "4px",
                      }}
                    >
                      {call.retries} retr{call.retries === 1 ? "y" : "ies"}
                    </span>
                  )}
                  <span
                    style={{
                      fontSize: "11px",
                      padding: "2px 8px",
                      borderRadius: "12px",
                      background: call.success
                        ? "rgba(16,185,129,0.15)"
                        : "rgba(239,68,68,0.15)",
                      color: call.success ? "#6ee7b7" : "#fca5a5",
                      border: `1px solid ${call.success ? "rgba(16,185,129,0.3)" : "rgba(239,68,68,0.3)"}`,
                    }}
                  >
                    {call.success ? "✓ success" : "✗ failed"}
                  </span>
                  <span
                    style={{
                      fontSize: "12px",
                      color: "rgba(255,255,255,0.4)",
                      fontFamily: "monospace",
                    }}
                  >
                    {call.latency_ms}ms
                  </span>
                </div>
              </div>

              {call.result_summary && (
                <p
                  style={{
                    fontSize: "12px",
                    color: "rgba(255,255,255,0.5)",
                    margin: 0,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {call.result_summary}
                </p>
              )}

              {call.error && (
                <p
                  style={{
                    fontSize: "12px",
                    color: "#fca5a5",
                    margin: "4px 0 0",
                  }}
                >
                  ⚠ {call.error}
                </p>
              )}

              <LatencyBar latencyMs={call.latency_ms} maxMs={maxLatency} />
            </div>
          </div>
        );
      })}

      {/* Summary footer */}
      <div
        style={{
          display: "flex",
          gap: "16px",
          marginTop: "8px",
          padding: "10px 14px",
          background: "rgba(255,255,255,0.03)",
          borderRadius: "8px",
          border: "1px solid rgba(255,255,255,0.06)",
          fontSize: "12px",
          color: "rgba(255,255,255,0.5)",
          flexWrap: "wrap",
        }}
      >
        <span>
          🔧 <b style={{ color: "rgba(255,255,255,0.75)" }}>{toolCalls.length}</b> tool
          {toolCalls.length !== 1 ? "s" : ""}
        </span>
        <span>
          ✓{" "}
          <b style={{ color: "#6ee7b7" }}>
            {toolCalls.filter((t) => t.success).length}
          </b>{" "}
          succeeded
        </span>
        {toolCalls.some((t) => !t.success) && (
          <span>
            ✗{" "}
            <b style={{ color: "#fca5a5" }}>
              {toolCalls.filter((t) => !t.success).length}
            </b>{" "}
            failed
          </span>
        )}
        <span>
          ⏱ <b style={{ color: "rgba(255,255,255,0.75)" }}>{totalLatencyMs}ms</b>{" "}
          total
        </span>
      </div>
    </div>
  );
}
