"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  BarChart3,
  FileText,
  Zap,
  ArrowRight,
  MessageSquare,
  Search,
  Bot,
  HardDrive,
  AlertCircle,
  Layers
} from "lucide-react";
import AppSidebar from "@/components/layout/AppSidebar";
import AppTopbar from "@/components/layout/AppTopbar";
import { dashboardApi, DashboardData } from "@/lib/api";

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const fetchDashboard = async () => {
      try {
        setLoading(true);
        setError(null);
        const stats = await dashboardApi.getStatistics();
        if (isMounted) setData(stats);
      } catch (err) {
        console.error("Failed to load dashboard data:", err);
        if (isMounted) {
          setError("Failed to sync system statistics. Ensure backend and DB are online.");
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    fetchDashboard();
    return () => {
      isMounted = false;
    };
  }, []);

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const formatDate = (isoString: string): string => {
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      });
    } catch {
      return isoString;
    }
  };

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
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
                  <BarChart3 className="text-blue-600" size={24} />
                  Workspace Analytics
                </h1>
                <p className="text-xs md:text-sm text-slate-500 mt-1">
                  Real-time knowledge base statistics, query metrics, and execution activity.
                </p>
              </div>

              {data && (
                <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-2xs self-start">
                  <HardDrive size={14} className="text-blue-600" />
                  <span>Storage: {formatBytes(data.storage_usage_bytes)}</span>
                </div>
              )}
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3 text-xs text-red-800 shadow-2xs">
                <AlertCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
                <div>
                  <span className="font-semibold block">Connection Error</span>
                  <p className="mt-0.5 text-red-700">{error}</p>
                </div>
              </div>
            )}

            {loading ? (
              <div className="space-y-6">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  {[...Array(4)].map((_, i) => (
                    <div key={i} className="h-28 bg-white border border-slate-200 rounded-2xl animate-pulse" />
                  ))}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="h-72 bg-white border border-slate-200 rounded-2xl animate-pulse" />
                  <div className="h-72 bg-white border border-slate-200 rounded-2xl animate-pulse" />
                </div>
              </div>
            ) : data ? (
              <div className="space-y-6">
                
                {/* 1. Metric Counter Cards Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  
                  {/* Documents */}
                  <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs flex flex-col justify-between">
                    <div className="flex items-center justify-between text-slate-400">
                      <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500">
                        Total Corpus
                      </span>
                      <div className="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                        <FileText size={15} />
                      </div>
                    </div>
                    <div className="mt-3">
                      <span className="text-2xl font-bold text-slate-900 block">
                        {data.total_documents}
                      </span>
                      <span className="text-[11px] text-slate-500 mt-0.5 block">
                        Ingested Documents
                      </span>
                    </div>
                  </div>

                  {/* Chunks */}
                  <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs flex flex-col justify-between">
                    <div className="flex items-center justify-between text-slate-400">
                      <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500">
                        Indexed Chunks
                      </span>
                      <div className="w-7 h-7 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
                        <Layers size={15} />
                      </div>
                    </div>
                    <div className="mt-3">
                      <span className="text-2xl font-bold text-slate-900 block">
                        {data.total_chunks}
                      </span>
                      <span className="text-[11px] text-slate-500 mt-0.5 block">
                        768-dim Vector Embeddings
                      </span>
                    </div>
                  </div>

                  {/* Queries Served */}
                  <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs flex flex-col justify-between">
                    <div className="flex items-center justify-between text-slate-400">
                      <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500">
                        Today&apos;s Queries
                      </span>
                      <div className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                        <MessageSquare size={15} />
                      </div>
                    </div>
                    <div className="mt-3">
                      <span className="text-2xl font-bold text-slate-900 block">
                        {data.todays_queries}
                      </span>
                      <span className="text-[11px] text-slate-500 mt-0.5 block">
                        Live Grounded Answers
                      </span>
                    </div>
                  </div>

                  {/* Avg Latency */}
                  <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs flex flex-col justify-between">
                    <div className="flex items-center justify-between text-slate-400">
                      <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500">
                        Avg Query Latency
                      </span>
                      <div className="w-7 h-7 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                        <Zap size={15} />
                      </div>
                    </div>
                    <div className="mt-3">
                      <span className="text-2xl font-bold text-slate-900 block">
                        {Math.round(data.average_latency_ms)} ms
                      </span>
                      <span className="text-[11px] text-slate-500 mt-0.5 block">
                        Vector + Gemini Generation
                      </span>
                    </div>
                  </div>
                </div>

                {/* 2. Quick Navigation Shortcuts */}
                <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs">
                  <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">
                    Workspace Actions
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <Link
                      href="/chat"
                      className="p-3.5 rounded-xl border border-slate-200/80 bg-slate-50 hover:bg-blue-50/50 hover:border-blue-200 transition-all flex items-center justify-between group"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center">
                          <MessageSquare size={16} />
                        </div>
                        <div>
                          <span className="text-xs font-bold text-slate-800 group-hover:text-blue-600 block">
                            Launch Assistant
                          </span>
                          <span className="text-[11px] text-slate-500">
                            Interactive cited Q&A
                          </span>
                        </div>
                      </div>
                      <ArrowRight size={14} className="text-slate-400 group-hover:text-blue-600 group-hover:translate-x-0.5 transition-all" />
                    </Link>

                    <Link
                      href="/documents"
                      className="p-3.5 rounded-xl border border-slate-200/80 bg-slate-50 hover:bg-blue-50/50 hover:border-blue-200 transition-all flex items-center justify-between group"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-purple-100 text-purple-600 flex items-center justify-center">
                          <FileText size={16} />
                        </div>
                        <div>
                          <span className="text-xs font-bold text-slate-800 group-hover:text-blue-600 block">
                            Manage Documents
                          </span>
                          <span className="text-[11px] text-slate-500">
                            Upload & ingest files
                          </span>
                        </div>
                      </div>
                      <ArrowRight size={14} className="text-slate-400 group-hover:text-blue-600 group-hover:translate-x-0.5 transition-all" />
                    </Link>

                    <Link
                      href="/search"
                      className="p-3.5 rounded-xl border border-slate-200/80 bg-slate-50 hover:bg-blue-50/50 hover:border-blue-200 transition-all flex items-center justify-between group"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-600 flex items-center justify-center">
                          <Search size={16} />
                        </div>
                        <div>
                          <span className="text-xs font-bold text-slate-800 group-hover:text-blue-600 block">
                            Semantic Search
                          </span>
                          <span className="text-[11px] text-slate-500">
                            Vector similarity exploration
                          </span>
                        </div>
                      </div>
                      <ArrowRight size={14} className="text-slate-400 group-hover:text-blue-600 group-hover:translate-x-0.5 transition-all" />
                    </Link>
                  </div>
                </div>

                {/* 3. Recent Activity Double Columns */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  
                  {/* Recent Searches */}
                  <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
                        <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                          <Search size={14} className="text-blue-600" />
                          Recent Search Logs
                        </h3>
                        <Link
                          href="/search"
                          className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1"
                        >
                          View all <ArrowRight size={11} />
                        </Link>
                      </div>

                      {data.recent_searches.length === 0 ? (
                        <div className="py-12 text-center text-xs text-slate-400">
                          No searches recorded yet.
                        </div>
                      ) : (
                        <div className="divide-y divide-slate-100">
                          {data.recent_searches.slice(0, 5).map((s) => (
                            <div key={s.id} className="py-2.5 text-xs flex items-center justify-between gap-3">
                              <div className="min-w-0">
                                <p className="font-semibold text-slate-800 truncate" title={s.query_text}>
                                  &ldquo;{s.query_text}&rdquo;
                                </p>
                                <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5">
                                  <span>{s.total_results} results</span>
                                  <span>•</span>
                                  <span>{formatDate(s.created_at)}</span>
                                </div>
                              </div>
                              <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-slate-100 text-slate-600 border border-slate-200 shrink-0">
                                {s.search_type}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Recent Agent Runs */}
                  <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
                        <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                          <Bot size={14} className="text-purple-600" />
                          Recent Agent Runs
                        </h3>
                        <Link
                          href="/agent"
                          className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1"
                        >
                          View all <ArrowRight size={11} />
                        </Link>
                      </div>

                      {data.recent_agent_runs.length === 0 ? (
                        <div className="py-12 text-center text-xs text-slate-400">
                          No agent runs recorded yet.
                        </div>
                      ) : (
                        <div className="divide-y divide-slate-100">
                          {data.recent_agent_runs.slice(0, 5).map((r) => (
                            <div key={r.id} className="py-2.5 text-xs flex items-center justify-between gap-3">
                              <div className="min-w-0">
                                <p className="font-semibold text-slate-800 truncate" title={r.question}>
                                  {r.question}
                                </p>
                                <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5">
                                  <span>{r.total_latency_ms} ms</span>
                                  <span>•</span>
                                  <span>{formatDate(r.created_at)}</span>
                                </div>
                              </div>
                              <span
                                className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase shrink-0 ${
                                  r.success
                                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                    : "bg-red-50 text-red-700 border border-red-200"
                                }`}
                              >
                                {r.success ? "success" : "failed"}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                </div>

              </div>
            ) : (
              <div className="py-16 text-center text-xs text-slate-400">
                No system statistics found.
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
