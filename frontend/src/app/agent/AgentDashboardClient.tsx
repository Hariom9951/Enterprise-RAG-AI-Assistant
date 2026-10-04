"use client";

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
} from "@/lib/agentApi";
import AppSidebar from "@/components/layout/AppSidebar";
import AppTopbar from "@/components/layout/AppTopbar";
import {
  Bot,
  Wrench,
  Shield,
  BarChart3,
  Send,
  Loader2,
  AlertCircle,
  CheckCircle,
  Sparkles
} from "lucide-react";

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

export default function AgentDashboardClient() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);

  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<AgentChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [tools, setTools] = useState<ToolListItem[]>([]);
  const [stats, setStats] = useState<AgentStatisticsResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"answer" | "timeline" | "chunks" | "raw">("answer");

  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let isMounted = true;
    listAgentTools()
      .then((res) => isMounted && setTools(res.tools))
      .catch(() => {});
    getAgentStatistics()
      .then((s) => isMounted && setStats(s))
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, []);

  const handleSubmit = async () => {
    if (!question.trim() || isLoading) return;
    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const resp = await agentChat({
        question: question.trim(),
        provider: "gemini",
        top_k: topK,
      });
      setResult(resp);
      setActiveTab("answer");
      getAgentStatistics().then((s) => setStats(s)).catch(() => {});
    } catch (err: unknown) {
      const e = err as { error?: { message?: string } };
      setError(e?.error?.message ?? "Agent execution failed. Please verify backend availability.");
    } finally {
      setIsLoading(false);
    }
  };

  const retrievedChunks: ChunkResult[] = [];

  const tabs = [
    { id: "answer" as const, label: "Answer", icon: "💬" },
    {
      id: "timeline" as const,
      label: `Timeline (${result?.total_tool_calls ?? 0})`,
      icon: "⚡",
    },
    {
      id: "chunks" as const,
      label: `Chunks (${retrievedChunks.length})`,
      icon: "📚",
    },
    { id: "raw" as const, label: "Trace JSON", icon: "🔍" },
  ];

  return (
    <div className="flex h-screen bg-[#F8FAFC] text-slate-800 overflow-hidden font-sans">
      {/* ── Left Sidebar (Dark Navy) ─────────────────────────────── */}
      <AppSidebar
        isMobileOpen={mobileSidebarOpen}
        onCloseMobile={() => setMobileSidebarOpen(false)}
      />

      {/* ── Main Layout ─────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col md:pl-64 h-full overflow-hidden">
        <AppTopbar onToggleMobileSidebar={() => setMobileSidebarOpen(true)} />

        <main className="flex-1 overflow-y-auto px-4 md:px-8 py-8 scrollbar-thin">
          <div className="max-w-6xl mx-auto space-y-6">
            
            {/* Header */}
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
                <Bot className="text-blue-600" size={24} />
                Autonomous AI Agent Workspace
              </h1>
              <p className="text-xs md:text-sm text-slate-500 mt-1">
                Tool-augmented reasoning powered by Google Gemini, pgvector retrieval, and automated citations.
              </p>
            </div>

            {/* Main 2-column Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Left Column (2 Cols): Query & Execution Tabs */}
              <div className="lg:col-span-2 space-y-6">
                
                {/* Query Composer Card */}
                <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                    <span className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                      Agent Goal / Query
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono">
                      Safe tool calling active
                    </span>
                  </div>

                  <textarea
                    ref={inputRef}
                    rows={3}
                    placeholder="Ask a complex question requiring document lookup, reasoning, and citation synthesis..."
                    value={question}
                    disabled={isLoading}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleSubmit();
                    }}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3.5 text-xs md:text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:border-blue-500 focus:bg-white focus:ring-1 focus:ring-blue-200 transition-all font-medium resize-none"
                  />

                  {/* Controls Row */}
                  <div className="flex items-center justify-between gap-3 pt-1 flex-wrap">
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1.5 text-xs font-semibold text-slate-700">
                        <Sparkles size={13} className="text-blue-600" />
                        <span>Google Gemini</span>
                      </div>

                      <select
                        value={topK}
                        onChange={(e) => setTopK(Number(e.target.value))}
                        className="bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1.5 text-xs font-semibold text-slate-700 focus:outline-none cursor-pointer"
                      >
                        {[3, 5, 8, 10].map((k) => (
                          <option key={k} value={k}>
                            Top {k} chunks
                          </option>
                        ))}
                      </select>
                    </div>

                    <button
                      onClick={handleSubmit}
                      disabled={isLoading || !question.trim()}
                      className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition-colors shadow-xs cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      {isLoading ? (
                        <>
                          <Loader2 size={14} className="animate-spin" />
                          <span>Reasoning…</span>
                        </>
                      ) : (
                        <>
                          <Send size={13} />
                          <span>Run Agent</span>
                        </>
                      )}
                    </button>
                  </div>

                  {error && (
                    <div className="bg-red-50 border border-red-200 rounded-xl p-3 flex items-start gap-2 text-xs text-red-800">
                      <AlertCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
                      <span>{error}</span>
                    </div>
                  )}
                </div>

                {/* Execution Results Card */}
                {result && (
                  <div className="bg-white border border-slate-200/90 rounded-2xl shadow-2xs overflow-hidden">
                    {/* Tab Navigation */}
                    <div className="flex items-center border-b border-slate-200 px-4 bg-slate-50/70">
                      {tabs.map((tab) => (
                        <button
                          key={tab.id}
                          onClick={() => setActiveTab(tab.id)}
                          className={`px-4 py-3 text-xs font-semibold border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer ${
                            activeTab === tab.id
                              ? "border-blue-600 text-blue-600 bg-white"
                              : "border-transparent text-slate-500 hover:text-slate-800"
                          }`}
                        >
                          <span>{tab.icon}</span>
                          <span>{tab.label}</span>
                        </button>
                      ))}
                    </div>

                    {/* Tab Content */}
                    <div className="p-5">
                      {/* Answer Tab */}
                      {activeTab === "answer" && (
                        <div className="space-y-4">
                          {/* Metrics Header */}
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                            <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl text-center">
                              <span className="text-[10px] text-slate-500 uppercase font-bold block">
                                Tool Calls
                              </span>
                              <span className="text-base font-bold text-slate-900 block mt-0.5">
                                {result.total_tool_calls}
                              </span>
                            </div>
                            <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl text-center">
                              <span className="text-[10px] text-slate-500 uppercase font-bold block">
                                Latency
                              </span>
                              <span className="text-base font-bold text-blue-600 block mt-0.5">
                                {result.total_latency_ms} ms
                              </span>
                            </div>
                            <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl text-center">
                              <span className="text-[10px] text-slate-500 uppercase font-bold block">
                                Prompt Tokens
                              </span>
                              <span className="text-base font-bold text-slate-900 block mt-0.5">
                                {result.prompt_tokens}
                              </span>
                            </div>
                            <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl text-center">
                              <span className="text-[10px] text-slate-500 uppercase font-bold block">
                                Completion Tokens
                              </span>
                              <span className="text-base font-bold text-slate-900 block mt-0.5">
                                {result.completion_tokens}
                              </span>
                            </div>
                          </div>

                          {/* Safe Status Timeline Pill */}
                          <div className="flex items-center gap-2 text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-3.5 py-2">
                            <CheckCircle size={14} className="text-emerald-600" />
                            <span>Workflow completed successfully via {result.total_tool_calls} safe tool operations.</span>
                          </div>

                          {/* Answer Body */}
                          <div className="text-xs md:text-sm text-slate-800 leading-relaxed font-sans bg-slate-50 border border-slate-100 rounded-xl p-4 whitespace-pre-wrap">
                            {result.final_answer}
                          </div>
                        </div>
                      )}

                      {/* Tool Timeline Tab */}
                      {activeTab === "timeline" && (
                        <div>
                          <AgentTimeline toolCalls={result.tool_calls} />
                        </div>
                      )}

                      {/* Chunks Tab */}
                      {activeTab === "chunks" && (
                        <div className="space-y-3">
                          {retrievedChunks.length === 0 ? (
                            <p className="text-center text-xs text-slate-400 py-8">
                              No vector chunks were retrieved in this run.
                            </p>
                          ) : (
                            retrievedChunks.map((chunk, idx) => (
                              <AgentChunkCard
                                key={chunk.chunk_id || idx}
                                documentName={chunk.document_name}
                                text={chunk.text}
                                score={chunk.score}
                                pageNumber={chunk.page_number}
                              />
                            ))
                          )}
                        </div>
                      )}

                      {/* Raw JSON Trace Tab */}
                      {activeTab === "raw" && (
                        <pre className="bg-slate-900 text-slate-100 p-4 rounded-xl text-[11px] font-mono overflow-x-auto max-h-96">
                          {JSON.stringify(result, null, 2)}
                        </pre>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Right Column (1 Col): Registered Tools & Safety Panel */}
              <div className="space-y-6">
                
                {/* Registered Tools */}
                <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-3">
                  <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Wrench size={14} className="text-blue-600" />
                      Registered Tools
                    </span>
                    <span className="text-[10px] bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-bold">
                      {tools.length} Available
                    </span>
                  </h3>

                  <div className="space-y-2">
                    {tools.map((t) => (
                      <div
                        key={t.id}
                        className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl text-xs space-y-0.5"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-slate-800">{t.name}</span>
                          <span className="text-[9px] font-mono bg-slate-200 text-slate-700 px-1 py-0.5 rounded">
                            {t.id}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500 leading-snug">{t.description}</p>
                      </div>
                    ))}
                    {tools.length === 0 && (
                      <p className="text-xs text-slate-400 py-4 text-center">Loading tools…</p>
                    )}
                  </div>
                </div>

                {/* Safety Guardrails */}
                <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-3">
                  <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5 text-emerald-700">
                    <Shield size={14} className="text-emerald-600" />
                    Safety Guardrails
                  </h3>
                  <ul className="text-xs text-slate-600 space-y-1.5 list-disc pl-4">
                    <li>Prompt injection detection & sanitization</li>
                    <li>Max 5 tool calls per execution round</li>
                    <li>15-second per-tool timeout cap</li>
                    <li>No direct raw SQL / database access from LLM</li>
                    <li>Strict schema validation on tool parameters</li>
                  </ul>
                </div>

                {/* Agent 30-Day Statistics (Real Data) */}
                {stats && (
                  <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-3">
                    <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                      <BarChart3 size={14} className="text-blue-600" />
                      Agent Statistics
                    </h3>
                    <div className="grid grid-cols-2 gap-2 text-center text-xs">
                      <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-100">
                        <span className="text-base font-bold text-slate-900 block">
                          {stats.total_runs}
                        </span>
                        <span className="text-[10px] text-slate-500 block">Total Runs</span>
                      </div>
                      <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-100">
                        <span className="text-base font-bold text-emerald-600 block">
                          {stats.total_runs > 0
                            ? `${Math.round((stats.successful_runs / stats.total_runs) * 100)}%`
                            : "0%"}
                        </span>
                        <span className="text-[10px] text-slate-500 block">Success Rate</span>
                      </div>
                      <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-100">
                        <span className="text-base font-bold text-slate-900 block">
                          {stats.total_tool_calls}
                        </span>
                        <span className="text-[10px] text-slate-500 block">Tool Calls</span>
                      </div>
                      <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-100">
                        <span className="text-base font-bold text-slate-900 block">
                          {Math.round(stats.avg_run_latency_ms)} ms
                        </span>
                        <span className="text-[10px] text-slate-500 block">Avg Latency</span>
                      </div>
                    </div>
                  </div>
                )}

              </div>

            </div>

          </div>
        </main>
      </div>
    </div>
  );
}
