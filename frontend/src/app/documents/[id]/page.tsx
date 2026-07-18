"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { documentsApi, ProcessedDocumentResponse, DocumentResponse } from "@/lib/api";

// ─── Status badge helper ──────────────────────────────────────────────────────
const STATUS_STYLES: Record<string, { bg: string; text: string; dot: string; label: string }> = {
  UPLOADED:   { bg: "bg-slate-800",  text: "text-slate-300",  dot: "bg-slate-400",  label: "Uploaded"   },
  QUEUED:     { bg: "bg-blue-900",   text: "text-blue-300",   dot: "bg-blue-400",   label: "Queued"     },
  PROCESSING: { bg: "bg-yellow-900", text: "text-yellow-300", dot: "bg-yellow-400", label: "Processing" },
  PROCESSED:  { bg: "bg-green-900",  text: "text-green-300",  dot: "bg-green-400",  label: "Processed"  },
  COMPLETED:  { bg: "bg-green-900",  text: "text-green-300",  dot: "bg-green-400",  label: "Completed"  },
  FAILED:     { bg: "bg-red-900",    text: "text-red-300",    dot: "bg-red-400",    label: "Failed"     },
};

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES["UPLOADED"];
  const isActive = ["QUEUED", "PROCESSING"].includes(status);
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${s.bg} ${s.text}`}>
      <span className={`w-2 h-2 rounded-full ${s.dot} ${isActive ? "animate-pulse" : ""}`} />
      {s.label}
    </span>
  );
}

// ─── Stat card ────────────────────────────────────────────────────────────────
function StatCard({ label, value, icon }: { label: string; value: string | number; icon: string }) {
  return (
    <div className="bg-slate-800/60 border border-slate-700/50 rounded-xl p-4 flex flex-col gap-1">
      <span className="text-2xl">{icon}</span>
      <span className="text-2xl font-bold text-white">{value.toLocaleString()}</span>
      <span className="text-xs text-slate-400 uppercase tracking-wide">{label}</span>
    </div>
  );
}

// ─── Language flag / code ─────────────────────────────────────────────────────
const LANG_NAMES: Record<string, string> = {
  en: "English", fr: "French", de: "German", es: "Spanish",
  it: "Italian", pt: "Portuguese", nl: "Dutch", ru: "Russian",
  zh: "Chinese", ja: "Japanese", ko: "Korean", ar: "Arabic",
  und: "Undetermined",
};

// ─── Main page ────────────────────────────────────────────────────────────────
export default function DocumentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const docId = params.id as string;

  const [doc, setDoc] = useState<DocumentResponse | null>(null);
  const [processed, setProcessed] = useState<ProcessedDocumentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const TERMINAL_STATUSES = ["PROCESSED", "FAILED", "COMPLETED"];
  const isTerminal = doc ? TERMINAL_STATUSES.includes(doc.processing_status) : false;

  const fetchData = useCallback(async () => {
    try {
      const [docData, textData] = await Promise.all([
        documentsApi.get(docId),
        documentsApi.getText(docId),
      ]);
      setDoc(docData);
      setProcessed(textData);
    } catch (e: unknown) {
      const msg = (e as { error?: { message?: string } })?.error?.message ?? "Failed to load document.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [docId]);

  // Initial load + polling for non-terminal statuses
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (isTerminal || loading || error) return;
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [isTerminal, loading, error, fetchData]);

  // ── Render states ────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="w-12 h-12 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-slate-400">Loading document…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="text-4xl">⚠️</div>
          <p className="text-red-400">{error}</p>
          <button onClick={() => router.back()} className="text-indigo-400 hover:text-indigo-300 underline text-sm">
            ← Go back
          </button>
        </div>
      </div>
    );
  }

  const langName = processed ? (LANG_NAMES[processed.language] ?? processed.language.toUpperCase()) : "—";
  const formatBytes = (n: number) =>
    n >= 1_048_576 ? `${(n / 1_048_576).toFixed(1)} MB` : n >= 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n} B`;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* ── Top nav ── */}
      <header className="border-b border-slate-800 bg-slate-900/70 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center gap-4">
          <button
            onClick={() => router.push("/documents")}
            className="text-slate-400 hover:text-white transition-colors"
          >
            ← Documents
          </button>
          <span className="text-slate-600">/</span>
          <span className="text-white font-medium truncate max-w-xs">{doc?.original_filename}</span>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10 space-y-8">

        {/* ── Document header ── */}
        <section className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-6 space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-white">{doc?.original_filename}</h1>
              <p className="text-slate-400 text-sm mt-1">
                {doc?.mime_type} · {formatBytes(doc?.file_size ?? 0)} ·{" "}
                Uploaded {new Date(doc?.created_at ?? "").toLocaleDateString()}
              </p>
            </div>
            {doc && <StatusBadge status={doc.processing_status} />}
          </div>

          {doc && !isTerminal && (
            <div className="flex items-center gap-2 text-sm text-yellow-400 bg-yellow-900/20 border border-yellow-800/40 rounded-lg px-4 py-2">
              <span className="w-2 h-2 bg-yellow-400 rounded-full animate-pulse" />
              Document is being processed… refreshing automatically.
            </div>
          )}

          {doc?.processing_status === "FAILED" && (
            <div className="text-sm text-red-400 bg-red-900/20 border border-red-800/40 rounded-lg px-4 py-2">
              ⚠ Processing failed. Please re-upload the document.
            </div>
          )}
        </section>

        {/* ── Statistics ── */}
        {processed && (
          <section className="space-y-4">
            <h2 className="text-lg font-semibold text-white">Extraction Statistics</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <StatCard icon="📄" label="Pages" value={processed.page_count} />
              <StatCard icon="📝" label="Words" value={processed.word_count} />
              <StatCard icon="🔤" label="Characters" value={processed.character_count} />
              <StatCard icon="🌐" label="Language" value={langName} />
            </div>
            <div className="bg-slate-800/40 border border-slate-700/40 rounded-xl px-4 py-3 flex items-center justify-between text-sm">
              <span className="text-slate-400">Extraction time</span>
              <span className="text-white font-mono">{processed.processing_time.toFixed(3)}s</span>
            </div>
          </section>
        )}

        {/* ── Text preview ── */}
        {processed && (
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Text Preview</h2>
              {processed.is_truncated && (
                <span className="text-xs text-slate-500 bg-slate-800 px-2 py-1 rounded-full">
                  First 500 chars shown
                </span>
              )}
            </div>
            <div className="bg-slate-900 border border-slate-700/50 rounded-xl p-5">
              <pre className="text-sm text-slate-300 whitespace-pre-wrap font-mono leading-relaxed">
                {processed.preview}
              </pre>
              {processed.is_truncated && (
                <p className="text-xs text-slate-500 mt-3 border-t border-slate-700/50 pt-3">
                  … {(processed.character_count - 500).toLocaleString()} more characters not shown
                </p>
              )}
            </div>
          </section>
        )}

        {/* ── Not yet processed placeholder ── */}
        {!processed && isTerminal && doc?.processing_status !== "FAILED" && (
          <section className="text-center py-16 text-slate-500 space-y-2">
            <p className="text-4xl">📂</p>
            <p>No extracted text available.</p>
          </section>
        )}
      </main>
    </div>
  );
}
