"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  FileText,
  ChevronDown,
  ChevronUp,
  ArrowUpRight,
  Zap,
  SlidersHorizontal,
  Database,
  Search,
  Layers,
  Sparkles
} from "lucide-react";
import { CitationItem } from "@/lib/api";

interface AppRightPanelProps {
  citations?: CitationItem[];
  onSuggestedQuestionClick?: (q: string) => void;
  onQuickActionClick?: (action: string) => void;
  // Chat configuration state
  temperature: number;
  setTemperature: (t: number) => void;
  topK: number;
  setTopK: (k: number) => void;
  threshold: number;
  setThreshold: (th: number) => void;
  useReranker: boolean;
  setUseReranker: (r: boolean) => void;
  maxTokens: number;
  setMaxTokens: (m: number) => void;
  onScrollToCitation?: (idx: number) => void;
}

export default function AppRightPanel({
  citations = [],
  onSuggestedQuestionClick,
  onQuickActionClick,
  temperature,
  setTemperature,
  topK,
  setTopK,
  threshold,
  setThreshold,
  useReranker,
  setUseReranker,
  maxTokens,
  setMaxTokens,
  onScrollToCitation
}: AppRightPanelProps) {
  const [activeTab, setActiveTab] = useState<"sources" | "settings" | "tools">("sources");
  const [sourcesAccordionOpen, setSourcesAccordionOpen] = useState(true);

  // Suggested questions list
  const suggestedQuestions = [
    "What is the system architecture?",
    "Tell me about the performance metrics",
    "What are the security considerations?",
    "Show me the implementation roadmap",
    "Compare this with other RAG approaches",
  ];

  // Helper to format match score
  const formatMatch = (score: number) => {
    // If score is normalized 0-1, show as %
    const percentage = score > 1 ? Math.min(Math.round(score), 100) : Math.round(score * 100);
    return `${percentage}% match`;
  };

  // Helper for document icon
  const getDocIcon = (filename: string) => {
    const lower = filename.toLowerCase();
    if (lower.endsWith(".pdf")) {
      return (
        <div className="w-7 h-7 rounded-md bg-red-100 text-red-600 flex items-center justify-center shrink-0">
          <span className="text-[9px] font-bold uppercase">PDF</span>
        </div>
      );
    }
    if (lower.endsWith(".docx") || lower.endsWith(".doc")) {
      return (
        <div className="w-7 h-7 rounded-md bg-blue-100 text-blue-600 flex items-center justify-center shrink-0">
          <span className="text-[9px] font-bold uppercase">DOC</span>
        </div>
      );
    }
    return (
      <div className="w-7 h-7 rounded-md bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
        <FileText size={14} />
      </div>
    );
  };

  return (
    <aside className="w-80 h-full bg-white border-l border-slate-200/80 flex flex-col shrink-0 overflow-hidden">
      {/* ── Tabs Header ─────────────────────────────────────────── */}
      <div className="flex items-center border-b border-slate-200 px-4 pt-2">
        <button
          onClick={() => setActiveTab("sources")}
          className={`px-3 py-2.5 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
            activeTab === "sources"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Sources
        </button>
        <button
          onClick={() => setActiveTab("settings")}
          className={`px-3 py-2.5 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
            activeTab === "settings"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Chat Settings
        </button>
        <button
          onClick={() => setActiveTab("tools")}
          className={`px-3 py-2.5 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
            activeTab === "tools"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Tools
        </button>
      </div>

      {/* ── Tab Content ─────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6 scrollbar-thin">
        {activeTab === "sources" && (
          <>
            {/* Relevant Documents Accordion */}
            <div>
              <button
                onClick={() => setSourcesAccordionOpen(!sourcesAccordionOpen)}
                className="w-full flex items-center justify-between text-xs font-bold text-slate-900 mb-2"
              >
                <span>Relevant Documents ({citations.length})</span>
                {sourcesAccordionOpen ? (
                  <ChevronUp size={14} className="text-slate-400" />
                ) : (
                  <ChevronDown size={14} className="text-slate-400" />
                )}
              </button>

              {sourcesAccordionOpen && (
                <div className="space-y-2 mt-2">
                  {citations.length === 0 ? (
                    <div className="p-4 bg-slate-50 border border-slate-200/80 rounded-xl text-center">
                      <FileText size={20} className="mx-auto text-slate-400 mb-1.5" />
                      <p className="text-xs font-semibold text-slate-700">No active sources</p>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        Ask a question to see real grounded document citations here.
                      </p>
                    </div>
                  ) : (
                    citations.map((c) => (
                      <div
                        key={c.citation_index}
                        onClick={() => onScrollToCitation && onScrollToCitation(c.citation_index)}
                        className="p-3 bg-slate-50/70 hover:bg-slate-100/80 border border-slate-200/80 rounded-xl transition-all cursor-pointer group"
                      >
                        <div className="flex items-start gap-2.5">
                          {getDocIcon(c.document_title)}
                          <div className="flex-1 min-w-0">
                            <h4
                              className="text-xs font-semibold text-slate-900 truncate group-hover:text-blue-600 transition-colors"
                              title={c.document_title}
                            >
                              {c.document_title}
                            </h4>
                            <div className="flex items-center gap-1.5 text-[11px] text-slate-500 mt-0.5 font-medium">
                              <span>Page {c.page_number}</span>
                              <span>•</span>
                              <span className="text-blue-600 font-semibold">
                                {formatMatch(c.score)}
                              </span>
                            </div>
                            <p className="mt-1.5 text-[11px] text-slate-600 line-clamp-2 leading-relaxed">
                              &ldquo;{c.text}&rdquo;
                            </p>
                          </div>
                        </div>
                      </div>
                    ))
                  )}

                  {citations.length > 0 && (
                    <Link
                      href="/documents"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-700 pt-1 transition-colors"
                    >
                      <span>View all sources</span>
                      <span>→</span>
                    </Link>
                  )}
                </div>
              )}
            </div>

            {/* Suggested Questions Section */}
            <div>
              <h3 className="text-xs font-bold text-slate-900 mb-2.5">
                Suggested Questions
              </h3>
              <div className="space-y-1.5">
                {suggestedQuestions.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => onSuggestedQuestionClick && onSuggestedQuestionClick(q)}
                    className="w-full flex items-center justify-between p-2.5 bg-slate-50 hover:bg-blue-50/50 border border-slate-200/80 hover:border-blue-200 rounded-xl text-left text-xs font-medium text-slate-700 hover:text-blue-700 transition-all duration-150 group cursor-pointer"
                  >
                    <span className="truncate pr-2">{q}</span>
                    <ArrowUpRight
                      size={14}
                      className="text-slate-400 group-hover:text-blue-600 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all shrink-0"
                    />
                  </button>
                ))}
              </div>
            </div>

            {/* Quick Actions 2x2 Grid */}
            <div>
              <h3 className="text-xs font-bold text-slate-900 mb-2.5">
                Quick Actions
              </h3>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() =>
                    onQuickActionClick &&
                    onQuickActionClick("Summarize the main findings from the uploaded documents.")
                  }
                  className="p-3 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-xl text-left transition-all cursor-pointer group"
                >
                  <div className="w-7 h-7 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center mb-2">
                    <FileText size={15} />
                  </div>
                  <span className="text-xs font-semibold text-slate-800 block">
                    Summarize Document
                  </span>
                </button>

                <button
                  onClick={() =>
                    onQuickActionClick &&
                    onQuickActionClick("Extract the key points and action items from the documents.")
                  }
                  className="p-3 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-xl text-left transition-all cursor-pointer group"
                >
                  <div className="w-7 h-7 rounded-lg bg-purple-100 text-purple-600 flex items-center justify-center mb-2">
                    <SlidersHorizontal size={15} />
                  </div>
                  <span className="text-xs font-semibold text-slate-800 block">
                    Extract Key Points
                  </span>
                </button>

                <button
                  onClick={() =>
                    onQuickActionClick &&
                    onQuickActionClick("Compare the key topics and metrics across multiple documents.")
                  }
                  className="p-3 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-xl text-left transition-all cursor-pointer group"
                >
                  <div className="w-7 h-7 rounded-lg bg-indigo-100 text-indigo-600 flex items-center justify-center mb-2">
                    <Layers size={15} />
                  </div>
                  <span className="text-xs font-semibold text-slate-800 block">
                    Compare Documents
                  </span>
                </button>

                <button
                  onClick={() =>
                    onQuickActionClick &&
                    onQuickActionClick("Generate a structured executive report with citations.")
                  }
                  className="p-3 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-xl text-left transition-all cursor-pointer group"
                >
                  <div className="w-7 h-7 rounded-lg bg-emerald-100 text-emerald-600 flex items-center justify-center mb-2">
                    <Zap size={15} />
                  </div>
                  <span className="text-xs font-semibold text-slate-800 block">
                    Generate Report
                  </span>
                </button>
              </div>
            </div>
          </>
        )}

        {activeTab === "settings" && (
          <div className="space-y-4 text-xs">
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="font-semibold text-slate-700">Temperature</label>
                <span className="font-mono text-slate-500">{temperature}</span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full accent-blue-600 cursor-pointer"
              />
              <span className="text-[10px] text-slate-400">
                Lower values give focused, deterministic grounded answers.
              </span>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="font-semibold text-slate-700">Top Chunks (Top-K)</label>
                <span className="font-mono text-slate-500">{topK}</span>
              </div>
              <input
                type="range"
                min="1"
                max="15"
                step="1"
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value))}
                className="w-full accent-blue-600 cursor-pointer"
              />
              <span className="text-[10px] text-slate-400">
                Number of relevant context passages passed to Gemini.
              </span>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="font-semibold text-slate-700">Similarity Cutoff</label>
                <span className="font-mono text-slate-500">{threshold}</span>
              </div>
              <input
                type="range"
                min="0"
                max="0.8"
                step="0.05"
                value={threshold}
                onChange={(e) => setThreshold(parseFloat(e.target.value))}
                className="w-full accent-blue-600 cursor-pointer"
              />
              <span className="text-[10px] text-slate-400">
                Minimum vector cosine similarity threshold.
              </span>
            </div>

            <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
              <div>
                <label className="font-semibold text-slate-800 block">Reranker</label>
                <span className="text-[10px] text-slate-400 block">
                  Cross-encoder contextual reranking
                </span>
              </div>
              <input
                type="checkbox"
                checked={useReranker}
                onChange={(e) => setUseReranker(e.target.checked)}
                className="w-4 h-4 rounded text-blue-600 accent-blue-600 cursor-pointer"
              />
            </div>

            <div className="pt-2 border-t border-slate-100">
              <div className="flex items-center justify-between mb-1.5">
                <label className="font-semibold text-slate-700">Max Tokens</label>
                <span className="font-mono text-slate-500">{maxTokens}</span>
              </div>
              <input
                type="range"
                min="256"
                max="2048"
                step="128"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value))}
                className="w-full accent-blue-600 cursor-pointer"
              />
            </div>
          </div>
        )}

        {activeTab === "tools" && (
          <div className="space-y-3 text-xs">
            <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl">
              <div className="flex items-center justify-between mb-1">
                <span className="font-bold text-slate-800 flex items-center gap-1.5">
                  <Database size={14} className="text-blue-600" />
                  pgvector Vector Store
                </span>
                <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded font-bold uppercase">
                  Connected
                </span>
              </div>
              <p className="text-[11px] text-slate-500">
                PostgreSQL database running vector similarity cosine indexing.
              </p>
            </div>

            <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl">
              <div className="flex items-center justify-between mb-1">
                <span className="font-bold text-slate-800 flex items-center gap-1.5">
                  <Sparkles size={14} className="text-purple-600" />
                  Google Gemini LLM
                </span>
                <span className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-bold uppercase">
                  Active Provider
                </span>
              </div>
              <p className="text-[11px] text-slate-500">
                Sole inference engine for grounded response generation and reasoning.
              </p>
            </div>

            <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl">
              <div className="flex items-center justify-between mb-1">
                <span className="font-bold text-slate-800 flex items-center gap-1.5">
                  <Search size={14} className="text-indigo-600" />
                  Hybrid Search Engine
                </span>
                <span className="text-[10px] bg-slate-200 text-slate-700 px-1.5 py-0.5 rounded font-bold uppercase">
                  Ready
                </span>
              </div>
              <p className="text-[11px] text-slate-500">
                Combines full-text lexical ranking with semantic embeddings.
              </p>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
