"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { searchApi, documentsApi, DocumentResponse, SearchResultItem, SearchQueryResponse, SearchStatisticsResponse } from "@/lib/api";
import { Loader2, Search, Sliders, History, BarChart3, AlertCircle, ArrowRight, ExternalLink } from "lucide-react";
import Navigation from "@/components/Navigation";

export default function SemanticSearchPage() {
  const router = useRouter();

  // Search Parameters
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(10);
  const [threshold, setThreshold] = useState(0.0);
  const [searchType, setSearchType] = useState("hybrid");

  // Filter Parameters
  const [allDocs, setAllDocs] = useState<DocumentResponse[]>([]);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [languages, setLanguages] = useState<string[]>([]);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [metaKey, setMetaKey] = useState("");
  const [metaVal, setMetaVal] = useState("");
  const [metaFilters, setMetaFilters] = useState<Record<string, string>>({});

  // Operational States
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [history, setHistory] = useState<SearchQueryResponse[]>([]);
  const [stats, setStats] = useState<SearchStatisticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [statsLoading, setStatsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState(1);

  // Fetch helper databases
  useEffect(() => {
    const loadAssets = async () => {
      try {
        const docs = await documentsApi.list({ limit: 100 });
        setAllDocs(docs);
      } catch (e) {
        console.error("Failed to load documents list", e);
      }
    };
    loadAssets();
  }, []);

  // Fetch search history and analytics statistics
  const fetchStatsAndHistory = useCallback(async () => {
    setStatsLoading(true);
    try {
      const historyList = await searchApi.getHistory();
      setHistory(historyList);
      const statObj = await searchApi.getStatistics();
      setStats(statObj);
    } catch (e) {
      console.error("Failed to load search stats", e);
    } finally {
      setStatsLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchStatsAndHistory();
    }, 0);
    return () => clearTimeout(timer);
  }, [fetchStatsAndHistory]);

  // Execute Search query
  const handleSearch = async (e?: React.FormEvent, newOffset = 0) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    const start = performance.now();

    try {
      const filtersObj: {
        document_ids?: string[];
        languages?: string[];
        start_date?: string;
        end_date?: string;
        metadata?: Record<string, string>;
      } = {};
      if (selectedDocs.length > 0) filtersObj.document_ids = selectedDocs;
      if (languages.length > 0) filtersObj.languages = languages;
      if (startDate) filtersObj.start_date = new Date(startDate).toISOString();
      if (endDate) filtersObj.end_date = new Date(endDate).toISOString();
      if (Object.keys(metaFilters).length > 0) filtersObj.metadata = metaFilters;

      const payload = {
        query: query.trim(),
        top_k: topK,
        offset: newOffset,
        threshold: threshold,
        search_type: searchType,
        filters: Object.keys(filtersObj).length > 0 ? filtersObj : undefined,
      };

      const items = await searchApi.search(payload);
      setResults(items);
      setOffset(newOffset);
      setPage(Math.floor(newOffset / topK) + 1);
      setLatency(Math.round(performance.now() - start));
      
      // Refresh history log & statistics
      fetchStatsAndHistory();
    } catch (err: unknown) {
      const errorResponse = err as { error?: { message?: string } } | undefined;
      setError(errorResponse?.error?.message ?? "Execution error. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handlePrevPage = () => {
    if (page > 1) {
      const nextOffset = Math.max(0, offset - topK);
      handleSearch(undefined, nextOffset);
    }
  };

  const handleNextPage = () => {
    if (results.length === topK) {
      const nextOffset = offset + topK;
      handleSearch(undefined, nextOffset);
    }
  };

  // Highlights search terms in the preview chunk
  const highlightText = (text: string, searchPhrase: string) => {
    if (!searchPhrase || !searchPhrase.trim()) return text;
    const keywords = searchPhrase
      .split(/\s+/)
      .map(word => word.replace(/[^a-zA-Z0-9]/g, ""))
      .filter(word => word.length > 2);
      
    if (keywords.length === 0) return text;
    
    try {
      const pattern = `(${keywords.join("|")})`;
      const regex = new RegExp(pattern, "gi");
      const parts = text.split(regex);
      return (
        <>
          {parts.map((part, index) =>
            regex.test(part) ? (
              <mark key={index} className="bg-indigo-500/35 text-indigo-200 px-0.5 rounded font-semibold">
                {part}
              </mark>
            ) : (
              part
            )
          )}
        </>
      );
    } catch (e) {
      console.error("Highlight rendering failed", e);
      return text;
    }
  };

  // Add Metadata tag criteria
  const handleAddMeta = () => {
    if (!metaKey.trim() || !metaVal.trim()) return;
    setMetaFilters(prev => ({ ...prev, [metaKey.trim()]: metaVal.trim() }));
    setMetaKey("");
    setMetaVal("");
  };

  // Quick rerun previous searches
  const handleRerun = (term: string, type: string) => {
    setQuery(term);
    setSearchType(type.toLowerCase());
    // Auto submit query next tick
    setTimeout(() => {
      const btn = document.getElementById("search-submit-btn");
      if (btn) btn.click();
    }, 100);
  };

  // Score validation styling helper
  const getScoreColor = (score: number) => {
    if (score >= 0.75) return "bg-emerald-950 text-emerald-400 border border-emerald-800/40";
    if (score >= 0.5) return "bg-blue-950 text-blue-400 border border-blue-800/40";
    return "bg-slate-900 text-slate-400 border border-slate-800";
  };

  return (
    <div className="relative min-h-screen bg-slate-950 text-slate-100 selection:bg-indigo-500/30 selection:text-indigo-200 pl-0 md:pl-64">
      <Navigation />
      {/* Background radial effects */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#0f172a_1px,transparent_1px),linear-gradient(to_bottom,#0f172a_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] opacity-20 pointer-events-none" />
      <div className="absolute top-0 left-1/4 w-[400px] h-[400px] bg-indigo-500/5 blur-[120px] rounded-full pointer-events-none" />

      {/* Main Console Layout */}
      <main className="mx-auto max-w-7xl px-6 py-8 grid grid-cols-1 lg:grid-cols-4 gap-8 relative z-10">
        
        {/* Left Column: Search & Settings Controls (3 columns wide) */}
        <div className="lg:col-span-3 space-y-6">
          
          {/* 🔍 Query Box Card */}
          <form onSubmit={handleSearch} className="bg-slate-900/40 border border-slate-900 rounded-2xl p-5 space-y-4">
            <div className="relative flex items-center">
              <Search className="absolute left-4 text-slate-400 h-5 w-5 pointer-events-none" />
              <input
                type="text"
                placeholder="Enter semantic search query (e.g., 'financial projections and revenue growth' or 'security policies')..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 focus:border-indigo-500 rounded-xl py-3.5 pl-12 pr-28 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all font-medium"
              />
              <button
                id="search-submit-btn"
                type="submit"
                disabled={loading || !query.trim()}
                className="absolute right-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
              >
                {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Retrieve"}
              </button>
            </div>

            {/* Quick configurations bar */}
            <div className="flex flex-wrap items-center justify-between gap-4 pt-2 border-t border-slate-900/60 text-xs">
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-1.5 text-slate-400 font-semibold">
                  Type:
                  <select
                    value={searchType}
                    onChange={(e) => setSearchType(e.target.value)}
                    className="bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-slate-200 outline-none cursor-pointer hover:border-slate-700"
                  >
                    <option value="hybrid">Hybrid (RRF Fusion)</option>
                    <option value="semantic">Semantic (pgvector)</option>
                  </select>
                </label>

                <button
                  type="button"
                  onClick={() => setShowFilters(!showFilters)}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded border transition-colors ${
                    showFilters 
                      ? "bg-indigo-950/40 text-indigo-400 border-indigo-800/40" 
                      : "bg-slate-950 text-slate-400 border-slate-800 hover:bg-slate-900"
                  }`}
                >
                  <Sliders className="h-3.5 w-3.5" />
                  Advanced Filters {Object.keys(metaFilters).length > 0 || selectedDocs.length > 0 ? "•" : ""}
                </button>
              </div>

              {latency !== null && (
                <span className="font-mono text-slate-500 font-medium">
                  Search executed in {latency}ms
                </span>
              )}
            </div>

            {/* ⚙️ Expandable Filters Section */}
            {showFilters && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-4 border-t border-slate-900/60 bg-slate-950/20 p-4 rounded-xl space-y-4 md:space-y-0">
                {/* File selectors */}
                <div className="space-y-3">
                  <span className="text-xs text-slate-300 font-bold block">Document Scope</span>
                  <div className="max-h-36 overflow-y-auto border border-slate-800/50 rounded-lg p-2.5 space-y-2.5 bg-slate-950/50">
                    {allDocs.map((doc) => (
                      <label key={doc.id} className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedDocs.includes(doc.id)}
                          onChange={(e) => {
                            if (e.target.checked) setSelectedDocs(prev => [...prev, doc.id]);
                            else setSelectedDocs(prev => prev.filter(id => id !== doc.id));
                          }}
                          className="rounded border-slate-800 text-indigo-600 focus:ring-indigo-500 bg-slate-900 cursor-pointer"
                        />
                        <span className="truncate max-w-[200px]" title={doc.original_filename}>
                          {doc.original_filename}
                        </span>
                      </label>
                    ))}
                    {allDocs.length === 0 && <span className="text-slate-500 block italic py-2">No documents found.</span>}
                  </div>
                </div>

                {/* Metadata & Tag Filters */}
                <div className="space-y-4">
                  {/* Language */}
                  <div className="space-y-2">
                    <span className="text-xs text-slate-300 font-bold block">Language Filter</span>
                    <input
                      type="text"
                      placeholder="e.g. en, fr, es (comma separated)"
                      value={languages.join(", ")}
                      onChange={(e) => setLanguages(e.target.value.split(",").map(s => s.trim()).filter(Boolean))}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs outline-none focus:border-slate-700"
                    />
                  </div>

                  {/* Date range */}
                  <div className="space-y-2">
                    <span className="text-xs text-slate-300 font-bold block">Date Range</span>
                    <div className="flex gap-2">
                      <input
                        type="date"
                        value={startDate}
                        onChange={(e) => setStartDate(e.target.value)}
                        className="w-1/2 bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-[11px] text-slate-300 outline-none"
                      />
                      <input
                        type="date"
                        value={endDate}
                        onChange={(e) => setEndDate(e.target.value)}
                        className="w-1/2 bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-[11px] text-slate-300 outline-none"
                      />
                    </div>
                  </div>
                </div>

                {/* JSON Metadata filter tags insertion */}
                <div className="md:col-span-2 space-y-3 pt-2">
                  <span className="text-xs text-slate-300 font-bold block">Metadata Key-Value Tags Match</span>
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      type="text"
                      placeholder="Key (e.g. department)"
                      value={metaKey}
                      onChange={(e) => setMetaKey(e.target.value)}
                      className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs outline-none max-w-[150px]"
                    />
                    <input
                      type="text"
                      placeholder="Value (e.g. HR)"
                      value={metaVal}
                      onChange={(e) => setMetaVal(e.target.value)}
                      className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs outline-none max-w-[150px]"
                    />
                    <button
                      type="button"
                      onClick={handleAddMeta}
                      className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold rounded-lg transition-colors"
                    >
                      Add Filter
                    </button>
                  </div>
                  {/* Render meta filters */}
                  {Object.keys(metaFilters).length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1.5">
                      {Object.entries(metaFilters).map(([k, v]) => (
                        <span key={k} className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-slate-900 border border-slate-800 text-[10px] text-slate-300">
                          {k}: {v}
                          <button
                            type="button"
                            onClick={() => setMetaFilters(prev => {
                              const copy = { ...prev };
                              delete copy[k];
                              return copy;
                            })}
                            className="text-red-400 hover:text-red-300 font-bold"
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </form>

          {/* 🎚️ Sliders Panel (Top-K / Threshold) */}
          <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Top K */}
            <div className="bg-slate-900/30 border border-slate-900 rounded-xl p-4 space-y-2.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 font-semibold uppercase tracking-wider">Top-K Returns limit</span>
                <span className="text-white font-mono font-bold bg-indigo-950 px-2 py-0.5 rounded border border-indigo-900/50">{topK} chunks</span>
              </div>
              <input
                type="range"
                min="1"
                max="50"
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value))}
                className="w-full accent-indigo-500 h-1 bg-slate-800 rounded-lg cursor-pointer"
              />
              <span className="text-[10px] text-slate-500 block">Controls maximum candidate segment list truncation.</span>
            </div>

            {/* Threshold */}
            <div className="bg-slate-900/30 border border-slate-900 rounded-xl p-4 space-y-2.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 font-semibold uppercase tracking-wider">Similarity Pruning Threshold</span>
                <span className="text-white font-mono font-bold bg-indigo-950 px-2 py-0.5 rounded border border-indigo-900/50">{(threshold).toFixed(2)}</span>
              </div>
              <input
                type="range"
                min="0.0"
                max="1.0"
                step="0.05"
                value={threshold}
                onChange={(e) => setThreshold(parseFloat(e.target.value))}
                className="w-full accent-indigo-500 h-1 bg-slate-800 rounded-lg cursor-pointer"
              />
              <span className="text-[10px] text-slate-500 block">Filters out segments with cosine similarities below target score.</span>
            </div>
          </section>

          {/* 📋 Results Panel */}
          <section className="space-y-4">
            {error && (
              <div className="bg-red-950/20 border border-red-900/50 rounded-xl p-4 flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
                <p className="text-sm text-red-300">{error}</p>
              </div>
            )}

            {loading ? (
              <div className="space-y-4">
                {[1, 2, 3].map((n) => (
                  <div key={n} className="bg-slate-900/20 border border-slate-900/80 rounded-xl p-5 space-y-3 animate-pulse">
                    <div className="h-3.5 bg-slate-800 rounded w-1/4" />
                    <div className="space-y-2">
                      <div className="h-3 bg-slate-800 rounded w-full" />
                      <div className="h-3 bg-slate-800 rounded w-5/6" />
                    </div>
                  </div>
                ))}
              </div>
            ) : results.length > 0 ? (
              <div className="space-y-4">
                {results.map((item, idx) => (
                  <article key={idx} className="bg-slate-900/40 border border-slate-900 hover:border-slate-800 rounded-xl p-5 space-y-4 transition-all">
                    {/* Header: Score / Document info */}
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex items-center gap-2">
                        <span className={`px-2.5 py-0.5 rounded text-[11px] font-bold ${getScoreColor(item.score)}`}>
                          {item.score.toFixed(4)} Cosine
                        </span>
                        <span className="text-xs text-slate-500 font-mono">Rank #{idx + 1}</span>
                      </div>
                      <button
                        onClick={() => router.push(`/documents/${item.document.id}`)}
                        className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1"
                      >
                        <span className="truncate max-w-[200px]" title={item.document.original_filename}>
                          {item.document.original_filename}
                        </span>
                        <ExternalLink className="h-3 w-3" />
                      </button>
                    </div>

                    {/* Highlighted text snippet */}
                    <p className="text-sm text-slate-200 leading-relaxed font-sans bg-slate-950/40 border border-slate-950 rounded-lg p-3.5 relative overflow-hidden">
                      {highlightText(item.chunk.text, query)}
                    </p>

                    {/* Metadata aggregates */}
                    <div className="flex flex-wrap gap-2 text-[10px] text-slate-400 font-mono">
                      <span className="px-2 py-0.5 bg-slate-950 border border-slate-900 rounded">
                        Page {item.chunk.page_number}
                      </span>
                      <span className="px-2 py-0.5 bg-slate-950 border border-slate-900 rounded">
                        {item.chunk.token_count} tokens
                      </span>
                      <span className="px-2 py-0.5 bg-slate-950 border border-slate-900 rounded">
                        Lang: {item.chunk.language}
                      </span>
                      {item.chunk.section_title && (
                        <span className="px-2 py-0.5 bg-slate-950 border border-slate-900 rounded truncate max-w-[200px]" title={item.chunk.section_title}>
                          Section: {item.chunk.section_title}
                        </span>
                      )}
                    </div>
                  </article>
                ))}
                
                {/* Pagination Controls */}
                <div className="flex items-center justify-between pt-4 border-t border-slate-900 text-xs">
                  <button
                    type="button"
                    disabled={page <= 1 || loading}
                    onClick={handlePrevPage}
                    className="px-3.5 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 disabled:opacity-40 disabled:hover:bg-transparent font-semibold transition-all cursor-pointer disabled:cursor-not-allowed text-slate-300"
                  >
                    Previous
                  </button>
                  <span className="text-slate-400 font-medium">
                    Page {page} (Chunks {offset + 1} – {offset + results.length})
                  </span>
                  <button
                    type="button"
                    disabled={results.length < topK || loading}
                    onClick={handleNextPage}
                    className="px-3.5 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 disabled:opacity-40 disabled:hover:bg-transparent font-semibold transition-all cursor-pointer disabled:cursor-not-allowed text-slate-300"
                  >
                    Next
                  </button>
                </div>
              </div>
            ) : (
              <div className="bg-slate-900/10 border border-slate-900 rounded-2xl py-16 px-4 text-center space-y-4">
                <div className="p-4 bg-slate-900/60 rounded-full border border-slate-800 inline-block text-slate-400">
                  <Search className="h-8 w-8" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-base font-bold text-white">No chunks retrieved</h3>
                  <p className="text-xs text-slate-500 max-w-sm mx-auto">
                    Type a search phrase above or adjust your similarity threshold and scope filters to pull documents.
                  </p>
                </div>
              </div>
            )}
          </section>
        </div>

        {/* Right Column: Audit History & Metrics statistics (1 column wide) */}
        <div className="space-y-6">
          
          {/* 📊 Analytics Dashboard */}
          <section className="bg-slate-900/40 border border-slate-900 rounded-2xl p-5 space-y-4">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <BarChart3 className="h-4 w-4" />
              Usage Statistics
            </h3>
            
            {statsLoading ? (
              <div className="space-y-3 py-2 animate-pulse">
                <div className="h-3.5 bg-slate-800 rounded w-3/4" />
                <div className="h-3.5 bg-slate-800 rounded w-1/2" />
              </div>
            ) : stats ? (
              <div className="space-y-4 text-xs font-medium">
                <div className="flex justify-between py-1.5 border-b border-slate-900/60">
                  <span className="text-slate-400">Total Queries Run</span>
                  <span className="text-white font-bold">{stats.total_queries}</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-slate-900/60">
                  <span className="text-slate-400">Avg Database Latency</span>
                  <span className="text-emerald-400 font-mono font-bold">{stats.average_latency_ms}ms</span>
                </div>
                
                {/* Search Type distribution */}
                <div className="space-y-2 pt-1">
                  <span className="text-slate-400 text-[10px] uppercase font-bold block">Engine Allocation</span>
                  <div className="flex gap-1.5 text-[10px]">
                    <div className="flex-1 bg-indigo-950/40 border border-indigo-900/30 p-2 rounded text-center">
                      <span className="text-indigo-400 block font-mono font-bold">
                        {stats.search_type_distribution.HYBRID ?? 0}
                      </span>
                      <span className="text-slate-500 block mt-0.5">Hybrid</span>
                    </div>
                    <div className="flex-1 bg-violet-950/40 border border-violet-900/30 p-2 rounded text-center">
                      <span className="text-violet-400 block font-mono font-bold">
                        {stats.search_type_distribution.SEMANTIC ?? 0}
                      </span>
                      <span className="text-slate-500 block mt-0.5">Semantic</span>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <span className="text-slate-500 block text-xs italic">Analytics unavailable.</span>
            )}
          </section>

          {/* ⏳ Search History Query log */}
          <section className="bg-slate-900/40 border border-slate-900 rounded-2xl p-5 space-y-4">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <History className="h-4 w-4" />
              Recent Searches
            </h3>

            {statsLoading ? (
              <div className="space-y-3 py-2 animate-pulse">
                <div className="h-3 bg-slate-800 rounded w-full" />
                <div className="h-3 bg-slate-800 rounded w-5/6" />
              </div>
            ) : history.length > 0 ? (
              <div className="space-y-2.5 max-h-96 overflow-y-auto pr-1">
                {history.map((log) => (
                  <button
                    key={log.id}
                    onClick={() => handleRerun(log.query_text, log.search_type)}
                    className="w-full text-left bg-slate-950/60 hover:bg-slate-900 border border-slate-900 hover:border-slate-800 rounded-lg p-2.5 space-y-1 text-xs transition-all group block"
                  >
                    <p className="text-slate-200 font-semibold group-hover:text-indigo-400 transition-colors line-clamp-2 pr-4 relative">
                      {log.query_text}
                      <ArrowRight className="h-3.5 w-3.5 text-indigo-500 opacity-0 group-hover:opacity-100 transition-all absolute right-0 top-0.5" />
                    </p>
                    <div className="flex items-center gap-2 text-[10px] text-slate-500 font-mono">
                      <span>{log.search_type}</span>
                      <span>•</span>
                      <span>{log.total_results} matches</span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <span className="text-slate-500 text-xs italic block py-2">No queries logged yet.</span>
            )}
          </section>
        </div>

      </main>
    </div>
  );
}
