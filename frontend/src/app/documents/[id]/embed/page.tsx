"use client";

import { useEffect, useState, useCallback, use } from "react";
import { useRouter } from "next/navigation";
import { documentsApi, DocumentEmbeddingStatusResponse } from "@/lib/api";
import { Loader2, ArrowLeft, Cpu, Hash, Activity, CheckCircle, AlertTriangle, Play } from "lucide-react";

// Helper to format duration nicely
function formatTime(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const mins = Math.floor(sec / 60);
  const secs = Math.ceil(sec % 60);
  return `${mins}m ${secs}s`;
}

// ─── Stat Card Component ──────────────────────────────────────────────────────
function StatusStatCard({ label, value, icon: Icon, color }: {
  label: string;
  value: string | number;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}) {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
      <div className={`p-2.5 rounded-lg ${color} shrink-0`}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <span className="text-xs text-slate-400 uppercase font-semibold tracking-wider block">{label}</span>
        <span className="text-lg font-bold text-white block mt-0.5">{value}</span>
      </div>
    </div>
  );
}

// ─── Main Page Component ──────────────────────────────────────────────────────
export default function EmbeddingStatusPage({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter();
  const resolvedParams = use(params);
  const docId = resolvedParams.id;

  const [status, setStatus] = useState<DocumentEmbeddingStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await documentsApi.getEmbeddingStatus(docId);
      setStatus(data);
      setError(null);
    } catch (e: unknown) {
      const msg = (e as { error?: { message?: string } })?.error?.message ?? "Failed to load embedding status.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [docId]);

  // Initial load
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchStatus();
    }, 0);
    return () => clearTimeout(timer);
  }, [fetchStatus]);

  // Auto-polling for active execution states
  useEffect(() => {
    if (!status) return;
    const activeStates = ["PROCESSING", "QUEUED"];
    if (!activeStates.includes(status.status)) return;

    const interval = setInterval(fetchStatus, 2500);
    return () => clearInterval(interval);
  }, [status, fetchStatus]);

  // Force trigger embedding handler
  const handleTriggerEmbed = async () => {
    setTriggering(true);
    try {
      await documentsApi.embed(docId);
      await fetchStatus();
    } catch (e: unknown) {
      const msg = (e as { error?: { message?: string } })?.error?.message ?? "Failed to queue embedding task.";
      alert(msg);
    } finally {
      setTriggering(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 className="h-10 w-10 animate-spin text-indigo-500 mx-auto" />
          <p className="text-slate-400 text-sm">Querying indexing status...</p>
        </div>
      </div>
    );
  }

  const percentage = status?.percentage_complete ?? 0.0;
  const isCompleted = status?.status === "COMPLETED";
  const isProcessing = status?.status === "PROCESSING";
  const isQueued = status?.status === "QUEUED";
  const isFailed = status?.status === "FAILED";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Header */}
      <header className="border-b border-slate-900 bg-slate-950/80 backdrop-blur sticky top-0 z-50 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center gap-4">
          <button
            onClick={() => router.push(`/documents/${docId}`)}
            className="p-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
            title="Back to Document details"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <h1 className="text-lg font-bold text-white">Vector Ingestion Pipeline</h1>
            <p className="text-xs text-slate-400">Monitor database vectorization progress and schema statistics</p>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 max-w-4xl w-full mx-auto px-6 py-8 space-y-8">
        {error ? (
          <div className="bg-red-950/20 border border-red-900/50 rounded-xl p-5 text-center space-y-4">
            <p className="text-sm text-red-400">{error}</p>
            <button
              onClick={() => { setError(null); setLoading(true); fetchStatus(); }}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-semibold transition-colors"
            >
              Try Again
            </button>
          </div>
        ) : (
          <>
            {/* ── Status Banner ── */}
            <section className="bg-slate-900/40 border border-slate-800 rounded-2xl p-6 md:p-8 flex flex-col md:flex-row items-center gap-8">
              {/* Progress Circle Ring */}
              <div className="relative h-32 w-32 shrink-0 flex items-center justify-center">
                {/* Outer Track */}
                <svg className="absolute transform -rotate-90 w-full h-full">
                  <circle
                    cx="64"
                    cy="64"
                    r="54"
                    className="stroke-slate-800"
                    strokeWidth="10"
                    fill="transparent"
                  />
                  <circle
                    cx="64"
                    cy="64"
                    r="54"
                    className="stroke-indigo-500 transition-all duration-500 ease-out"
                    strokeWidth="10"
                    fill="transparent"
                    strokeDasharray={2 * Math.PI * 54}
                    strokeDashoffset={2 * Math.PI * 54 * (1 - percentage / 100)}
                    strokeLinecap="round"
                  />
                </svg>
                <div className="text-center">
                  <span className="text-2xl font-bold text-white block">{Math.round(percentage)}%</span>
                  <span className="text-[10px] text-slate-400 block uppercase tracking-wider font-semibold">Indexed</span>
                </div>
              </div>

              {/* Status details */}
              <div className="flex-1 text-center md:text-left space-y-3">
                <div className="flex flex-col md:flex-row md:items-center gap-3">
                  <h2 className="text-xl font-bold text-white">
                    {isCompleted && "Vector Index Complete"}
                    {isProcessing && "Vectorizing Chunks..."}
                    {isQueued && "Task Queued in Redis"}
                    {isFailed && "Vectorization Failed"}
                  </h2>
                  <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold self-center md:self-auto ${
                    isCompleted ? "bg-green-950 text-green-400" :
                    isProcessing ? "bg-indigo-950 text-indigo-400 animate-pulse" :
                    isQueued ? "bg-blue-950 text-blue-400" :
                    "bg-red-950 text-red-400"
                  }`}>
                    {isCompleted && <CheckCircle className="h-3.5 w-3.5" />}
                    {isProcessing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    {isQueued && <Activity className="h-3.5 w-3.5" />}
                    {isFailed && <AlertTriangle className="h-3.5 w-3.5" />}
                    {status?.status}
                  </span>
                </div>

                <p className="text-sm text-slate-400 leading-relaxed max-w-xl">
                  {isCompleted && "All semantic segments for this document have been converted to high-dimensional embeddings and successfully indexed inside PostgreSQL pgvector."}
                  {isProcessing && `SentenceTransformers is processing batch chunks of text. Remaining segments: ${status?.remaining_chunks}. Please hold on.`}
                  {isQueued && "Background Celery task has been scheduled and is waiting for an idle worker thread to begin embedding generation."}
                  {isFailed && `An error occurred during embedding: ${status?.error_message ?? "Task execution abort."}`}
                </p>

                {/* Control Action Buttons */}
                <div className="pt-2 flex flex-wrap justify-center md:justify-start gap-3">
                  <button
                    onClick={handleTriggerEmbed}
                    disabled={triggering || isProcessing || isQueued}
                    className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 text-white rounded-lg text-xs font-semibold transition-colors"
                  >
                    {triggering ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Play className="h-3.5 w-3.5 fill-current" />
                    )}
                    {isCompleted ? "Re-generate Embeddings" : "Start Embedding Pipeline"}
                  </button>
                  <button
                    onClick={() => router.push(`/documents/${docId}`)}
                    className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-slate-300 rounded-lg text-xs font-semibold transition-colors"
                  >
                    Back to Details
                  </button>
                </div>
              </div>
            </section>

            {/* ── Statistics Cards Grid ── */}
            <section className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <StatusStatCard
                label="Model Configured"
                value={status?.model_used.split("/").pop() ?? "bge-base-en-v1.5"}
                icon={Cpu}
                color="bg-violet-950 text-violet-400"
              />
              <StatusStatCard
                label="Vector Dimensions"
                value={`${status?.vector_dimension} float32`}
                icon={Hash}
                color="bg-emerald-950 text-emerald-400"
              />
              <StatusStatCard
                label="Total Execution Time"
                value={formatTime(status?.processing_time_ms ?? 0)}
                icon={Activity}
                color="bg-amber-950 text-amber-400"
              />
            </section>

            {/* ── Detailed Progress stats list ── */}
            <section className="bg-slate-900/20 border border-slate-900 rounded-xl p-5 space-y-4">
              <h3 className="text-sm font-semibold text-white">Pipeline Execution Details</h3>
              <div className="space-y-3.5 font-mono text-xs">
                <div className="flex justify-between py-1.5 border-b border-slate-900">
                  <span className="text-slate-400">Total Extracted Segments</span>
                  <span className="text-slate-200">{(status?.processed_chunks ?? 0) + (status?.remaining_chunks ?? 0)} chunks</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-slate-900">
                  <span className="text-slate-400">Embedded Chunks</span>
                  <span className="text-emerald-400">{status?.processed_chunks} chunks</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-slate-900">
                  <span className="text-slate-400">Remaining Chunks</span>
                  <span className={status?.remaining_chunks && status.remaining_chunks > 0 ? "text-indigo-400" : "text-slate-500"}>
                    {status?.remaining_chunks} chunks
                  </span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-slate-900">
                  <span className="text-slate-400">Database Vector Index</span>
                  <span className="text-slate-200">PostgreSQL pgvector (HNSW cosine_ops)</span>
                </div>
                <div className="flex justify-between py-1.5">
                  <span className="text-slate-400">Pipeline Schema Version</span>
                  <span className="text-slate-500">v1.0.0</span>
                </div>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
