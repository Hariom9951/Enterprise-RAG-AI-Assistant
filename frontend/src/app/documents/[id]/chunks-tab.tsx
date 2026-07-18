"use client";

import { useEffect, useState, useCallback } from "react";
import { documentsApi, chunksApi, ChunkResponse, ChunkSummaryResponse } from "@/lib/api";
import { Loader2, Search, Trash2, BookOpen, Layers, Hash, Globe, Clock, ChevronDown, ChevronUp } from "lucide-react";

const CHUNKS_PAGE_SIZE = 5;

// Helper to format duration nicely
function formatReadingTime(seconds: number): string {
  if (seconds < 60) return `${Math.ceil(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.ceil(seconds % 60);
  return `${mins}m ${secs}s`;
}

// ─── Stat Card Component ──────────────────────────────────────────────────────
function ChunkStatCard({ label, value, subtext, icon: Icon, color }: {
  label: string;
  value: string | number;
  subtext?: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}) {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex items-start gap-4">
      <div className={`p-2.5 rounded-lg ${color} shrink-0`}>
        <Icon className="h-5 w-5" />
      </div>
      <div className="space-y-1">
        <span className="text-xs text-slate-400 uppercase font-semibold tracking-wider block">{label}</span>
        <span className="text-xl font-bold text-white block">{value}</span>
        {subtext && <span className="text-[10px] text-slate-500 block">{subtext}</span>}
      </div>
    </div>
  );
}

// ─── Metadata Inspector ───────────────────────────────────────────────────────
function MetadataInspector({ metadata }: { metadata: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-slate-800/60 bg-slate-950/40 rounded-lg overflow-hidden mt-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3.5 py-2 text-xs text-slate-400 hover:text-white bg-slate-950/20 hover:bg-slate-900/40 transition-colors"
      >
        <span className="font-mono">📦 Enrichment Metadata ({Object.keys(metadata).length} keys)</span>
        {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>
      {expanded && (
        <div className="p-3.5 bg-slate-950/80 border-t border-slate-900 font-mono text-[11px] text-slate-300 overflow-x-auto max-h-48">
          <pre>{JSON.stringify(metadata, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

// ─── Chunks Tab View ──────────────────────────────────────────────────────────
export default function ChunksTab({ documentId }: { documentId: string }) {
  const [summary, setSummary] = useState<ChunkSummaryResponse | null>(null);
  const [chunks, setChunks] = useState<ChunkResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingChunks, setLoadingChunks] = useState(false);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setOffset(0); // reset page on search
    }, 400);
    return () => clearTimeout(timer);
  }, [search]);

  // Fetch summary stats
  const fetchSummary = useCallback(async () => {
    try {
      const data = await documentsApi.getChunkSummary(documentId);
      setSummary(data);
    } catch (e: unknown) {
      console.error("Failed to load chunk summary", e);
    }
  }, [documentId]);

  // Fetch list of chunks
  const fetchChunks = useCallback(async () => {
    setLoadingChunks(true);
    try {
      const data = await documentsApi.getChunks(documentId, {
        limit: CHUNKS_PAGE_SIZE,
        offset: offset,
        search: debouncedSearch,
      });
      setChunks(data);
    } catch (e: unknown) {
      const msg = (e as { error?: { message?: string } })?.error?.message ?? "Failed to fetch document chunks.";
      setError(msg);
    } finally {
      setLoadingChunks(false);
      setLoading(false);
    }
  }, [documentId, offset, debouncedSearch]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchSummary();
    }, 0);
    return () => clearTimeout(timer);
  }, [fetchSummary]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchChunks();
    }, 0);
    return () => clearTimeout(timer);
  }, [fetchChunks]);

  // Delete handler
  const handleDeleteChunk = async (chunkId: string) => {
    if (!confirm("Are you sure you want to delete this chunk from the index? This action cannot be undone.")) return;
    setDeletingId(chunkId);
    try {
      await chunksApi.delete(chunkId);
      // Refresh both list and statistics
      await Promise.all([fetchSummary(), fetchChunks()]);
    } catch (e: unknown) {
      const msg = (e as { error?: { message?: string } })?.error?.message ?? "Failed to delete chunk.";
      alert(msg);
    } finally {
      setDeletingId(null);
    }
  };

  if (loading) {
    return (
      <div className="py-12 flex flex-col items-center justify-center text-slate-500 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
        <p className="text-sm">Retrieving document chunks from storage...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-8 text-center bg-red-900/10 border border-red-800/40 rounded-xl p-6">
        <p className="text-red-400 font-medium">{error}</p>
        <button
          onClick={() => { setError(null); setOffset(0); fetchChunks(); }}
          className="mt-4 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-sm transition-colors"
        >
          Try Again
        </button>
      </div>
    );
  }

  const hasNextPage = chunks.length === CHUNKS_PAGE_SIZE;

  return (
    <div className="space-y-8">
      {/* ── Statistics Summary Grid ── */}
      {summary && summary.total_chunks > 0 && (
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <ChunkStatCard
            label="Total Chunks"
            value={summary.total_chunks}
            icon={Layers}
            color="bg-indigo-950 text-indigo-400"
          />
          <ChunkStatCard
            label="Total Tokens"
            value={summary.total_tokens.toLocaleString()}
            subtext={`Avg: ${Math.round(summary.average_chunk_size)} tokens/chunk`}
            icon={Hash}
            color="bg-violet-950 text-violet-400"
          />
          <ChunkStatCard
            label="Reading Time"
            value={formatReadingTime(summary.reading_time_estimate)}
            icon={BookOpen}
            color="bg-emerald-950 text-emerald-400"
          />
          <ChunkStatCard
            label="Languages"
            value={summary.languages.map(l => l.toUpperCase()).join(", ") || "EN"}
            icon={Globe}
            color="bg-amber-950 text-amber-400"
          />
        </section>
      )}

      {/* ── Search Input ── */}
      <section className="relative">
        <Search className="absolute left-3 top-2.5 h-4.5 w-4.5 text-slate-500" />
        <input
          type="text"
          placeholder="Filter chunks by text content..."
          className="w-full bg-slate-900/40 border border-slate-800/80 rounded-xl pl-10 pr-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 transition-all"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </section>

      {/* ── Chunks List ── */}
      <section className="space-y-4">
        {loadingChunks ? (
          <div className="py-12 flex justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-indigo-400" />
          </div>
        ) : chunks.length === 0 ? (
          <div className="py-12 text-center text-slate-500 space-y-1">
            <p className="text-3xl">🧩</p>
            <p className="text-sm font-medium">No chunks found</p>
            <p className="text-xs text-slate-600">
              {debouncedSearch ? "Try adjusting your search criteria." : "Run document processing to indexing chunks."}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {chunks.map((chunk) => (
              <div
                key={chunk.id}
                className="bg-slate-900/30 border border-slate-800/70 hover:border-slate-850/80 rounded-xl p-5 hover:bg-slate-900/40 transition-all duration-200"
              >
                {/* Header info */}
                <div className="flex items-start justify-between gap-4 pb-3 border-b border-slate-850 mb-3.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                      Chunk #{chunk.chunk_index + 1}
                    </span>
                    {chunk.page_number > 0 && (
                      <span className="text-xs text-slate-400 flex items-center gap-1">
                        📄 Page {chunk.page_number}
                      </span>
                    )}
                    {chunk.section_title && (
                      <span className="text-xs text-indigo-400 truncate max-w-xs font-medium" title={chunk.section_title}>
                        🏷️ {chunk.section_title}
                      </span>
                    )}
                  </div>

                  <button
                    onClick={() => handleDeleteChunk(chunk.id)}
                    disabled={deletingId === chunk.id}
                    className="text-slate-500 hover:text-red-400 p-1 rounded hover:bg-red-950/20 transition-colors shrink-0"
                    title="Delete chunk index"
                  >
                    {deletingId === chunk.id ? (
                      <Loader2 className="h-4 w-4 animate-spin text-red-400" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                  </button>
                </div>

                {/* Text Body */}
                <div className="bg-slate-950/40 rounded-lg p-4 font-mono text-sm text-slate-200 leading-relaxed whitespace-pre-wrap select-all">
                  {chunk.text}
                </div>

                {/* Stats / Details */}
                <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mt-4 text-xs text-slate-500 font-medium">
                  <span className="flex items-center gap-1.5">
                    <Layers className="h-3.5 w-3.5 text-indigo-500" />
                    {chunk.token_count.toLocaleString()} tokens
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Hash className="h-3.5 w-3.5 text-violet-500" />
                    {chunk.character_count.toLocaleString()} chars · {chunk.word_count} words
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5 text-emerald-500" />
                    {Math.ceil(chunk.reading_time_estimate)}s read time
                  </span>
                  <span className="text-[10px] font-mono ml-auto truncate" title={`SHA-256 Hash: ${chunk.sha256_hash}`}>
                    Hash: {chunk.sha256_hash.slice(0, 16)}...
                  </span>
                </div>

                {/* Metadata inspector */}
                {chunk.metadata && Object.keys(chunk.metadata).length > 0 && (
                  <MetadataInspector metadata={chunk.metadata} />
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Pagination Buttons ── */}
      {summary && summary.total_chunks > CHUNKS_PAGE_SIZE && (
        <section className="flex items-center justify-between border-t border-slate-900 pt-5">
          <span className="text-xs text-slate-500">
            Showing chunks {offset + 1} - {Math.min(offset + CHUNKS_PAGE_SIZE, summary.total_chunks)} of {summary.total_chunks}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setOffset(prev => Math.max(0, prev - CHUNKS_PAGE_SIZE))}
              disabled={offset === 0 || loadingChunks}
              className="px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 disabled:opacity-40 disabled:hover:bg-slate-900 transition-colors"
            >
              Previous
            </button>
            <button
              onClick={() => setOffset(prev => prev + CHUNKS_PAGE_SIZE)}
              disabled={!hasNextPage || loadingChunks}
              className="px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 disabled:opacity-40 disabled:hover:bg-slate-900 transition-colors"
            >
              Next
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
