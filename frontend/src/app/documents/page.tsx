"use client";

/**
 * Enterprise RAG AI Assistant — Document Management Dashboard
 * ==========================================================
 * Provides a production-grade interface for uploading documents via
 * drag-and-drop, listing metadata, searching, renaming, and deleting files.
 * Includes dynamic polling for background Celery parsing tasks.
 */

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  UploadCloud,
  FileText,
  Trash2,
  Edit2,
  Search,
  Loader2,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  CheckCircle,
  File,
  X,
  RefreshCw,
} from "lucide-react";
import { documentsApi, DocumentResponse } from "@/lib/api";

const PAGE_SIZE = 8;

export default function DocumentsPage() {
  // ── State management ───────────────────────────────────────────────────────
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);

  // Upload States
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);

  // Modals & Feedback
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [editingDoc, setEditingDoc] = useState<DocumentResponse | null>(null);
  const [newName, setNewName] = useState("");
  const [confirmDeleteDoc, setConfirmDeleteDoc] = useState<DocumentResponse | null>(null);

  // ── API Fetch Calls ────────────────────────────────────────────────────────
  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await documentsApi.list({
        limit: PAGE_SIZE,
        offset,
        search: search.trim() || undefined,
      });
      setDocuments(data);
    } catch (err: unknown) {
      console.error(err);
      const errorResponse = err as { error?: { message?: string } } | undefined;
      setErrorMsg(errorResponse?.error?.message || "Failed to load documents.");
    } finally {
      setLoading(false);
    }
  }, [offset, search]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchDocuments();
    }, 0);
    return () => clearTimeout(timer);
  }, [fetchDocuments]);

  // Debounced search trigger reset
  useEffect(() => {
    const timer = setTimeout(() => {
      setOffset(0);
    }, 0);
    return () => clearTimeout(timer);
  }, [search]);

  // ── Transient State Polling Hook ──────────────────────────────────────────
  useEffect(() => {
    // Identify which listed documents are in a transient background processing state
    const transientDocs = documents.filter((doc) =>
      ["UPLOADED", "QUEUED", "PROCESSING"].includes(doc.processing_status.toUpperCase())
    );

    if (transientDocs.length === 0) return;

    // Start polling status every 3 seconds for active tasks
    const interval = setInterval(async () => {
      try {
        let hasChanges = false;
        const updatedDocs = await Promise.all(
          documents.map(async (doc) => {
            if (["UPLOADED", "QUEUED", "PROCESSING"].includes(doc.processing_status.toUpperCase())) {
              const statusResponse = await documentsApi.status(doc.id);
              if (statusResponse.status !== doc.processing_status) {
                hasChanges = true;
                return { ...doc, processing_status: statusResponse.status };
              }
            }
            return doc;
          })
        );

        if (hasChanges) {
          setDocuments(updatedDocs);
        }
      } catch (err) {
        console.error("Error polling document status:", err);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [documents]);

  // ── Ingestion & Upload Actions ─────────────────────────────────────────────
  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];

    // Basic frontend client validations
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    const allowedExtensions = [".pdf", ".docx", ".txt"];
    if (!allowedExtensions.includes(ext)) {
      setErrorMsg(`File extension '${ext}' is not supported. Allowed: PDF, DOCX, TXT.`);
      return;
    }

    const maxLimit = 50 * 1024 * 1024; // 50MB matching backend settings
    if (file.size > maxLimit) {
      setErrorMsg("File size exceeds the maximum limit of 50MB.");
      return;
    }

    setUploading(true);
    setUploadProgress(20);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      const interval = setInterval(() => {
        setUploadProgress((prev) => (prev < 80 ? prev + 15 : prev));
      }, 200);

      await documentsApi.upload(file);
      clearInterval(interval);
      setUploadProgress(100);
      setSuccessMsg(`Document '${file.name}' uploaded and queued for background processing.`);
      fetchDocuments();
    } catch (err: unknown) {
      console.error(err);
      const errorResponse = err as { error?: { message?: string } } | undefined;
      setErrorMsg(errorResponse?.error?.message || "File upload failed.");
    } finally {
      setTimeout(() => {
        setUploading(false);
        setUploadProgress(0);
      }, 500);
    }
  };

  // ── Rename Action ──────────────────────────────────────────────────────────
  const handleRename = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingDoc || !newName.trim()) return;

    try {
      await documentsApi.rename(editingDoc.id, newName.trim());
      setSuccessMsg(`Document renamed to '${newName.trim()}'.`);
      setEditingDoc(null);
      fetchDocuments();
    } catch (err: unknown) {
      console.error(err);
      const errorResponse = err as { error?: { message?: string } } | undefined;
      setErrorMsg(errorResponse?.error?.message || "Failed to rename document.");
    }
  };

  // ── Delete Action ──────────────────────────────────────────────────────────
  const handleDelete = async () => {
    if (!confirmDeleteDoc) return;

    try {
      await documentsApi.delete(confirmDeleteDoc.id);
      setSuccessMsg(`Document '${confirmDeleteDoc.original_filename}' deleted.`);
      setConfirmDeleteDoc(null);
      fetchDocuments();
    } catch (err: unknown) {
      console.error(err);
      const errorResponse = err as { error?: { message?: string } } | undefined;
      setErrorMsg(errorResponse?.error?.message || "Failed to delete document.");
    }
  };

  // Helper to format file sizes
  const formatSize = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  // Render Status Badge
  const renderStatusBadge = (status: string) => {
    switch (status?.toUpperCase()) {
      case "UPLOADED":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
            Uploaded
          </span>
        );
      case "QUEUED":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-purple-950/40 text-purple-300 border border-purple-800/40">
            Queued
          </span>
        );
      case "PROCESSING":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-amber-950/40 text-amber-300 border border-amber-800/40 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping shrink-0" />
            Processing
          </span>
        );
      case "COMPLETED":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-950/40 text-emerald-300 border border-emerald-800/40">
            Completed
          </span>
        );
      case "FAILED":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-red-950/40 text-red-300 border border-red-800/40">
            Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
            {status || "Unknown"}
          </span>
        );
    }
  };

  return (
    <div className="relative min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-indigo-500/30 selection:text-indigo-200">
      {/* Background Gradients */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#0f172a_1px,transparent_1px),linear-gradient(to_bottom,#0f172a_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] opacity-30 pointer-events-none" />
      <div className="absolute top-0 right-1/4 w-[500px] h-[500px] bg-indigo-500/10 blur-[120px] rounded-full pointer-events-none" />
      <div className="absolute top-1/3 left-1/4 w-[600px] h-[600px] bg-blue-500/5 blur-[150px] rounded-full pointer-events-none" />

      {/* Header Panel */}
      <header className="sticky top-0 z-40 w-full border-b border-slate-800 bg-slate-950/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center space-x-2 text-xl font-bold tracking-tight text-white hover:text-indigo-400 transition-colors">
            <span className="bg-gradient-to-r from-indigo-400 via-sky-400 to-emerald-400 bg-clip-text text-transparent">
              Enterprise RAG
            </span>
          </Link>
          <div className="flex items-center space-x-6">
            <Link
              href="/search"
              className="text-sm font-semibold text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1.5"
            >
              🔍 Semantic Search
            </Link>
            <Link href="/" className="text-sm font-medium text-slate-400 hover:text-white transition-colors">
              Back to Home
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 relative z-10">
        {/* Banner Section */}
        <div className="mb-8">
          <h1 className="text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
            Document Center
          </h1>
          <p className="mt-2 text-sm sm:text-base text-slate-400 max-w-3xl">
            Ingest enterprise knowledge bases (PDF, DOCX, TXT) securely. Files are automatically verified, hashed for deduplication, and stored isolated in your workspace.
          </p>
        </div>

        {/* Global Feedback Notifications */}
        {errorMsg && (
          <div className="mb-6 flex items-start space-x-3 rounded-lg border border-red-500/20 bg-red-950/20 p-4 text-red-200">
            <AlertTriangle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
            <div className="flex-1 text-sm font-medium">{errorMsg}</div>
            <button onClick={() => setErrorMsg(null)} className="text-red-400 hover:text-red-200">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {successMsg && (
          <div className="mb-6 flex items-start space-x-3 rounded-lg border border-emerald-500/20 bg-emerald-950/20 p-4 text-emerald-200">
            <CheckCircle className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
            <div className="flex-1 text-sm font-medium">{successMsg}</div>
            <button onClick={() => setSuccessMsg(null)} className="text-emerald-400 hover:text-emerald-200">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Uploader Column */}
          <div className="lg:col-span-1">
            <div
              className={`rounded-2xl border-2 border-dashed p-8 flex flex-col items-center justify-center text-center transition-all duration-300 ${
                dragOver
                  ? "border-indigo-500 bg-indigo-500/10 scale-[1.01]"
                  : "border-slate-800 bg-slate-900/30 hover:border-slate-700"
              }`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                handleUpload(e.dataTransfer.files);
              }}
            >
              <div className="p-4 bg-slate-850 rounded-full text-indigo-400 mb-4 ring-1 ring-slate-850 shadow-inner">
                <UploadCloud className="h-10 w-10 animate-pulse" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-1">Upload Document</h3>
              <p className="text-xs text-slate-400 mb-6 max-w-xs">
                Drag & drop files here or click to browse. Supports PDF, DOCX, and TXT (Max 50MB).
              </p>

              <label className="cursor-pointer">
                <span className="inline-flex items-center px-4 py-2 text-sm font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/20 transition-all duration-200 hover:scale-[1.02]">
                  Select File
                </span>
                <input
                  type="file"
                  className="hidden"
                  accept=".pdf,.docx,.txt"
                  onChange={(e) => handleUpload(e.target.files)}
                />
              </label>

              {uploading && (
                <div className="w-full mt-6">
                  <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                    <span>Uploading...</span>
                    <span>{uploadProgress}%</span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                    <div
                      className="bg-gradient-to-r from-indigo-500 to-sky-400 h-1.5 rounded-full transition-all duration-300"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* List Dashboard Column */}
          <div className="lg:col-span-2 space-y-4">
            {/* Search and Refresh */}
            <div className="flex flex-col sm:flex-row items-center gap-3">
              <div className="relative w-full">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
                <input
                  type="text"
                  placeholder="Search files by name..."
                  className="w-full bg-slate-900/60 border border-slate-800 rounded-lg pl-10 pr-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 transition-all"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <button
                onClick={fetchDocuments}
                className="flex items-center gap-2 px-4 py-2 border border-slate-800 rounded-lg text-sm bg-slate-900/40 hover:bg-slate-800/60 text-slate-300 hover:text-white transition-all shrink-0 w-full sm:w-auto justify-center"
              >
                <RefreshCw className="h-4 w-4" />
                Refresh
              </button>
            </div>

            {/* List panel */}
            <div className="border border-slate-800 bg-slate-900/20 backdrop-blur-md rounded-2xl overflow-hidden">
              {loading ? (
                <div className="p-12 flex flex-col items-center justify-center text-slate-500">
                  <Loader2 className="h-8 w-8 animate-spin text-indigo-400 mb-3" />
                  <p className="text-sm font-medium">Scanning storage workspace...</p>
                </div>
              ) : documents.length === 0 ? (
                <div className="p-16 flex flex-col items-center justify-center text-center">
                  <div className="p-4 bg-slate-900/50 rounded-full text-slate-600 mb-4 ring-1 ring-slate-850">
                    <File className="h-10 w-10" />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-300 mb-1">No documents found</h3>
                  <p className="text-xs text-slate-500 max-w-sm">
                    {search ? "No matching files found for this query." : "Ingest files on the left partition to get started."}
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-slate-850">
                  <div className="grid grid-cols-12 px-6 py-3 text-xs font-semibold uppercase tracking-wider text-slate-400 bg-slate-900/50 items-center">
                    <div className="col-span-5 sm:col-span-6">Filename</div>
                    <div className="col-span-3 sm:col-span-2 text-center">Status</div>
                    <div className="col-span-2 sm:col-span-2 text-right">Size</div>
                    <div className="col-span-2 sm:col-span-2 text-right">Actions</div>
                  </div>

                  {documents.map((doc) => (
                    <div key={doc.id} className="grid grid-cols-12 px-6 py-4 items-center hover:bg-slate-900/20 transition-all duration-150">
                      <div className="col-span-5 sm:col-span-6 flex items-center space-x-3 pr-2 overflow-hidden">
                        <FileText className="h-5 w-5 text-indigo-400 shrink-0" />
                        <div className="overflow-hidden">
                          <Link
                            href={`/documents/${doc.id}`}
                            className="text-sm font-medium text-slate-200 truncate hover:text-indigo-400 transition-colors block"
                            title={doc.original_filename}
                          >
                            {doc.original_filename}
                          </Link>
                          <p className="text-[10px] text-slate-500">
                            Uploaded {new Date(doc.created_at).toLocaleDateString()}
                          </p>
                        </div>
                      </div>

                      <div className="col-span-3 sm:col-span-2 flex justify-center">
                        {renderStatusBadge(doc.processing_status)}
                      </div>

                      <div className="col-span-2 sm:col-span-2 text-right text-xs text-slate-400 font-mono">
                        {formatSize(doc.file_size)}
                      </div>

                      <div className="col-span-2 sm:col-span-2 flex items-center justify-end space-x-2">
                        <button
                          onClick={() => {
                            setEditingDoc(doc);
                            setNewName(doc.original_filename);
                          }}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                          title="Rename file"
                        >
                          <Edit2 className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => setConfirmDeleteDoc(doc)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-950/20 transition-colors"
                          title="Delete file"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Pagination */}
            {!loading && documents.length > 0 && (
              <div className="flex items-center justify-between px-2">
                <span className="text-xs text-slate-500">
                  Showing page {Math.floor(offset / PAGE_SIZE) + 1}
                </span>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setOffset((prev) => Math.max(0, prev - PAGE_SIZE))}
                    disabled={offset === 0}
                    className="p-2 border border-slate-800 rounded-lg bg-slate-900/40 text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-40 disabled:hover:bg-slate-900/40 transition-all cursor-pointer disabled:cursor-not-allowed"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => setOffset((prev) => prev + PAGE_SIZE)}
                    disabled={documents.length < PAGE_SIZE}
                    className="p-2 border border-slate-800 rounded-lg bg-slate-900/40 text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-40 disabled:hover:bg-slate-900/40 transition-all cursor-pointer disabled:cursor-not-allowed"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* ── Rename Dialog Modal ──────────────────────────────────────────────── */}
      {editingDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl relative animate-in fade-in zoom-in duration-200">
            <button onClick={() => setEditingDoc(null)} className="absolute top-4 right-4 text-slate-500 hover:text-white">
              <X className="h-5 w-5" />
            </button>
            <h3 className="text-lg font-bold text-white mb-4">Rename Document</h3>
            <form onSubmit={handleRename} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1 uppercase tracking-wider">
                  Filename
                </label>
                <input
                  type="text"
                  required
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-650 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
              </div>
              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setEditingDoc(null)}
                  className="px-4 py-2 border border-slate-850 rounded-lg text-sm text-slate-400 hover:text-white hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-semibold text-white shadow-md shadow-indigo-600/10"
                >
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Delete Confirmation Dialog Modal ─────────────────────────────────── */}
      {confirmDeleteDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl relative animate-in fade-in zoom-in duration-200">
            <h3 className="text-lg font-bold text-white mb-2">Delete Document</h3>
            <p className="text-sm text-slate-400 mb-6">
              Are you sure you want to permanently delete <strong className="text-slate-200">&apos;{confirmDeleteDoc.original_filename}&apos;</strong>? This action cannot be undone and will delete the physical file.
            </p>
            <div className="flex items-center justify-end space-x-3">
              <button
                type="button"
                onClick={() => setConfirmDeleteDoc(null)}
                className="px-4 py-2 border border-slate-850 rounded-lg text-sm text-slate-400 hover:text-white hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 rounded-lg text-sm font-semibold text-white shadow-md shadow-red-600/10"
              >
                Delete File
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
