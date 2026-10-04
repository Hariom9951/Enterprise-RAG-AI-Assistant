"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  searchApi,
  SearchResultItem,
  SearchQueryResponse,
  SearchStatisticsResponse
} from "@/lib/api";
import {
  Search,
  Sliders,
  History,
  BarChart3,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronUp
} from "lucide-react";
import AppSidebar from "@/components/layout/AppSidebar";
import AppTopbar from "@/components/layout/AppTopbar";

export default function SemanticSearchPage() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // Search Parameters
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(10);
  const [threshold, setThreshold] = useState(0.0);
  const [searchType, setSearchType] = useState<"hybrid" | "semantic">("hybrid");

  // Operational States
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [history, setHistory] = useState<SearchQueryResponse[]>([]);
  const [stats, setStats] = useState<SearchStatisticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  // Fetch search history and analytics statistics
  const fetchStatsAndHistory = useCallback(async () => {
    try {
      const [historyList, statObj] = await Promise.all([
        searchApi.getHistory().catch(() => []),
        searchApi.getStatistics().catch(() => null)
      ]);
      setHistory(historyList);
      setStats(statObj);
    } catch (e) {
      console.error("Failed to load search stats", e);
    }
  }, []);

  useEffect(() => {
    void fetchStatsAndHistory();
  }, [fetchStatsAndHistory]);

  // Execute Search query
  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    const start = performance.now();

    try {
      const payload = {
        query: query.trim(),
        top_k: topK,
        threshold,
        search_type: searchType,
      };

      const searchResults = await searchApi.search(payload);
      setResults(searchResults || []);
      setLatency(Math.round(performance.now() - start));
      void fetchStatsAndHistory();
    } catch (err: unknown) {
      console.error("Search query failed:", err);
      setError("Search query execution failed. Please verify backend availability.");
    } finally {
      setLoading(false);
    }
  };

  const highlightMatches = (text: string, term: string) => {
    if (!term.trim()) return text;
    try {
      const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const regex = new RegExp(`(${escaped})`, "gi");
      const parts = text.split(regex);
      return (
        <>
          {parts.map((part, index) =>
            regex.test(part) ? (
              <mark
                key={index}
                className="bg-blue-100 text-blue-900 font-semibold px-0.5 rounded"
              >
                {part}
              </mark>
            ) : (
              part
            )
          )}
        </>
      );
    } catch {
      return text;
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.75) return "bg-emerald-50 text-emerald-700 border-emerald-200";
    if (score >= 0.5) return "bg-blue-50 text-blue-700 border-blue-200";
    return "bg-slate-100 text-slate-700 border-slate-200";
  };

  const getFileBadge = (filename: string) => {
    const isPdf = filename.toLowerCase().endsWith(".pdf");
    return (
      <span
        className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
          isPdf ? "bg-red-50 text-red-600 border border-red-200" : "bg-blue-50 text-blue-600 border border-blue-200"
        }`}
      >
        {isPdf ? "PDF" : "DOC"}
      </span>
    );
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
                  <Search className="text-blue-600" size={24} />
                  Semantic & Hybrid Search
                </h1>
                <p className="text-xs md:text-sm text-slate-500 mt-1">
                  Dense vector similarity search using BAAI/bge-base embeddings combined with lexical BM25.
                </p>
              </div>

              {stats && (
                <div className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-2xs self-start">
                  <span className="flex items-center gap-1.5">
                    <BarChart3 size={14} className="text-blue-600" />
                    <span>Total Searches: {stats.total_queries ?? 0}</span>
                  </span>
                  <span>•</span>
                  <span>Avg: {Math.round(stats.average_latency_ms ?? 0)} ms</span>
                </div>
              )}
            </div>

            {/* Error Notification */}
            {error && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3 text-xs text-red-800 shadow-2xs">
                <AlertCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
                <p>{error}</p>
              </div>
            )}

            {/* ── Search Input Card ─────────────────────────────────── */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-2xs space-y-4">
              <form onSubmit={handleSearch} className="space-y-3">
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-3.5 top-3.5 text-slate-400 h-4 w-4 pointer-events-none" />
                    <input
                      type="text"
                      placeholder="Search knowledge base concepts, terms, or policies..."
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl py-3 pl-10 pr-4 text-xs md:text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:border-blue-500 focus:bg-white focus:ring-1 focus:ring-blue-200 transition-all font-medium"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={!query.trim() || loading}
                    className="px-5 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition-colors shadow-xs cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shrink-0 flex items-center gap-2"
                  >
                    {loading ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Search size={14} />
                    )}
                    <span>Search</span>
                  </button>
                </div>

                {/* Sub-bar: Search Type Toggle + Filter Button */}
                <div className="flex items-center justify-between pt-1 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                      Search Mode:
                    </span>
                    <button
                      type="button"
                      onClick={() => setSearchType("hybrid")}
                      className={`px-3 py-1.5 rounded-lg font-semibold transition-all cursor-pointer ${
                        searchType === "hybrid"
                          ? "bg-blue-50 text-blue-700 border border-blue-200"
                          : "text-slate-600 hover:bg-slate-100 border border-transparent"
                      }`}
                    >
                      Hybrid (Vector + BM25)
                    </button>
                    <button
                      type="button"
                      onClick={() => setSearchType("semantic")}
                      className={`px-3 py-1.5 rounded-lg font-semibold transition-all cursor-pointer ${
                        searchType === "semantic"
                          ? "bg-blue-50 text-blue-700 border border-blue-200"
                          : "text-slate-600 hover:bg-slate-100 border border-transparent"
                      }`}
                    >
                      Dense Vector Only
                    </button>
                  </div>

                  <button
                    type="button"
                    onClick={() => setShowFilters(!showFilters)}
                    className="flex items-center gap-1.5 text-slate-600 hover:text-slate-900 font-semibold cursor-pointer"
                  >
                    <Sliders size={13} className="text-blue-600" />
                    <span>Filters & Top-K</span>
                    {showFilters ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                  </button>
                </div>

                {/* Expandable Filter Box */}
                {showFilters && (
                  <div className="mt-3 p-4 bg-slate-50 border border-slate-200 rounded-xl grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs animate-fade-in">
                    <div>
                      <div className="flex justify-between font-semibold text-slate-700 mb-1">
                        <span>Top Results (Top-K)</span>
                        <span className="font-mono text-blue-600">{topK}</span>
                      </div>
                      <input
                        type="range"
                        min="1"
                        max="25"
                        value={topK}
                        onChange={(e) => setTopK(parseInt(e.target.value))}
                        className="w-full accent-blue-600 cursor-pointer"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between font-semibold text-slate-700 mb-1">
                        <span>Min Cosine Similarity</span>
                        <span className="font-mono text-blue-600">{threshold}</span>
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
                    </div>
                  </div>
                )}
              </form>
            </div>

            {/* ── Search Results & History Grid ────────────────────── */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Results Column (2 Cols) */}
              <div className="lg:col-span-2 space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                    Search Results ({results.length})
                  </h2>
                  {latency !== null && (
                    <span className="text-[11px] text-slate-500 font-mono">
                      Query executed in {latency} ms
                    </span>
                  )}
                </div>

                {loading ? (
                  <div className="bg-white border border-slate-200/90 rounded-2xl p-12 text-center text-xs text-slate-400 flex flex-col items-center justify-center gap-2">
                    <Loader2 size={24} className="animate-spin text-blue-600" />
                    <span>Searching vector database…</span>
                  </div>
                ) : results.length === 0 ? (
                  <div className="bg-white border border-slate-200/90 rounded-2xl p-12 text-center text-xs text-slate-400 space-y-2">
                    <Search size={28} className="mx-auto text-slate-300" />
                    <p className="font-medium text-slate-600">No search results to display</p>
                    <p className="text-[11px] text-slate-400">
                      Enter a query above to explore semantically matching document passages.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {results.map((res, idx) => {
                      const docName = res.document?.original_filename || "Document";
                      return (
                        <div
                          key={idx}
                          className="bg-white border border-slate-200/90 hover:border-blue-200 rounded-2xl p-4 shadow-2xs transition-all space-y-2 group"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2 min-w-0">
                              {getFileBadge(docName)}
                              <h3
                                className="text-xs font-bold text-slate-900 truncate group-hover:text-blue-600 transition-colors"
                                title={docName}
                              >
                                {docName}
                              </h3>
                            </div>

                            <div className="flex items-center gap-2 shrink-0">
                              <span className="text-[10px] text-slate-500 font-medium">
                                Page {res.chunk?.page_number ?? 1}
                              </span>
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono border ${getScoreColor(
                                  res.score
                                )}`}
                              >
                                Score: {res.score.toFixed(4)}
                              </span>
                            </div>
                          </div>

                          <p className="text-xs text-slate-700 leading-relaxed font-sans bg-slate-50 border border-slate-100 rounded-xl p-3">
                            {highlightMatches(res.chunk?.text || "", query)}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* History / Previous Searches Column (1 Col) */}
              <div className="space-y-4">
                <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                  <History size={14} className="text-blue-600" />
                  Recent Search History
                </h2>

                <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs space-y-2">
                  {history.length === 0 ? (
                    <p className="py-8 text-center text-xs text-slate-400">
                      No recent searches found.
                    </p>
                  ) : (
                    <div className="divide-y divide-slate-100">
                      {history.slice(0, 8).map((h) => (
                        <button
                          key={h.id}
                          onClick={() => {
                            setQuery(h.query_text);
                            setSearchType(
                              h.search_type.toLowerCase() === "hybrid" ? "hybrid" : "semantic"
                            );
                            handleSearch();
                          }}
                          className="w-full py-2.5 text-left text-xs hover:text-blue-600 transition-colors flex items-center justify-between group cursor-pointer"
                        >
                          <span className="truncate pr-2 font-medium text-slate-700 group-hover:text-blue-600">
                            &ldquo;{h.query_text}&rdquo;
                          </span>
                          <span className="text-[10px] text-slate-400 font-mono shrink-0">
                            {h.total_results} results
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

            </div>

          </div>
        </main>
      </div>
    </div>
  );
}
