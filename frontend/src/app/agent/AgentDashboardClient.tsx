"use client";

/**
 * Enterprise RAG AI Assistant — Agent Dashboard (Client Component)
 * =================================================================
 * Interactive agent UI with question submission, execution timeline,
 * chunk viewer, and observability panels.
 */

import { useState, useRef, useEffect } from "react";
import AgentTimeline from "@/components/AgentTimeline";
import AgentChunkCard from "@/components/AgentChunkCard";
import {
  agentChat,
  listAgentTools,
  getAgentStatistics,
  type AgentChatResponse,
  type ToolListItem,
  type AgentStatisticsResponse,
  type AgentToolCallResponse,
} from "@/lib/agentApi";
import Navigation from "@/components/Navigation";

// =============================================================================
// Types
// =============================================================================

interface ChunkResult {
  chunk_id: string;
  document_id: string;
  document_name: string;
  page_number: number | null;
  section_title: string | null;
  text: string;
  score: number;
  language?: string;
  chunk_index?: number;
}

// =============================================================================
// Sub-components
// =============================================================================

function MetricCard({
  label,
  value,
  sub,
  icon,
  accent = "#6366f1",
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: string;
  accent?: string;
}) {
  return (
    <div
      style={{
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.09)",
        borderRadius: "12px",
        padding: "14px 16px",
        flex: "1 1 140px",
        minWidth: "120px",
      }}
    >
      <div style={{ fontSize: "20px", marginBottom: "6px" }}>{icon}</div>
      <div
        style={{
          fontSize: "22px",
          fontWeight: 700,
          color: accent,
          lineHeight: 1,
          marginBottom: "4px",
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: "12px", color: "rgba(255,255,255,0.5)" }}>
        {label}
      </div>
      {sub && (
        <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.3)", marginTop: "2px" }}>
          {sub}
        </div>
      )}
    </div>
  );
}

function ToolBadge({ tool }: { tool: ToolListItem }) {
  const ICONS: Record<string, string> = {
    semantic_search: "🔍",
    document_lookup: "📄",
    citation: "📝",
    conversation_history: "💬",
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "8px",
        padding: "8px 12px",
        background: "rgba(99,102,241,0.08)",
        border: "1px solid rgba(99,102,241,0.2)",
        borderRadius: "8px",
        cursor: "default",
        transition: "background 0.2s",
      }}
      onMouseEnter={(e) =>
        ((e.currentTarget as HTMLDivElement).style.background =
          "rgba(99,102,241,0.16)")
      }
      onMouseLeave={(e) =>
        ((e.currentTarget as HTMLDivElement).style.background =
          "rgba(99,102,241,0.08)")
      }
      title={tool.description}
    >
      <span style={{ fontSize: "16px" }}>{ICONS[tool.id] ?? "🔧"}</span>
      <div>
        <div style={{ fontSize: "12px", fontWeight: 600, color: "#e2e8f0" }}>
          {tool.name}
        </div>
        <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.4)" }}>
          {tool.id}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Main Dashboard
// =============================================================================

export default function AgentDashboardClient() {
  const [question, setQuestion] = useState("");
  const [provider, setProvider] = useState("gemini");
  const [topK, setTopK] = useState(5);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<AgentChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tools, setTools] = useState<ToolListItem[]>([]);
  const [stats, setStats] = useState<AgentStatisticsResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"answer" | "trace" | "chunks" | "stats">("answer");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    listAgentTools()
      .then((res) => setTools(res.tools))
      .catch(() => {});
    getAgentStatistics()
      .then(setStats)
      .catch(() => {});
  }, []);

  const handleSubmit = async () => {
    if (!question.trim() || isLoading) return;
    setIsLoading(true);
    setError(null);
    setResult(null);
    setActiveTab("answer");

    try {
      const res = await agentChat({
        question: question.trim(),
        provider,
        top_k: topK,
      });
      setResult(res);
      // Auto-switch to trace if there are tool calls
      if (res.tool_calls.length > 0) {
        setActiveTab("trace");
      }
      // Refresh stats
      getAgentStatistics().then(setStats).catch(() => {});
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Agent request failed.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      handleSubmit();
    }
  };

  // Extract chunks from semantic_search tool calls
  const chunks: ChunkResult[] = [];
  if (result) {
    for (const call of result.tool_calls) {
      if (call.tool_id === "semantic_search" && call.result_summary) {
        // We can't get the full chunks from result_summary alone,
        // but we show what's available from the summary
      }
    }
  }

  const tabs = [
    { id: "answer", label: "Answer", icon: "💡" },
    { id: "trace", label: `Trace (${result?.tool_calls.length ?? 0})`, icon: "🔧" },
    { id: "stats", label: "Statistics", icon: "📊" },
  ] as const;

  return (
    <div
      className="pl-0 md:pl-64"
      style={{
        minHeight: "100vh",
        background: "linear-gradient(135deg, #0f0f1a 0%, #1a1b2e 50%, #12121f 100%)",
        fontFamily: "'Inter', -apple-system, sans-serif",
        color: "#e2e8f0",
      }}
    >
      <Navigation />
      {/* Header */}
      <div
        style={{
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          padding: "16px 24px",
          display: "flex",
          alignItems: "center",
          gap: "12px",
          background: "rgba(0,0,0,0.3)",
          backdropFilter: "blur(10px)",
          position: "sticky",
          top: 0,
          zIndex: 10,
        }}
      >
        <div
          style={{
            width: "36px",
            height: "36px",
            borderRadius: "10px",
            background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "18px",
          }}
        >
          🤖
        </div>
        <div>
          <h1
            style={{ fontSize: "18px", fontWeight: 700, margin: 0, color: "#f8fafc" }}
          >
            Enterprise AI Agent
          </h1>
          <p style={{ fontSize: "12px", color: "rgba(255,255,255,0.4)", margin: 0 }}>
            Tool-augmented question answering — Phase 11
          </p>
        </div>
        {result && (
          <div style={{ marginLeft: "auto", display: "flex", gap: "8px" }}>
            <span
              style={{
                fontSize: "12px",
                padding: "4px 10px",
                borderRadius: "8px",
                background: result.success
                  ? "rgba(16,185,129,0.15)"
                  : "rgba(239,68,68,0.15)",
                color: result.success ? "#6ee7b7" : "#fca5a5",
                border: `1px solid ${result.success ? "rgba(16,185,129,0.3)" : "rgba(239,68,68,0.3)"}`,
              }}
            >
              {result.success ? "✓ Run complete" : "✗ Run failed"}
            </span>
            <span
              style={{
                fontSize: "12px",
                padding: "4px 10px",
                borderRadius: "8px",
                background: "rgba(255,255,255,0.06)",
                color: "rgba(255,255,255,0.5)",
              }}
            >
              ⏱ {result.total_latency_ms}ms
            </span>
          </div>
        )}
      </div>

      <div
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          padding: "24px",
          display: "grid",
          gridTemplateColumns: "1fr 340px",
          gap: "24px",
          alignItems: "start",
        }}
      >
        {/* ── Left Column ─────────────────────────────────────────────────── */}
        <div>
          {/* Input Card */}
          <div
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.09)",
              borderRadius: "16px",
              padding: "20px",
              marginBottom: "20px",
            }}
          >
            <h2
              style={{
                fontSize: "15px",
                fontWeight: 600,
                color: "#f8fafc",
                margin: "0 0 14px",
              }}
            >
              Ask the Agent
            </h2>

            <textarea
              ref={textareaRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your documents… (Ctrl+Enter to submit)"
              rows={4}
              id="agent-question-input"
              style={{
                width: "100%",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.12)",
                borderRadius: "10px",
                padding: "12px 14px",
                color: "#e2e8f0",
                fontSize: "14px",
                resize: "vertical",
                outline: "none",
                boxSizing: "border-box",
                fontFamily: "inherit",
                lineHeight: 1.6,
                transition: "border-color 0.2s",
              }}
              onFocus={(e) =>
                (e.currentTarget.style.borderColor = "rgba(99,102,241,0.5)")
              }
              onBlur={(e) =>
                (e.currentTarget.style.borderColor = "rgba(255,255,255,0.12)")
              }
            />

            {/* Controls row */}
            <div
              style={{
                display: "flex",
                gap: "10px",
                marginTop: "12px",
                flexWrap: "wrap",
                alignItems: "center",
              }}
            >
              <div style={{ display: "flex", gap: "8px", flex: 1, flexWrap: "wrap" }}>
                <select
                  id="agent-provider-select"
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  style={{
                    background: "rgba(255,255,255,0.06)",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: "8px",
                    color: "#e2e8f0",
                    padding: "7px 10px",
                    fontSize: "13px",
                    cursor: "pointer",
                    outline: "none",
                  }}
                >
                  <option value="gemini">Gemini</option>
                  <option value="openai">OpenAI</option>
                  <option value="ollama">Ollama</option>
                </select>

                <select
                  id="agent-topk-select"
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                  style={{
                    background: "rgba(255,255,255,0.06)",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: "8px",
                    color: "#e2e8f0",
                    padding: "7px 10px",
                    fontSize: "13px",
                    cursor: "pointer",
                    outline: "none",
                  }}
                >
                  {[3, 5, 8, 10, 15].map((k) => (
                    <option key={k} value={k}>
                      Top {k}
                    </option>
                  ))}
                </select>
              </div>

              <button
                id="agent-submit-btn"
                onClick={handleSubmit}
                disabled={isLoading || !question.trim()}
                style={{
                  background:
                    isLoading || !question.trim()
                      ? "rgba(99,102,241,0.3)"
                      : "linear-gradient(135deg, #6366f1, #8b5cf6)",
                  border: "none",
                  borderRadius: "10px",
                  color: "#fff",
                  padding: "9px 20px",
                  fontSize: "14px",
                  fontWeight: 600,
                  cursor: isLoading || !question.trim() ? "not-allowed" : "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  transition: "opacity 0.2s",
                }}
              >
                {isLoading ? (
                  <>
                    <span
                      style={{
                        width: "14px",
                        height: "14px",
                        border: "2px solid rgba(255,255,255,0.3)",
                        borderTopColor: "#fff",
                        borderRadius: "50%",
                        display: "inline-block",
                        animation: "spin 0.8s linear infinite",
                      }}
                    />
                    Running…
                  </>
                ) : (
                  <>🚀 Run Agent</>
                )}
              </button>
            </div>

            {error && (
              <div
                style={{
                  marginTop: "12px",
                  padding: "10px 14px",
                  background: "rgba(239,68,68,0.12)",
                  border: "1px solid rgba(239,68,68,0.3)",
                  borderRadius: "8px",
                  fontSize: "13px",
                  color: "#fca5a5",
                }}
              >
                ⚠ {error}
              </div>
            )}
          </div>

          {/* Result Tabs */}
          {result && (
            <div
              style={{
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: "16px",
                overflow: "hidden",
              }}
            >
              {/* Tab bar */}
              <div
                style={{
                  display: "flex",
                  borderBottom: "1px solid rgba(255,255,255,0.07)",
                  background: "rgba(0,0,0,0.2)",
                }}
              >
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    id={`agent-tab-${tab.id}`}
                    onClick={() => setActiveTab(tab.id)}
                    style={{
                      padding: "12px 18px",
                      background: "transparent",
                      border: "none",
                      borderBottom:
                        activeTab === tab.id
                          ? "2px solid #6366f1"
                          : "2px solid transparent",
                      color:
                        activeTab === tab.id
                          ? "#a5b4fc"
                          : "rgba(255,255,255,0.45)",
                      fontSize: "13px",
                      fontWeight: activeTab === tab.id ? 600 : 400,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      transition: "all 0.15s",
                    }}
                  >
                    {tab.icon} {tab.label}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              <div style={{ padding: "20px" }}>
                {/* Answer tab */}
                {activeTab === "answer" && (
                  <div>
                    {/* Metrics row */}
                    <div
                      style={{
                        display: "flex",
                        gap: "10px",
                        marginBottom: "18px",
                        flexWrap: "wrap",
                      }}
                    >
                      <MetricCard
                        icon="🔧"
                        label="Tool calls"
                        value={result.total_tool_calls}
                        accent="#a5b4fc"
                      />
                      <MetricCard
                        icon="⏱"
                        label="Latency"
                        value={`${result.total_latency_ms}ms`}
                        accent="#6ee7b7"
                      />
                      <MetricCard
                        icon="📥"
                        label="Prompt tokens"
                        value={result.prompt_tokens}
                        accent="#fcd34d"
                      />
                      <MetricCard
                        icon="📤"
                        label="Output tokens"
                        value={result.completion_tokens}
                        accent="#f9a8d4"
                      />
                    </div>

                    {/* Final answer */}
                    <div
                      style={{
                        background: "rgba(99,102,241,0.06)",
                        border: "1px solid rgba(99,102,241,0.2)",
                        borderRadius: "12px",
                        padding: "18px 20px",
                      }}
                    >
                      <div
                        style={{
                          fontSize: "12px",
                          fontWeight: 600,
                          color: "#a5b4fc",
                          marginBottom: "10px",
                          textTransform: "uppercase",
                          letterSpacing: "0.06em",
                        }}
                      >
                        🤖 Agent Answer
                      </div>
                      <div
                        style={{
                          fontSize: "15px",
                          lineHeight: 1.8,
                          color: "#e2e8f0",
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        {result.final_answer}
                      </div>
                    </div>

                    {result.provider && (
                      <div
                        style={{
                          marginTop: "10px",
                          fontSize: "12px",
                          color: "rgba(255,255,255,0.3)",
                        }}
                      >
                        Run ID: {result.run_id} · Provider:{" "}
                        {result.provider}
                        {result.model_name ? ` / ${result.model_name}` : ""}
                      </div>
                    )}
                  </div>
                )}

                {/* Trace tab */}
                {activeTab === "trace" && (
                  <AgentTimeline
                    toolCalls={result.tool_calls}
                    totalLatencyMs={result.total_latency_ms}
                  />
                )}

                {/* Stats tab */}
                {activeTab === "stats" && stats && (
                  <div>
                    <div
                      style={{
                        display: "flex",
                        gap: "10px",
                        marginBottom: "18px",
                        flexWrap: "wrap",
                      }}
                    >
                      <MetricCard
                        icon="🏃"
                        label="Total runs"
                        value={stats.total_runs}
                        accent="#a5b4fc"
                      />
                      <MetricCard
                        icon="✅"
                        label="Successful"
                        value={stats.successful_runs}
                        accent="#6ee7b7"
                      />
                      <MetricCard
                        icon="🔧"
                        label="Tool calls"
                        value={stats.total_tool_calls}
                        accent="#fcd34d"
                      />
                      <MetricCard
                        icon="⏱"
                        label="Avg latency"
                        value={`${Math.round(stats.avg_run_latency_ms)}ms`}
                        accent="#f9a8d4"
                      />
                    </div>

                    {/* Tool stats table */}
                    {stats.tool_stats.length > 0 && (
                      <div
                        style={{
                          background: "rgba(255,255,255,0.03)",
                          border: "1px solid rgba(255,255,255,0.07)",
                          borderRadius: "10px",
                          overflow: "hidden",
                        }}
                      >
                        <table
                          style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}
                        >
                          <thead>
                            <tr
                              style={{
                                background: "rgba(255,255,255,0.04)",
                                borderBottom: "1px solid rgba(255,255,255,0.07)",
                              }}
                            >
                              {["Tool", "Calls", "Success", "Avg ms", "P95 ms"].map(
                                (h) => (
                                  <th
                                    key={h}
                                    style={{
                                      padding: "10px 12px",
                                      textAlign: "left",
                                      color: "rgba(255,255,255,0.5)",
                                      fontWeight: 600,
                                      fontSize: "12px",
                                    }}
                                  >
                                    {h}
                                  </th>
                                )
                              )}
                            </tr>
                          </thead>
                          <tbody>
                            {stats.tool_stats.map((t) => (
                              <tr
                                key={t.tool_id}
                                style={{
                                  borderBottom: "1px solid rgba(255,255,255,0.05)",
                                }}
                              >
                                <td style={{ padding: "10px 12px", color: "#e2e8f0" }}>
                                  {t.tool_name}
                                </td>
                                <td
                                  style={{
                                    padding: "10px 12px",
                                    color: "#a5b4fc",
                                    fontWeight: 600,
                                  }}
                                >
                                  {t.total_calls}
                                </td>
                                <td
                                  style={{
                                    padding: "10px 12px",
                                    color: "#6ee7b7",
                                  }}
                                >
                                  {t.successful_calls}
                                </td>
                                <td
                                  style={{
                                    padding: "10px 12px",
                                    color: "rgba(255,255,255,0.6)",
                                    fontFamily: "monospace",
                                  }}
                                >
                                  {Math.round(t.avg_latency_ms)}
                                </td>
                                <td
                                  style={{
                                    padding: "10px 12px",
                                    color: "rgba(255,255,255,0.4)",
                                    fontFamily: "monospace",
                                  }}
                                >
                                  {Math.round(t.p95_latency_ms)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {stats.tool_stats.length === 0 && (
                      <p
                        style={{
                          fontSize: "13px",
                          color: "rgba(255,255,255,0.3)",
                          textAlign: "center",
                          padding: "20px",
                        }}
                      >
                        No agent runs yet. Submit a question to get started.
                      </p>
                    )}
                  </div>
                )}
                {activeTab === "stats" && !stats && (
                  <p style={{ fontSize: "13px", color: "rgba(255,255,255,0.3)", textAlign: "center" }}>
                    Loading statistics…
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Empty state */}
          {!result && !isLoading && (
            <div
              style={{
                textAlign: "center",
                padding: "40px 20px",
                color: "rgba(255,255,255,0.25)",
              }}
            >
              <div style={{ fontSize: "48px", marginBottom: "12px" }}>🤖</div>
              <p style={{ fontSize: "15px", margin: "0 0 6px" }}>
                Ask the agent a question
              </p>
              <p style={{ fontSize: "13px", margin: 0 }}>
                The agent will automatically select the best tools to answer it.
              </p>
            </div>
          )}

          {/* Loading state */}
          {isLoading && (
            <div
              style={{
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: "16px",
                padding: "24px 20px",
              }}
            >
              <AgentTimeline toolCalls={[]} totalLatencyMs={0} isLoading />
            </div>
          )}
        </div>

        {/* ── Right Column ─────────────────────────────────────────────────── */}
        <div>
          {/* Registered Tools Panel */}
          <div
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.09)",
              borderRadius: "16px",
              padding: "18px",
              marginBottom: "18px",
            }}
          >
            <h3
              style={{
                fontSize: "14px",
                fontWeight: 600,
                color: "#f8fafc",
                margin: "0 0 12px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              🔧 Registered Tools
              <span
                style={{
                  fontSize: "11px",
                  background: "rgba(99,102,241,0.2)",
                  color: "#a5b4fc",
                  padding: "2px 7px",
                  borderRadius: "10px",
                  fontWeight: 600,
                }}
              >
                {tools.length}
              </span>
            </h3>

            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {tools.map((tool) => (
                <ToolBadge key={tool.id} tool={tool} />
              ))}
              {tools.length === 0 && (
                <p style={{ fontSize: "13px", color: "rgba(255,255,255,0.3)", margin: 0 }}>
                  Loading tools…
                </p>
              )}
            </div>
          </div>

          {/* Safety Info Panel */}
          <div
            style={{
              background: "rgba(16,185,129,0.06)",
              border: "1px solid rgba(16,185,129,0.2)",
              borderRadius: "16px",
              padding: "16px 18px",
              marginBottom: "18px",
            }}
          >
            <h3
              style={{
                fontSize: "13px",
                fontWeight: 600,
                color: "#6ee7b7",
                margin: "0 0 10px",
              }}
            >
              🛡 Safety Guardrails
            </h3>
            <ul
              style={{
                margin: 0,
                padding: "0 0 0 16px",
                fontSize: "12px",
                color: "rgba(255,255,255,0.5)",
                lineHeight: 1.8,
              }}
            >
              <li>Prompt injection detection</li>
              <li>Max 5 tool calls per run</li>
              <li>60-second budget cap</li>
              <li>User ownership enforcement</li>
              <li>No raw database access from LLM</li>
            </ul>
          </div>

          {/* Quick Stats */}
          {stats && (
            <div
              style={{
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.07)",
                borderRadius: "16px",
                padding: "16px 18px",
              }}
            >
              <h3
                style={{
                  fontSize: "13px",
                  fontWeight: 600,
                  color: "rgba(255,255,255,0.6)",
                  margin: "0 0 10px",
                }}
              >
                📊 Your Usage (30 days)
              </h3>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "8px",
                }}
              >
                {[
                  { label: "Runs", value: stats.total_runs },
                  { label: "Success rate", value: stats.total_runs > 0 ? `${Math.round((stats.successful_runs / stats.total_runs) * 100)}%` : "—" },
                  { label: "Total tool calls", value: stats.total_tool_calls },
                  { label: "Avg latency", value: `${Math.round(stats.avg_run_latency_ms)}ms` },
                ].map((item) => (
                  <div
                    key={item.label}
                    style={{
                      background: "rgba(255,255,255,0.04)",
                      borderRadius: "8px",
                      padding: "8px 10px",
                      textAlign: "center",
                    }}
                  >
                    <div
                      style={{ fontSize: "16px", fontWeight: 700, color: "#a5b4fc" }}
                    >
                      {item.value}
                    </div>
                    <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.35)" }}>
                      {item.label}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100% { opacity: 0.4; } 50% { opacity: 0.8; } }
        * { box-sizing: border-box; }
        select option { background: #1a1b2e; color: #e2e8f0; }
      `}</style>
    </div>
  );
}
