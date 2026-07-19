"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  LayoutDashboard,
  FileText,
  Database,
  Clock,
  Zap,
  TrendingUp,
  Cpu,
  ArrowRight,
  MessageSquare,
  Search,
  Bot,
  HardDrive,
  Loader2,
  AlertCircle
} from "lucide-react";
import Navigation from "@/components/Navigation";
import { dashboardApi, DashboardData } from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        setLoading(true);
        setError(null);
        const stats = await dashboardApi.getStatistics();
        setData(stats);
      } catch (err) {
        console.error("Failed to load dashboard data:", err);
        setError("Failed to sync system statistics. Ensure backend and DB are online.");
      } finally {
        setLoading(false);
      }
    };
    fetchDashboard();
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
    <div className="flex min-h-screen bg-slate-950 text-slate-100 font-sans pl-0 md:pl-64">
      {/* Sidebar Navigation */}
      <Navigation />

      {/* Decorative glows */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#0f172a_1px,transparent_1px),linear-gradient(to_bottom,#0f172a_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] opacity-20 pointer-events-none" />
      <div className="absolute top-0 left-1/3 w-[600px] h-[500px] bg-indigo-500/5 blur-[160px] rounded-full pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-[500px] h-[400px] bg-sky-500/5 blur-[150px] rounded-full pointer-events-none" />

      {/* Main Workspace Console */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8 relative z-10 overflow-y-auto">
        
        {/* Title Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-2.5">
              <LayoutDashboard className="text-indigo-400" size={28} />
              Workspace Dashboard
            </h1>
            <p className="mt-2 text-sm text-slate-400">
              System health logs, recent uploads, audit logs, and GenAI parameter counters.
            </p>
          </div>
          {data && (
            <div className="flex items-center gap-2.5 bg-slate-900/60 border border-slate-800 rounded-xl px-4 py-2 text-xs font-semibold text-slate-300">
              <HardDrive size={14} className="text-indigo-400" />
              <span>Storage Used: {formatBytes(data.storage_usage_bytes)}</span>
            </div>
          )}
        </div>

        {error && (
          <div className="bg-rose-950/20 border border-rose-900/40 rounded-xl p-4 flex items-start gap-3 mb-6">
            <AlertCircle className="h-5 w-5 text-rose-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-white">System Error</p>
              <p className="text-xs text-rose-300 mt-1">{error}</p>
            </div>
          </div>
        )}

        {loading ? (
          /* Skeleton Loader */
          <div className="space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-24 bg-slate-900/40 border border-slate-900 rounded-xl animate-pulse" />
              ))}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="h-80 bg-slate-900/30 border border-slate-900 rounded-xl animate-pulse" />
              <div className="h-80 bg-slate-900/30 border border-slate-900 rounded-xl animate-pulse" />
            </div>
          </div>
        ) : data ? (
          <div className="space-y-8">
            
            {/* 1. Counter Widgets Grid */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              
              <div className="bg-slate-900/40 border border-slate-900 rounded-xl p-4 flex flex-col justify-between hover:border-slate-800 transition-colors">
                <div className="flex items-center justify-between text-slate-400">
                  <span className="text-[10px] uppercase font-bold tracking-wider">Total Corpus</span>
                  <FileText size={16} className="text-indigo-400" />
                </div>
                <div className="mt-4">
                  <span className="text-2xl font-extrabold text-white block">{data.total_documents}</span>
                  <span className="text-[10px] text-slate-500 mt-0.5 block">Ingested Documents</span>
                </div>
              </div>

              <div className="bg-slate-900/40 border border-slate-900 rounded-xl p-4 flex flex-col justify-between hover:border-slate-800 transition-colors">
                <div className="flex items-center justify-between text-slate-400">
                  <span className="text-[10px] uppercase font-bold tracking-wider">Vector Chunks</span>
                  <Database size={16} className="text-sky-400" />
                </div>
                <div className="mt-4">
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-2xl font-extrabold text-white">{data.total_embeddings}</span>
                    <span className="text-xs text-slate-500">/ {data.total_chunks}</span>
                  </div>
                  <span className="text-[10px] text-slate-500 mt-0.5 block">Embedded Passages</span>
                </div>
              </div>

              <div className="bg-slate-900/40 border border-slate-900 rounded-xl p-4 flex flex-col justify-between hover:border-slate-800 transition-colors">
                <div className="flex items-center justify-between text-slate-400">
                  <span className="text-[10px] uppercase font-bold tracking-wider">Query Traffic</span>
                  <Clock size={16} className="text-emerald-400" />
                </div>
                <div className="mt-4">
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-2xl font-extrabold text-white">{data.todays_queries}</span>
                    <span className="text-[10px] text-emerald-400 font-mono">Today</span>
                  </div>
                  <span className="text-[10px] text-slate-500 mt-0.5 block">Total Conversations: {data.total_conversations}</span>
                </div>
              </div>

              <div className="bg-slate-900/40 border border-slate-900 rounded-xl p-4 flex flex-col justify-between hover:border-slate-800 transition-colors">
                <div className="flex items-center justify-between text-slate-400">
                  <span className="text-[10px] uppercase font-bold tracking-wider">Avg Latency</span>
                  <Zap size={16} className="text-amber-400" />
                </div>
                <div className="mt-4">
                  <span className="text-2xl font-extrabold text-white block">{data.average_latency_ms} ms</span>
                  <span className="text-[10px] text-slate-500 mt-0.5 block">Avg Similarity: {(data.average_similarity * 100).toFixed(1)}%</span>
                </div>
              </div>

            </div>

            {/* 2. Primary Layout Workspace Lists */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              
              {/* Recent Document Uploads Card */}
              <section className="bg-slate-900/40 border border-slate-900 rounded-2xl p-6 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between border-b border-slate-850 pb-4 mb-4">
                    <h2 className="text-sm font-bold text-white flex items-center gap-2">
                      <FileText size={16} className="text-indigo-400" />
                      Recent Ingested Documents
                    </h2>
                    <Link
                      href="/documents"
                      className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1 transition-colors"
                    >
                      View All <ArrowRight size={12} />
                    </Link>
                  </div>

                  {data.recent_uploads.length === 0 ? (
                    <div className="text-center text-xs text-slate-500 py-12">
                      No documents found in knowledge base.
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-850">
                      {data.recent_uploads.map((doc) => (
                        <div key={doc.id} className="py-3 flex items-center justify-between gap-4 text-xs">
                          <div className="min-w-0">
                            <span
                              className="font-semibold text-slate-200 block truncate cursor-pointer hover:text-indigo-300"
                              onClick={() => router.push(`/documents/${doc.id}`)}
                            >
                              {doc.original_filename}
                            </span>
                            <span className="text-slate-500 font-mono mt-0.5 block">
                              {formatBytes(doc.file_size)} · {formatDate(doc.created_at)}
                            </span>
                          </div>
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                              doc.processing_status.toUpperCase() === "COMPLETED"
                                ? "bg-emerald-950/40 border-emerald-800/40 text-emerald-400"
                                : doc.processing_status.toUpperCase() === "FAILED"
                                ? "bg-rose-950/40 border-rose-800/40 text-rose-400"
                                : "bg-slate-900 border-slate-800 text-slate-400 animate-pulse"
                            }`}
                          >
                            {doc.processing_status.toLowerCase()}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>

              {/* Recent Conversations Card */}
              <section className="bg-slate-900/40 border border-slate-900 rounded-2xl p-6 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between border-b border-slate-850 pb-4 mb-4">
                    <h2 className="text-sm font-bold text-white flex items-center gap-2">
                      <MessageSquare size={16} className="text-indigo-400" />
                      Active Chat Sessions
                    </h2>
                    <Link
                      href="/chat"
                      className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1 transition-colors"
                    >
                      Open Chat <ArrowRight size={12} />
                    </Link>
                  </div>

                  {data.recent_conversations.length === 0 ? (
                    <div className="text-center text-xs text-slate-500 py-12">
                      No active sessions. Start a conversation in the chat assistant.
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-850">
                      {data.recent_conversations.map((session) => (
                        <div
                          key={session.id}
                          onClick={() => router.push(`/chat`)}
                          className="py-3 flex items-center justify-between gap-4 cursor-pointer hover:bg-slate-900/20 px-2 rounded-xl transition-all"
                        >
                          <div className="min-w-0">
                            <span className="font-semibold text-slate-200 block truncate">
                              {session.title}
                            </span>
                            <span className="text-[10px] text-slate-500 mt-0.5 block">
                              Last updated: {formatDate(session.updated_at)}
                            </span>
                          </div>
                          <ChevronIcon className="text-slate-600 shrink-0" />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>

            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">

              {/* Recent Search Logs Card */}
              <section className="bg-slate-900/40 border border-slate-900 rounded-2xl p-6">
                <div className="flex items-center justify-between border-b border-slate-850 pb-4 mb-4">
                  <h2 className="text-sm font-bold text-white flex items-center gap-2">
                    <Search size={16} className="text-indigo-400" />
                    Audited Retrieval Logs
                  </h2>
                  <Link
                    href="/search"
                    className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1 transition-colors"
                  >
                    Run Search <ArrowRight size={12} />
                  </Link>
                </div>

                {data.recent_searches.length === 0 ? (
                  <div className="text-center text-xs text-slate-500 py-12">
                    No search logs found.
                  </div>
                ) : (
                  <div className="divide-y divide-slate-850">
                    {data.recent_searches.map((search) => (
                      <div key={search.id} className="py-3.5 text-xs">
                        <div className="flex items-start justify-between gap-4">
                          <p className="font-semibold text-slate-200 line-clamp-1 italic">
                            "{search.query_text}"
                          </p>
                          <span className="px-1.5 py-0.5 rounded text-[8px] font-mono border border-slate-800 text-slate-400 shrink-0 uppercase">
                            {search.search_type}
                          </span>
                        </div>
                        <div className="flex gap-3 text-[10px] text-slate-500 font-mono mt-1">
                          <span>Results matched: {search.total_results}</span>
                          <span>•</span>
                          <span>Timestamp: {formatDate(search.created_at)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {/* Recent Agent Execution Logs Card */}
              <section className="bg-slate-900/40 border border-slate-900 rounded-2xl p-6">
                <div className="flex items-center justify-between border-b border-slate-850 pb-4 mb-4">
                  <h2 className="text-sm font-bold text-white flex items-center gap-2">
                    <Bot size={16} className="text-indigo-400" />
                    Agent Reasoning Logs
                  </h2>
                  <Link
                    href="/agent"
                    className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1 transition-colors"
                  >
                    Open Agent <ArrowRight size={12} />
                  </Link>
                </div>

                {data.recent_agent_runs.length === 0 ? (
                  <div className="text-center text-xs text-slate-500 py-12">
                    No agent runs found.
                  </div>
                ) : (
                  <div className="divide-y divide-slate-850">
                    {data.recent_agent_runs.map((run) => (
                      <div key={run.id} className="py-3.5 text-xs">
                        <div className="flex items-start justify-between gap-4">
                          <p className="font-semibold text-slate-200 line-clamp-1">
                            {run.question}
                          </p>
                          <span
                            className={`px-2 py-0.5 rounded text-[9px] font-bold border shrink-0 ${
                              run.success
                                ? "bg-emerald-950/40 border-emerald-800/40 text-emerald-400"
                                : "bg-rose-950/40 border-rose-800/40 text-rose-400"
                            }`}
                          >
                            {run.success ? "success" : "failed"}
                          </span>
                        </div>
                        <div className="flex gap-3 text-[10px] text-slate-500 font-mono mt-1">
                          <span>Latency: {run.total_latency_ms} ms</span>
                          <span>•</span>
                          <span>Ran on: {formatDate(run.created_at)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>

            </div>

          </div>
        ) : (
          <div className="text-center text-xs text-slate-500 py-12">No data sync found.</div>
        )}

      </main>
    </div>
  );
}

function ChevronIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      viewBox="0 0 24 24"
      width="14"
      height="14"
      {...props}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}
