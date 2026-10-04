"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  UploadCloud,
  FileText,
  Trash2,
  Search,
  Loader2,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  CheckCircle,
  X,
  RefreshCw,
  FolderOpen
} from "lucide-react";
import { documentsApi, DocumentResponse } from "@/lib/api";
import AppSidebar from "@/components/layout/AppSidebar";
import AppTopbar from "@/components/layout/AppTopbar";

const PAGE_SIZE = 8;

export default function DocumentsPage() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
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
  const [confirmDeleteDoc, setConfirmDeleteDoc] = useState<DocumentResponse | null>(null);

  // API Fetch
  const fetchDocuments = useCallback(async () => {
    try {
      const data = await documentsApi.list({
        limit: PAGE_SIZE,
        offset,
        search: search.trim() || undefined,
      });
      setDocuments(data);
    } catch (err: unknown) {
      console.error("Failed to load documents:", err);
      const errorResponse = err as { error?: { message?: string } } | undefined;
      setErrorMsg(errorResponse?.error?.message || "Failed to load documents.");
    } finally {
      setLoading(false);
    }
  }, [offset, search]);

  useEffect(() => {
    void fetchDocuments();
  }, [fetchDocuments]);

  const handleRefresh = () => {
    setLoading(true);
    setErrorMsg(null);
    void fetchDocuments();
  };

  // Transient State Polling Hook for Ingestion
  useEffect(() => {
    const transientDocs = documents.filter((doc) =>
      ["UPLOADED", "QUEUED", "PROCESSING"].includes(doc.processing_status.toUpperCase())
    );

    if (transientDocs.length === 0) return;

    const interval = setInterval(async () => {
      try {
        let hasChanges = false;
        const updatedDocs = await Promise.all(
          documents.map(async (doc) => {
            if (["UPLOADED", "QUEUED", "PROCESSING"].includes(doc.processing_status.toUpperCase())) {
              try {
                const refreshed = await documentsApi.get(doc.id);
                if (refreshed.processing_status !== doc.processing_status) {
                  hasChanges = true;
                  return refreshed;
                }
              } catch (e) {
                console.error("Error polling document:", e instanceof Error ? e.message : e);
              }
            }
            return doc;
          })
        );

        if (hasChanges) {
          setDocuments(updatedDocs);
        }
      } catch (e) {
        console.error("Background document status poll failed:", e);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [documents]);

  // Handle Upload
  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];

    const allowedExtensions = [".pdf", ".docx", ".txt"];
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    if (!allowedExtensions.includes(ext)) {
      setErrorMsg(`Unsupported file type: ${ext}. Please upload PDF, DOCX, or TXT.`);
      return;
    }

    if (file.size > 50 * 1024 * 1024) {
      setErrorMsg("File size exceeds 50MB maximum limit.");
      return;
    }

    setUploading(true);
    setUploadProgress(15);
    setErrorMsg(null);
    setSuccessMsg(null);

    const progressTimer = setInterval(() => {
      setUploadProgress((prev) => (prev < 85 ? prev + 15 : prev));
    }, 250);

    try {
      const newDoc = await documentsApi.upload(file);
      clearInterval(progressTimer);
      setUploadProgress(100);
      setSuccessMsg(`"${file.name}" uploaded successfully. Ingestion pipeline scheduled.`);
      setDocuments((prev) => [newDoc, ...prev]);
    } catch (err: unknown) {
      clearInterval(progressTimer);
      console.error(err);
      const errorResponse = err as { error?: { message?: string } } | undefined;
      setErrorMsg(errorResponse?.error?.message || "File upload failed. Please try again.");
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  };

  // Delete Action
  const handleDelete = async (id: string) => {
    try {
      await documentsApi.delete(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
      setSuccessMsg("Document deleted successfully.");
      setConfirmDeleteDoc(null);
    } catch (err: unknown) {
      const errorResponse = err as { error?: { message?: string } } | undefined;
      setErrorMsg(errorResponse?.error?.message || "Failed to delete document.");
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const renderStatusBadge = (status: string) => {
    switch (status?.toUpperCase()) {
      case "UPLOADED":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-700 border border-slate-200">
            Uploaded
          </span>
        );
      case "QUEUED":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-purple-50 text-purple-700 border border-purple-200">
            Queued
          </span>
        );
      case "PROCESSING":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-ping shrink-0" />
            Processing
          </span>
        );
      case "COMPLETED":
      case "PROCESSED":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            Indexed
          </span>
        );
      case "FAILED":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-red-50 text-red-700 border border-red-200">
            Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-700 border border-slate-200">
            {status || "Unknown"}
          </span>
        );
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
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
                <FileText className="text-blue-600" size={24} />
                Documents & Knowledge Base
              </h1>
              <p className="text-xs md:text-sm text-slate-500 mt-1">
                Upload and manage files. Uploaded documents are chunked and embedded using BAAI/bge-base-en-v1.5.
              </p>
            </div>

            {/* Error / Success Notifications */}
            {errorMsg && (
              <div className="flex items-start justify-between rounded-xl border border-red-200 bg-red-50 p-4 text-red-800 text-xs shadow-2xs">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-red-600 shrink-0" />
                  <span>{errorMsg}</span>
                </div>
                <button onClick={() => setErrorMsg(null)} className="text-red-500 hover:text-red-800">
                  <X size={14} />
                </button>
              </div>
            )}

            {successMsg && (
              <div className="flex items-start justify-between rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-800 text-xs shadow-2xs">
                <div className="flex items-center gap-2">
                  <CheckCircle className="h-4 w-4 text-emerald-600 shrink-0" />
                  <span>{successMsg}</span>
                </div>
                <button onClick={() => setSuccessMsg(null)} className="text-emerald-500 hover:text-emerald-800">
                  <X size={14} />
                </button>
              </div>
            )}

            {/* Main 2-column Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Uploader Column */}
              <div className="lg:col-span-1">
                <div
                  className={`bg-white rounded-2xl border-2 border-dashed p-6 flex flex-col items-center justify-center text-center transition-all duration-200 shadow-2xs ${
                    dragOver
                      ? "border-blue-500 bg-blue-50/50 scale-[1.01]"
                      : "border-slate-300 hover:border-blue-400"
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
                  <div className="p-3.5 bg-blue-50 text-blue-600 rounded-full mb-3 shadow-2xs">
                    <UploadCloud className="h-8 w-8" />
                  </div>
                  <h3 className="text-sm font-bold text-slate-900 mb-1">
                    Upload Documents
                  </h3>
                  <p className="text-[11px] text-slate-500 mb-5 max-w-xs">
                    Drag and drop files here, or browse from your device. Supports PDF, DOCX, and TXT (Max 50MB).
                  </p>

                  <label className="cursor-pointer">
                    <span className="inline-flex items-center px-4 py-2 text-xs font-semibold rounded-xl bg-blue-600 hover:bg-blue-500 text-white shadow-xs transition-colors">
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
                    <div className="w-full mt-4">
                      <div className="flex items-center justify-between text-[11px] text-slate-500 mb-1 font-medium">
                        <span>Uploading...</span>
                        <span>{uploadProgress}%</span>
                      </div>
                      <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-blue-600 h-1.5 rounded-full transition-all duration-300"
                          style={{ width: `${uploadProgress}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Documents List Column */}
              <div className="lg:col-span-2 space-y-4">
                
                {/* Search & Refresh Toolbar */}
                <div className="flex flex-col sm:flex-row items-center gap-3">
                  <div className="relative w-full">
                    <Search className="absolute left-3.5 top-2.5 h-4 w-4 text-slate-400" />
                    <input
                      type="text"
                      placeholder="Search files by name..."
                      className="w-full bg-white border border-slate-200 rounded-xl pl-10 pr-4 py-2 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-200 shadow-2xs"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>
                  <button
                    onClick={handleRefresh}
                    className="flex items-center gap-1.5 px-3.5 py-2 border border-slate-200 rounded-xl text-xs font-semibold bg-white hover:bg-slate-50 text-slate-700 shadow-2xs transition-colors shrink-0 cursor-pointer"
                  >
                    <RefreshCw className="h-3.5 w-3.5 text-blue-600" />
                    <span>Refresh</span>
                  </button>
                </div>

                {/* Table Container */}
                <div className="bg-white border border-slate-200/90 rounded-2xl shadow-2xs overflow-hidden">
                  {loading ? (
                    <div className="p-12 flex flex-col items-center justify-center text-slate-400 text-xs gap-2">
                      <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
                      <span>Loading documents…</span>
                    </div>
                  ) : documents.length === 0 ? (
                    <div className="p-12 text-center text-slate-400 space-y-2">
                      <FolderOpen className="h-10 w-10 mx-auto text-slate-300" />
                      <h4 className="text-xs font-bold text-slate-700">No documents found</h4>
                      <p className="text-[11px] text-slate-400 max-w-sm mx-auto">
                        {search ? "No files matching your search term." : "Upload documents using the left panel to populate your RAG knowledge base."}
                      </p>
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-100">
                      {/* Table Header */}
                      <div className="grid grid-cols-12 px-5 py-2.5 text-[10px] font-bold uppercase tracking-wider text-slate-500 bg-slate-50/70 items-center">
                        <div className="col-span-6 sm:col-span-6">Filename</div>
                        <div className="col-span-3 sm:col-span-2 text-center">Status</div>
                        <div className="col-span-3 sm:col-span-2 text-right">Size</div>
                        <div className="col-span-12 sm:col-span-2 text-right mt-1 sm:mt-0">Actions</div>
                      </div>

                      {/* Rows */}
                      {documents.map((doc) => {
                        const isPdf = doc.original_filename.toLowerCase().endsWith(".pdf");
                        return (
                          <div
                            key={doc.id}
                            className="grid grid-cols-12 px-5 py-3.5 items-center hover:bg-slate-50/60 transition-colors text-xs"
                          >
                            <div className="col-span-6 sm:col-span-6 flex items-center gap-2.5 pr-2 overflow-hidden">
                              <div
                                className={`w-6 h-6 rounded flex items-center justify-center text-[8px] font-bold uppercase shrink-0 ${
                                  isPdf ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-600"
                                }`}
                              >
                                {isPdf ? "PDF" : "DOC"}
                              </div>
                              <div className="overflow-hidden min-w-0">
                                <Link
                                  href={`/documents/${doc.id}`}
                                  className="font-semibold text-slate-800 truncate hover:text-blue-600 transition-colors block"
                                  title={doc.original_filename}
                                >
                                  {doc.original_filename}
                                </Link>
                                <span className="text-[10px] text-slate-400 block mt-0.5">
                                  Uploaded {new Date(doc.created_at).toLocaleDateString()}
                                </span>
                              </div>
                            </div>

                            <div className="col-span-3 sm:col-span-2 flex justify-center">
                              {renderStatusBadge(doc.processing_status)}
                            </div>

                            <div className="col-span-3 sm:col-span-2 text-right font-mono text-[11px] text-slate-500">
                              {formatSize(doc.file_size)}
                            </div>

                            <div className="col-span-12 sm:col-span-2 flex items-center justify-end gap-1 mt-2 sm:mt-0">
                              <Link
                                href={`/documents/${doc.id}`}
                                className="p-1 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"
                                title="View document chunks"
                              >
                                <FileText size={13} />
                              </Link>
                              <button
                                onClick={() => setConfirmDeleteDoc(doc)}
                                className="p-1 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors cursor-pointer"
                                title="Delete"
                              >
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Pagination Controls */}
                <div className="flex items-center justify-between text-xs text-slate-500 pt-1">
                  <span>
                    Showing {documents.length > 0 ? offset + 1 : 0} to {offset + documents.length}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                      disabled={offset === 0}
                      className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 transition-colors cursor-pointer"
                    >
                      <ChevronLeft size={14} />
                    </button>
                    <button
                      onClick={() => setOffset(offset + PAGE_SIZE)}
                      disabled={documents.length < PAGE_SIZE}
                      className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 transition-colors cursor-pointer"
                    >
                      <ChevronRight size={14} />
                    </button>
                  </div>
                </div>

              </div>

            </div>

          </div>
        </main>
      </div>



      {/* Delete Confirmation Modal */}
      {confirmDeleteDoc && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl p-5 max-w-sm w-full shadow-lg space-y-3 animate-fade-in">
            <h3 className="text-sm font-bold text-slate-900">Confirm Deletion</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Are you sure you want to permanently delete{" "}
              <strong className="text-slate-900 font-semibold">{confirmDeleteDoc.original_filename}</strong>? All associated 768-dim embeddings will be removed from pgvector.
            </p>
            <div className="flex justify-end gap-2 text-xs pt-1">
              <button
                onClick={() => setConfirmDeleteDoc(null)}
                className="px-3 py-2 rounded-xl text-slate-600 hover:bg-slate-100 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(confirmDeleteDoc.id)}
                className="px-4 py-2 rounded-xl bg-red-600 text-white font-semibold hover:bg-red-500 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
