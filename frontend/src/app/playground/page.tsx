"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  ragApi,
  documentsApi,
  DocumentResponse,
  RAGQueryResponse,
  RAGStatisticsResponse,
  RAGModelItem,
  SearchFilters,
} from "@/lib/api";
import {
  Loader2,
  Send,
  Sliders,
  BarChart3,
  AlertCircle,
  BookOpen,
  Clock,
  Hash,
  Cpu,
  Sparkles,
  ExternalLink,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import Navigation from "@/components/Navigation";
import { renderMarkdown } from "@/lib/markdown";

export default function RAGPlaygroundPage() {
  const router = useRouter();

  // Search parameters
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);
  const [threshold, setThreshold] = useState(0.0);
  const [useReranker, setUseReranker] = useState(true);
  const [provider, setProvider] = useState("gemini");
  const [model, setModel] = useState("gemini-3.5-flash");

  // Filtering criteria
  const [allDocs, setAllDocs] = useState<DocumentResponse[]>([]);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [languages, setLanguages] = useState<string[]>([]);
  const [metaKey, setMetaKey] = useState("");
  const [metaVal, setMetaVal] = useState("");
  const [metaFilters, setMetaFilters] = useState<Record<string, string>>({});

  // Operational states
  const [response, setResponse] = useState<RAGQueryResponse | null>(null);
  const [stats, setStats] = useState<RAGStatisticsResponse | null>(null);
  const [models, setModels] = useState<RAGModelItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [statsLoading, setStatsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);

  // References for cited highlighting
  const chunkRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const [highlightedCitation, setHighlightedCitation] = useState<number | null>(null);

  // Load models, documents, and user statistics on startup
  const loadInitialData = useCallback(async () => {
    try {
      const docList = await documentsApi.list({ limit: 100 });
      setAllDocs(docList);
      
      const modelList = await ragApi.getModels();
      setModels(modelList);
      
      const statsObj = await ragApi.getStatistics();
      setStats(statsObj);
    } catch (e) {
      console.error("Failed to load playground assets", e);
    } finally {
      setStatsLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadInitialData();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadInitialData]);

  // Loading animation lifecycle steps
  useEffect(() => {
    if (!loading) {
      setLoadingStep(0);
      return;
    }
    const interval = setInterval(() => {
      setLoadingStep((prev) => (prev < 3 ? prev + 1 : prev));
    }, 1200);
    return () => clearInterval(interval);
  }, [loading]);

  const handleQuery = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError(null);
    setResponse(null);
    setLoadingStep(1);

    try {
      const filtersObj: SearchFilters = {};
      if (selectedDocs.length > 0) filtersObj.document_ids = selectedDocs;
      if (languages.length > 0) filtersObj.languages = languages;
      if (Object.keys(metaFilters).length > 0) filtersObj.metadata = metaFilters;

      const payload = {
        question: question.trim(),
        top_k: topK,
        threshold: threshold,
        use_reranker: useReranker,
        provider: provider,
        model: model,
        filters: Object.keys(filtersObj).length > 0 ? filtersObj : undefined,
      };

      const result = await ragApi.query(payload);
      setResponse(result);

      // Refresh RAG usage stats
      const statsObj = await ragApi.getStatistics();
      setStats(statsObj);
    } catch (err: unknown) {
      const errorResponse = err as { error?: { message?: string } } | undefined;
      setError(errorResponse?.error?.message ?? "Failed to compile grounded answer. Check API keys.");
    } finally {
      setLoading(false);
    }
  };

  const handleAddMeta = () => {
    if (!metaKey.trim() || !metaVal.trim()) return;
    setMetaFilters((prev) => ({ ...prev, [metaKey.trim()]: metaVal.trim() }));
    setMetaKey("");
    setMetaVal("");
  };

  // Scroll to source chunk element and highlight it
  const handleScrollToCitation = (index: number) => {
    const el = chunkRefs.current[index];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setHighlightedCitation(index);
      setTimeout(() => setHighlightedCitation(null), 3000);
    }
  };

  // Formats text, wrapping raw [1] citation tags in interactive rounded badges
  const renderFormattedAnswer = (text: string) => {
    if (!text) return null;
    const parts = text.split(/(\[\d+\])/g);
    return (
      <p className="text-sm leading-relaxed text-slate-200">
        {parts.map((part, index) => {
          const match = part.match(/^\[(\d+)\]$/);
          if (match) {
            const citeIdx = parseInt(match[1]);
            return (
              <span
                key={index}
                onClick={() => handleScrollToCitation(citeIdx)}
                className="mx-0.5 inline-flex items-center justify-center px-1.5 py-0.5 text-[10px] font-mono font-bold bg-indigo-500/25 hover:bg-indigo-500/40 text-indigo-300 border border-indigo-500/30 rounded cursor-pointer transition-colors select-none"
                title={`Jump to Source Chunk [${citeIdx}]`}
              >
                [{citeIdx}]
              </span>
            );
          }
          return part;
        })}
      </p>
    );
  };

  const getConfidenceLevel = (score: number) => {
    if (score >= 0.75) return { text: "High Confidence", color: "text-emerald-400 bg-emerald-950/40 border-emerald-800/40" };
    if (score >= 0.5) return { text: "Moderate Confidence", color: "text-blue-400 bg-blue-950/40 border-blue-800/40" };
    return { text: "Low Confidence", color: "text-slate-400 bg-slate-900 border-slate-800" };
  };

  return (
    <div className="relative min-h-screen bg-slate-950 text-slate-100 selection:bg-indigo-500/30 selection:text-indigo-200 pl-0 md:pl-64">
      <Navigation />
      {/* Background radial glow */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#0f172a_1px,transparent_1px),linear-gradient(to_bottom,#0f172a_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] opacity-20 pointer-events-none" />
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-indigo-500/5 blur-[150px] rounded-full pointer-events-none" />

      {/* Main Grid console */}
      <main className="mx-auto max-w-7xl px-6 py-8 grid grid-cols-1 lg:grid-cols-4 gap-8 relative z-10">
        
        {/* Left Side: Parameters and inputs (3 cols) */}
        <div className="lg:col-span-3 space-y-6">
          
          {/* Top aggregation stats */}
          {!statsLoading && stats && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-slate-900/40 border border-slate-900 rounded-xl p-4 flex items-center gap-3.5">
                <div className="p-2 bg-indigo-950 text-indigo-400 border border-indigo-900/40 rounded-lg">
                  <Cpu className="h-4.5 w-4.5" />
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 uppercase font-semibold tracking-wide block">RAG Query Runs</span>
                  <span className="text-lg font-bold text-white block">{stats.total_queries} queries</span>
                </div>
              </div>
              <div className="bg-slate-900/40 border border-slate-900 rounded-xl p-4 flex items-center gap-3.5">
                <div className="p-2 bg-emerald-950 text-emerald-400 border border-emerald-900/40 rounded-lg">
                  <Clock className="h-4.5 w-4.5" />
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 uppercase font-semibold tracking-wide block">Avg Latency</span>
                  <span className="text-lg font-bold text-white block">{stats.average_latency_ms} ms</span>
                </div>
              </div>
              <div className="bg-slate-900/40 border border-slate-900 rounded-xl p-4 flex items-center gap-3.5">
                <div className="p-2 bg-blue-950 text-blue-400 border border-blue-900/40 rounded-lg">
                  <Hash className="h-4.5 w-4.5" />
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 uppercase font-semibold tracking-wide block">Tokens Consumed</span>
                  <span className="text-lg font-bold text-white block">{stats.total_tokens_used.toLocaleString()} tokens</span>
                </div>
              </div>
            </div>
          )}

          {/* RAG query prompt form */}
          <form onSubmit={handleQuery} className="bg-slate-900/40 border border-slate-900 rounded-2xl p-5 space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Enter Natural Language Question</label>
              <div className="relative flex items-center">
                <input
                  type="text"
                  placeholder="Ask a question grounded in your document base (e.g., 'What is our Q3 revenue forecast?')..."
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 focus:border-indigo-500 rounded-xl py-4 pl-4 pr-16 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all font-medium"
                />
                <button
                  type="submit"
                  disabled={loading || !question.trim()}
                  className="absolute right-2.5 p-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white rounded-lg transition-colors"
                >
                  <Send className="h-4.5 w-4.5" />
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-4 pt-2 border-t border-slate-900/60 text-xs">
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-1.5 text-slate-400 font-semibold">
                  LLM Provider:
                  <select
                    value={provider}
                    onChange={(e) => {
                      setProvider(e.target.value);
                      setModel(e.target.value === "gemini" ? "gemini-3.5-flash" : e.target.value === "openai" ? "gpt-4o-mini" : "llama3");
                    }}
                    className="bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-slate-200 outline-none cursor-pointer hover:border-slate-700 font-medium"
                  >
                    <option value="gemini">Google Gemini</option>
                    <option value="openai">OpenAI GPT</option>
                    <option value="ollama">Local Ollama</option>
                  </select>
                </label>

                <label className="flex items-center gap-1.5 text-slate-400 font-semibold">
                  Model:
                  <select
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    className="bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-slate-200 outline-none cursor-pointer hover:border-slate-700 font-medium"
                  >
                    {provider === "gemini" && (
                      <>
                        <option value="gemini-3.5-flash">gemini-3.5-flash (default)</option>
                        <option value="gemini-2.5-pro">gemini-2.5-pro</option>
                      </>
                    )}
                    {provider === "openai" && (
                      <>
                        <option value="gpt-4o-mini">gpt-4o-mini (default)</option>
                        <option value="gpt-4o">gpt-4o</option>
                      </>
                    )}
                    {provider === "ollama" && (
                      <>
                        <option value="llama3">llama3</option>
                        <option value="mistral">mistral</option>
                      </>
                    )}
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
                  Context Filters {selectedDocs.length > 0 ? "•" : ""}
                </button>
              </div>
            </div>

            {/* Expandable Advanced Document Filters */}
            {showFilters && (
              <div className="bg-slate-950/40 border border-slate-900/80 rounded-xl p-4 space-y-4 animate-fadeIn">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide block">Limit Search to Documents</span>
                    <div className="max-h-28 overflow-y-auto border border-slate-900 rounded-lg p-2.5 space-y-1 bg-slate-950/60">
                      {allDocs.map((doc) => (
                        <label key={doc.id} className="flex items-center gap-2 text-xs text-slate-300 hover:text-white cursor-pointer select-none">
                          <input
                            type="checkbox"
                            checked={selectedDocs.includes(doc.id)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedDocs(prev => [...prev, doc.id]);
                              } else {
                                setSelectedDocs(prev => prev.filter(id => id !== doc.id));
                              }
                            }}
                            className="rounded border-slate-800 text-indigo-600 focus:ring-0 focus:ring-offset-0 accent-indigo-600"
                          />
                          <span className="truncate">{doc.original_filename}</span>
                        </label>
                      ))}
                      {allDocs.length === 0 && <p className="text-[11px] text-slate-600 py-2">No documents indexed in storage.</p>}
                    </div>
                  </div>

                  {/* Metadata Tag Filters */}
                  <div className="space-y-2">
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide block">Metadata Key-Value Tag Filtering</span>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        placeholder="Key (e.g. priority)"
                        value={metaKey}
                        onChange={(e) => setMetaKey(e.target.value)}
                        className="bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs w-1/2 focus:outline-none focus:border-slate-700"
                      />
                      <input
                        type="text"
                        placeholder="Value (e.g. high)"
                        value={metaVal}
                        onChange={(e) => setMetaVal(e.target.value)}
                        className="bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs w-1/2 focus:outline-none focus:border-slate-700"
                      />
                      <button
                        type="button"
                        onClick={handleAddMeta}
                        className="bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[10px] font-bold px-2 rounded cursor-pointer shrink-0 text-slate-300"
                      >
                        Add
                      </button>
                    </div>
                    {Object.keys(metaFilters).length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pt-2.5">
                        {Object.entries(metaFilters).map(([k, v]) => (
                          <span key={k} className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-slate-900 border border-slate-800 text-[10px] font-mono rounded text-slate-400">
                            {k}:{v}
                            <button
                              type="button"
                              onClick={() => {
                                const newFilters = { ...metaFilters };
                                delete newFilters[k];
                                setMetaFilters(newFilters);
                              }}
                              className="text-[10px] text-red-500 font-bold hover:text-red-400"
                            >
                              ×
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </form>

          {/* RAG response answers output */}
          <section className="space-y-4">
            {error && (
              <div className="bg-red-950/20 border border-red-900/50 rounded-xl p-4 flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
                <p className="text-sm text-red-300">{error}</p>
              </div>
            )}

            {/* Stepped loading indicator panel */}
            {loading && (
              <div className="bg-slate-900/30 border border-slate-900/80 rounded-2xl p-8 flex flex-col items-center justify-center text-center space-y-5">
                <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
                <div className="space-y-1.5">
                  <p className="text-sm font-semibold text-white">Grounding Query Answer...</p>
                  <div className="text-xs text-slate-500 font-mono space-y-1">
                    <p className={loadingStep >= 1 ? "text-indigo-400" : "opacity-40"}>
                      {loadingStep >= 1 ? "✓" : "○"} Step 1: Preprocessing & embedding query
                    </p>
                    <p className={loadingStep >= 2 ? "text-indigo-400" : "opacity-40"}>
                      {loadingStep >= 2 ? "✓" : "○"} Step 2: Retrieving context segments from pgvector
                    </p>
                    <p className={loadingStep >= 3 ? "text-indigo-400" : "opacity-40"}>
                      {loadingStep >= 3 ? "✓" : "○"} Step 3: Generating cited answer from {provider.toUpperCase()}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* RAG Query Answer Display card */}
            {!loading && response && (
              <div className="space-y-6">
                <article className="bg-slate-900/40 border border-slate-900 rounded-2xl p-6 space-y-5">
                  <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-900/60 pb-4">
                    <div className="flex items-center gap-2">
                      <span className={`px-2.5 py-0.5 rounded text-[11px] font-bold border ${getConfidenceLevel(response.confidence_score).color}`}>
                        {getConfidenceLevel(response.confidence_score).text} ({(response.confidence_score * 100).toFixed(0)}%)
                      </span>
                      <span className="text-xs text-slate-500 font-mono">Model: {response.model_name}</span>
                    </div>

                    <div className="flex items-center gap-3 text-[10px] text-slate-500 font-mono">
                      <span>LLM Latency: {response.latency.llm_ms}ms</span>
                      <span>•</span>
                      <span>Total: {response.latency.total_ms}ms</span>
                    </div>
                  </div>

                  <div className="prose prose-invert max-w-none">
                    {renderMarkdown(response.answer, handleScrollToCitation)}
                  </div>

                  <div className="flex flex-wrap gap-4 pt-3 border-t border-slate-900/60 text-[10px] text-slate-400 font-mono">
                    <div>
                      <span className="text-slate-500">Prompt: </span>
                      <span className="text-white font-bold">{response.tokens_used.prompt_tokens}</span>
                    </div>
                    <div>
                      <span className="text-slate-500">Completion: </span>
                      <span className="text-white font-bold">{response.tokens_used.completion_tokens}</span>
                    </div>
                    <div>
                      <span className="text-slate-500">Total: </span>
                      <span className="text-white font-bold">{response.tokens_used.total_tokens}</span>
                    </div>
                  </div>
                </article>

                {/* Grounding Source references list */}
                {response.citations.length > 0 && (
                  <section className="space-y-3.5">
                    <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Grounding Source References</h3>
                    <div className="space-y-3">
                      {response.citations.map((item) => (
                        <div
                          key={item.citation_index}
                          ref={(el) => { chunkRefs.current[item.citation_index] = el; }}
                          className={`bg-slate-950/60 border rounded-xl p-4 space-y-3 transition-all duration-300 ${
                            highlightedCitation === item.citation_index
                              ? "border-indigo-500 bg-indigo-950/10 shadow-lg shadow-indigo-500/5 scale-[1.01]"
                              : "border-slate-900"
                          }`}
                        >
                          <div className="flex items-center justify-between text-xs gap-4">
                            <div className="flex items-center gap-2">
                              <span className="w-5 h-5 rounded bg-indigo-950 text-indigo-400 border border-indigo-900/40 flex items-center justify-center font-mono font-bold text-[10px]">
                                {item.citation_index}
                              </span>
                              <span className="text-slate-500 font-mono">Similarity Score: {item.score.toFixed(4)}</span>
                            </div>
                            <button
                              onClick={() => router.push(`/documents/${item.document_id}`)}
                              className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1.5"
                            >
                              <span className="truncate max-w-[200px]" title={item.document_title}>
                                {item.document_title}
                              </span>
                              <ExternalLink className="h-3 w-3" />
                            </button>
                          </div>

                          <p className="text-xs text-slate-300 leading-relaxed font-sans bg-slate-900/30 border border-slate-900/60 rounded-lg p-3">
                            {item.text}
                          </p>

                          <div className="flex gap-2 text-[9px] text-slate-500 font-mono">
                            <span className="px-2 py-0.5 bg-slate-900 border border-slate-800/80 rounded">
                              Page {item.page_number}
                            </span>
                            {item.section_title && (
                              <span className="px-2 py-0.5 bg-slate-900 border border-slate-800/80 rounded truncate max-w-[200px]">
                                Section: {item.section_title}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {/* All Retrieved context chunks list */}
                {response.retrieved_chunks && response.retrieved_chunks.length > 0 && (
                  <section className="space-y-3.5 mt-6">
                    <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">All Retrieved Context Chunks</h3>
                    <div className="space-y-3">
                      {response.retrieved_chunks.map((item, idx) => {
                        const isCited = response.citations.some(c => c.chunk_id === item.chunk_id);
                        return (
                          <div
                            key={item.chunk_id || idx}
                            className={`bg-slate-900/20 border rounded-xl p-4 space-y-3 transition-all duration-300 ${
                              isCited ? "border-indigo-500/40 bg-indigo-950/5 shadow-md shadow-indigo-500/2" : "border-slate-900"
                            }`}
                          >
                            <div className="flex items-center justify-between text-xs gap-4">
                              <div className="flex items-center gap-2">
                                <span className={`px-2 py-0.5 rounded text-[9px] font-bold border ${
                                  isCited ? "bg-indigo-950/60 border-indigo-800 text-indigo-400" : "bg-slate-900 border-slate-800 text-slate-500"
                                }`}>
                                  {isCited ? "Cited" : "Retrieved (Pruned)"}
                                </span>
                                <span className="text-slate-500 font-mono font-semibold">Similarity: {item.score.toFixed(4)}</span>
                              </div>
                              <button
                                onClick={() => router.push(`/documents/${item.document_id}`)}
                                className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1.5"
                              >
                                <span className="truncate max-w-[200px]" title={item.document_title}>
                                  {item.document_title}
                                </span>
                                <ExternalLink className="h-3 w-3" />
                              </button>
                            </div>

                            <p className="text-xs text-slate-400 leading-relaxed font-sans bg-slate-900/10 border border-slate-900/40 rounded-lg p-3">
                              {item.text}
                            </p>

                            <div className="flex gap-2 text-[9px] text-slate-500 font-mono">
                              <span className="px-2 py-0.5 bg-slate-900 border border-slate-800/80 rounded">
                                Page {item.page_number}
                              </span>
                              {item.section_title && (
                                <span className="px-2 py-0.5 bg-slate-900 border border-slate-800/80 rounded truncate max-w-[200px]">
                                  Section: {item.section_title}
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </section>
                )}
              </div>
            )}

            {/* Empty state instruction panel */}
            {!loading && !response && !error && (
              <div className="bg-slate-900/10 border border-slate-900 rounded-2xl p-12 text-center text-slate-500 space-y-4">
                <div className="w-12 h-12 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center mx-auto">
                  <BookOpen className="h-5 w-5 text-slate-400" />
                </div>
                <div className="max-w-md mx-auto space-y-1">
                  <p className="text-sm font-semibold text-slate-300">Playground Console Active</p>
                  <p className="text-xs text-slate-500">
                    Input a question in the prompt bar above to retrieve relevant vector contexts and generate citations.
                  </p>
                </div>
              </div>
            )}
          </section>
        </div>

        {/* Right Side Column: Config Sidebar Controls (1 col) */}
        <div className="space-y-6">
          <div className="bg-slate-900/40 border border-slate-900 rounded-2xl p-5 space-y-5">
            <h2 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
              <Sliders className="h-4 w-4 text-indigo-400" />
              Engine Configuration
            </h2>

            {/* Top-K Return Slider */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 font-medium">Context Count (Top-K)</span>
                <span className="text-white font-mono font-bold bg-indigo-950 px-2 py-0.5 rounded border border-indigo-900/50">
                  {topK}
                </span>
              </div>
              <input
                type="range"
                min="1"
                max="25"
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value))}
                className="w-full accent-indigo-500 h-1 bg-slate-800 rounded-lg cursor-pointer"
              />
              <span className="text-[10px] text-slate-500 block leading-normal">
                Adjusts maximum document segment chunks parsed to the LLM prompt.
              </span>
            </div>

            {/* Threshold Slider */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 font-medium">Pruning Threshold</span>
                <span className="text-white font-mono font-bold bg-indigo-950 px-2 py-0.5 rounded border border-indigo-900/50">
                  {threshold.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                min="0.0"
                max="0.9"
                step="0.05"
                value={threshold}
                onChange={(e) => setThreshold(parseFloat(e.target.value))}
                className="w-full accent-indigo-500 h-1 bg-slate-800 rounded-lg cursor-pointer"
              />
              <span className="text-[10px] text-slate-500 block leading-normal">
                Discards segments whose semantic similarities fall below target score.
              </span>
            </div>

            {/* Reranker Toggle */}
            <div className="flex items-center justify-between pt-2 border-t border-slate-900/60">
              <div className="space-y-0.5">
                <span className="text-xs font-semibold text-slate-300 block">Freshness Reranker</span>
                <span className="text-[10px] text-slate-500 block">Boosts fresh, priority docs.</span>
              </div>
              <label className="relative inline-flex items-center cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={useReranker}
                  onChange={(e) => setUseReranker(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-slate-300 after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600 peer-checked:after:bg-white" />
              </label>
            </div>
          </div>
        </div>

      </main>
    </div>
  );
}
