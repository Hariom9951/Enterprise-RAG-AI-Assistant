"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { UploadCloud, CheckCircle, AlertTriangle, ArrowLeft, FileText, Loader2 } from "lucide-react";
import { documentsApi } from "@/lib/api";
import Navigation from "@/components/Navigation";

export default function UploadPage() {
  const router = useRouter();
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const validateFile = (file: File): boolean => {
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    const allowedExtensions = [".pdf", ".docx", ".txt"];
    if (!allowedExtensions.includes(ext)) {
      setErrorMsg(`File extension '${ext}' is not supported. Allowed: PDF, DOCX, TXT.`);
      return false;
    }

    const maxLimit = 50 * 1024 * 1024; // 50MB
    if (file.size > maxLimit) {
      setErrorMsg("File size exceeds the maximum limit of 50MB.");
      return false;
    }

    return true;
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    setErrorMsg(null);
    setSuccessMsg(null);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (validateFile(file)) {
        setSelectedFile(file);
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setErrorMsg(null);
    setSuccessMsg(null);

    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      if (validateFile(file)) {
        setSelectedFile(file);
      }
    }
  };

  const handleUploadSubmit = async () => {
    if (!selectedFile) return;

    setUploading(true);
    setUploadProgress(20);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      const interval = setInterval(() => {
        setUploadProgress((prev) => (prev < 80 ? prev + 15 : prev));
      }, 150);

      await documentsApi.upload(selectedFile);
      
      clearInterval(interval);
      setUploadProgress(100);
      setSuccessMsg(`File '${selectedFile.name}' uploaded successfully. Background Celery parsing has started!`);
      setSelectedFile(null);
    } catch (err: unknown) {
      console.error(err);
      const errorResponse = err as { error?: { message?: string } } | undefined;
      setErrorMsg(errorResponse?.error?.message || "File upload failed. Ensure API keys / backend are online.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100 font-sans pl-0 md:pl-64">
      {/* Sidebar Navigation */}
      <Navigation />

      {/* Main Workspace */}
      <main className="flex-1 max-w-4xl mx-auto px-6 py-8 relative z-10 overflow-y-auto">
        
        {/* Banner Section */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-2">
              <UploadCloud className="text-indigo-400" size={28} />
              Ingest Documents
            </h1>
            <p className="mt-2 text-sm text-slate-400">
              Upload PDF, DOCX, and TXT files. They will be automatically split, chunked, and embedded into pgvector.
            </p>
          </div>
          <Link
            href="/documents"
            className="flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 font-semibold"
          >
            <ArrowLeft size={14} />
            <span>Document Center</span>
          </Link>
        </div>

        <div className="space-y-6">
          {/* Feedback alerts */}
          {errorMsg && (
            <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 flex items-start gap-2.5">
              <AlertTriangle className="text-red-400 mt-0.5 shrink-0" size={16} />
              <div>
                <h4 className="text-sm font-semibold text-red-400">Upload Failure</h4>
                <p className="text-xs text-red-400/80 mt-1">{errorMsg}</p>
              </div>
            </div>
          )}

          {successMsg && (
            <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-start gap-2.5">
              <CheckCircle className="text-emerald-400 mt-0.5 shrink-0" size={16} />
              <div>
                <h4 className="text-sm font-semibold text-emerald-400">Upload Completed</h4>
                <p className="text-xs text-emerald-400/80 mt-1">{successMsg}</p>
                <div className="mt-3">
                  <Link
                    href="/documents"
                    className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 font-semibold"
                  >
                    <span>View parsed status in center &rarr;</span>
                  </Link>
                </div>
              </div>
            </div>
          )}

          {/* Drag & Drop Card */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-3xl p-12 text-center transition-all ${
              dragOver
                ? "border-indigo-500 bg-indigo-500/5"
                : "border-slate-800 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-900/60"
            }`}
          >
            <input
              type="file"
              id="upload-file-input"
              className="hidden"
              accept=".pdf,.docx,.txt"
              onChange={handleFileSelect}
            />
            
            <div className="flex flex-col items-center">
              <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-400 mb-4">
                <UploadCloud size={32} />
              </div>
              
              <h3 className="text-md font-bold text-white mb-2">
                Drag and drop your file here
              </h3>
              <p className="text-xs text-slate-500 max-w-sm mb-6 leading-relaxed">
                Accepts PDF, Word (DOCX), or plain text (TXT) up to 50MB. Double-check layout integrity before submission.
              </p>

              <label
                htmlFor="upload-file-input"
                className="px-4 py-2 bg-slate-800 hover:bg-slate-750 text-white rounded-xl text-xs font-semibold cursor-pointer border border-slate-700 transition-all"
              >
                Choose Local File
              </label>
            </div>
          </div>

          {/* Selected File Card */}
          {selectedFile && (
            <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-10 h-10 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-center text-slate-400 shrink-0">
                  <FileText size={18} />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-white truncate max-w-md">
                    {selectedFile.name}
                  </div>
                  <div className="text-xs text-slate-500">
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSelectedFile(null)}
                  className="px-3 py-1.5 rounded-lg border border-slate-800 text-slate-400 hover:text-white text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  onClick={handleUploadSubmit}
                  disabled={uploading}
                  className="px-4 py-1.5 bg-gradient-to-br from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white rounded-lg text-xs font-semibold border border-indigo-500/20 shadow-md flex items-center gap-1.5"
                >
                  {uploading && <Loader2 className="animate-spin" size={12} />}
                  <span>Upload & Ingest</span>
                </button>
              </div>
            </div>
          )}

          {/* Progress bar */}
          {uploading && (
            <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800">
              <div className="flex justify-between items-center text-xs mb-2">
                <span className="text-slate-400">Uploading and hashing…</span>
                <span className="font-semibold text-indigo-400">{uploadProgress}%</span>
              </div>
              <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-350"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}

        </div>
      </main>
    </div>
  );
}
