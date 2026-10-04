"use client";

import React, { useEffect, useState } from "react";
import { userApi, ragApi, UserResponse, RAGModelItem } from "@/lib/api";
import {
  User as UserIcon,
  Settings as SettingsIcon,
  Database,
  Loader2,
  CheckCircle,
  Sliders,
  Save,
  Sparkles
} from "lucide-react";
import AppSidebar from "@/components/layout/AppSidebar";
import AppTopbar from "@/components/layout/AppTopbar";

export default function SettingsPage() {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [models, setModels] = useState<RAGModelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // Form states
  const [model, setModel] = useState("gemini-3.5-flash");
  const [temperature, setTemperature] = useState(0.2);
  const [topK, setTopK] = useState(5);
  const [threshold, setThreshold] = useState(0.0);
  const [maxTokens, setMaxTokens] = useState(1024);
  const [systemPrompt, setSystemPrompt] = useState(
    "You are a professional, helpful Enterprise AI Assistant. Base your answers only on the context provided."
  );
  // Real backend embedding architecture
  const [embeddingModel] = useState("BAAI/bge-base-en-v1.5");
  const [vectorDimension] = useState(768);
  const [vectorStore] = useState("PostgreSQL + pgvector (HNSW Cosine)");
  const [useReranker, setUseReranker] = useState(true);

  const [saving, setSaving] = useState(false);
  const [showSavedToast, setShowSavedToast] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const loadSettingsData = async () => {
      try {
        const [profile, modelList] = await Promise.all([
          userApi.me().catch(() => null),
          ragApi.getModels().catch(() => [])
        ]);

        if (!isMounted) return;
        if (profile) setUser(profile);
        setModels(modelList);

        // Load config values from localStorage
        const saved = localStorage.getItem("rag_settings");
        if (saved) {
          const parsed = JSON.parse(saved);
          setModel(parsed.model ?? (modelList[0]?.model_name || "gemini-2.5-flash"));
          setTemperature(parsed.temperature ?? 0.2);
          setTopK(parsed.topK ?? 5);
          setThreshold(parsed.threshold ?? 0.0);
          setMaxTokens(parsed.maxTokens ?? 1024);
          setSystemPrompt(
            parsed.systemPrompt ??
              "You are a professional, helpful Enterprise AI Assistant. Base your answers only on the context provided."
          );
          setUseReranker(parsed.useReranker ?? true);
        } else if (modelList.length > 0) {
          setModel(modelList[0].model_name);
        }
      } catch (err) {
        console.error("Failed to load settings data:", err);
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    loadSettingsData();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const config = {
        provider: "gemini",
        model,
        temperature,
        topK,
        threshold,
        maxTokens,
        systemPrompt,
        embeddingModel,
        useReranker
      };
      localStorage.setItem("rag_settings", JSON.stringify(config));
      setShowSavedToast(true);
      setTimeout(() => setShowSavedToast(false), 3000);
    } catch (err) {
      console.error("Failed to save settings to localStorage:", err);
    } finally {
      setSaving(false);
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
          <div className="max-w-4xl mx-auto space-y-6">
            
            {/* Page Header */}
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
                <SettingsIcon className="text-blue-600" size={24} />
                System Settings
              </h1>
              <p className="text-xs md:text-sm text-slate-500 mt-1">
                Configure your Enterprise RAG parameters, LLM model selection, and view active infrastructure.
              </p>
            </div>

            {/* Saved Toast Alert */}
            {showSavedToast && (
              <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 px-4 py-3 rounded-xl flex items-center gap-2 text-xs font-semibold shadow-xs animate-fade-in">
                <CheckCircle size={16} className="text-emerald-600" />
                <span>Configuration preferences saved successfully.</span>
              </div>
            )}

            {loading ? (
              <div className="py-24 flex flex-col items-center justify-center text-slate-400 gap-2">
                <Loader2 className="animate-spin text-blue-600" size={24} />
                <span className="text-xs">Loading system configuration…</span>
              </div>
            ) : (
              <form onSubmit={handleSave} className="space-y-6">
                
                {/* 1. Infrastructure Architecture Card (Accurate Reality) */}
                <div className="bg-white border border-slate-200/90 rounded-2xl p-5 md:p-6 shadow-2xs space-y-4">
                  <div className="border-b border-slate-100 pb-3 flex items-center justify-between">
                    <div>
                      <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                        <Database size={16} className="text-blue-600" />
                        Active AI & Embedding Architecture
                      </h2>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Current verified backend retrieval and vector search configuration.
                      </p>
                    </div>
                    <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full text-[10px] font-bold uppercase tracking-wider">
                      Verified
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    {/* Embedding Model */}
                    <div className="p-3.5 bg-slate-50 border border-slate-200/80 rounded-xl space-y-1">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                        Embedding Model (Dense)
                      </span>
                      <p className="font-semibold text-slate-900 font-mono text-xs">
                        {embeddingModel}
                      </p>
                      <p className="text-[11px] text-slate-500">
                        {vectorDimension}-dimensional dense vectors via local sentence-transformers.
                      </p>
                    </div>

                    {/* Vector Database */}
                    <div className="p-3.5 bg-slate-50 border border-slate-200/80 rounded-xl space-y-1">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                        Vector Store & Index
                      </span>
                      <p className="font-semibold text-slate-900 font-mono text-xs">
                        {vectorStore}
                      </p>
                      <p className="text-[11px] text-slate-500">
                        High-performance HNSW index on PostgreSQL Neon cloud instance.
                      </p>
                    </div>

                    {/* LLM Provider */}
                    <div className="p-3.5 bg-slate-50 border border-slate-200/80 rounded-xl space-y-1">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                        Primary LLM Provider
                      </span>
                      <p className="font-semibold text-slate-900 font-mono text-xs flex items-center gap-1.5">
                        <Sparkles size={13} className="text-blue-600" />
                        Google Gemini API
                      </p>
                      <p className="text-[11px] text-slate-500">
                        Sole LLM provider for grounded answers and tool reasoning.
                      </p>
                    </div>

                    {/* Retrieval Pipeline */}
                    <div className="p-3.5 bg-slate-50 border border-slate-200/80 rounded-xl space-y-1">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                        Retrieval Strategy
                      </span>
                      <p className="font-semibold text-slate-900 font-mono text-xs">
                        Hybrid Search (Dense + Lexical BM25)
                      </p>
                      <p className="text-[11px] text-slate-500">
                        Reciprocal rank fusion + contextual cross-encoder reranking.
                      </p>
                    </div>
                  </div>
                </div>

                {/* 2. Generation & Inference Parameters */}
                <div className="bg-white border border-slate-200/90 rounded-2xl p-5 md:p-6 shadow-2xs space-y-4">
                  <div className="border-b border-slate-100 pb-3">
                    <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                      <Sliders size={16} className="text-blue-600" />
                      Inference & Generation Controls
                    </h2>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Tune temperature, context chunking, and output length.
                    </p>
                  </div>

                  <div className="space-y-4 text-xs">
                    {/* Gemini Model Selector */}
                    <div>
                      <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                        Active Gemini Model
                      </label>
                      <select
                        value={model}
                        onChange={(e) => setModel(e.target.value)}
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 text-xs text-slate-800 font-medium focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-200"
                      >
                        {models.length > 0 ? (
                          models.map((m) => (
                            <option key={m.model_name} value={m.model_name}>
                              {m.model_name} ({m.provider})
                            </option>
                          ))
                        ) : (
                          <option value="gemini-3.5-flash">gemini-3.5-flash</option>
                        )}
                      </select>
                    </div>

                    {/* Sliders Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                      {/* Temperature */}
                      <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl space-y-2">
                        <div className="flex justify-between items-center">
                          <label className="font-semibold text-slate-800">
                            Temperature ({temperature})
                          </label>
                          <span className="text-[10px] text-slate-400">0.0 - 1.0</span>
                        </div>
                        <input
                          type="range"
                          min="0"
                          max="1"
                          step="0.05"
                          value={temperature}
                          onChange={(e) => setTemperature(parseFloat(e.target.value))}
                          className="w-full accent-blue-600 cursor-pointer"
                        />
                        <p className="text-[10px] text-slate-500">
                          Low values give deterministic, grounded responses with minimal hallucination.
                        </p>
                      </div>

                      {/* Top Chunks */}
                      <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl space-y-2">
                        <div className="flex justify-between items-center">
                          <label className="font-semibold text-slate-800">
                            Top Chunks / Top-K ({topK})
                          </label>
                          <span className="text-[10px] text-slate-400">1 - 15</span>
                        </div>
                        <input
                          type="range"
                          min="1"
                          max="15"
                          step="1"
                          value={topK}
                          onChange={(e) => setTopK(parseInt(e.target.value))}
                          className="w-full accent-blue-600 cursor-pointer"
                        />
                        <p className="text-[10px] text-slate-500">
                          Number of document context passages injected into the prompt.
                        </p>
                      </div>

                      {/* Similarity Cutoff */}
                      <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl space-y-2">
                        <div className="flex justify-between items-center">
                          <label className="font-semibold text-slate-800">
                            Similarity Cutoff ({threshold})
                          </label>
                          <span className="text-[10px] text-slate-400">0.0 - 0.8</span>
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
                        <p className="text-[10px] text-slate-500">
                          Filters out chunks with cosine similarity score below this threshold.
                        </p>
                      </div>

                      {/* Max Tokens */}
                      <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl space-y-2">
                        <div className="flex justify-between items-center">
                          <label className="font-semibold text-slate-800">
                            Max Response Tokens ({maxTokens})
                          </label>
                          <span className="text-[10px] text-slate-400">256 - 4096</span>
                        </div>
                        <input
                          type="range"
                          min="256"
                          max="4096"
                          step="128"
                          value={maxTokens}
                          onChange={(e) => setMaxTokens(parseInt(e.target.value))}
                          className="w-full accent-blue-600 cursor-pointer"
                        />
                        <p className="text-[10px] text-slate-500">
                          Maximum token length allowed for Gemini assistant answers.
                        </p>
                      </div>
                    </div>

                    {/* Reranker Toggle */}
                    <div className="p-3.5 bg-slate-50 border border-slate-200/80 rounded-xl flex items-center justify-between">
                      <div>
                        <span className="font-semibold text-slate-800 block">
                          Cross-Encoder Contextual Reranking
                        </span>
                        <span className="text-[11px] text-slate-500 block">
                          Applies high-precision secondary neural reranking over retrieved passages.
                        </span>
                      </div>
                      <input
                        type="checkbox"
                        checked={useReranker}
                        onChange={(e) => setUseReranker(e.target.checked)}
                        className="w-4 h-4 rounded text-blue-600 accent-blue-600 cursor-pointer"
                      />
                    </div>

                    {/* System Prompt */}
                    <div className="pt-2">
                      <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                        Base System Instruction Prompt
                      </label>
                      <textarea
                        rows={3}
                        value={systemPrompt}
                        onChange={(e) => setSystemPrompt(e.target.value)}
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs text-slate-800 leading-relaxed font-sans focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-200"
                      />
                    </div>
                  </div>
                </div>

                {/* 3. Account Profile Card */}
                {user && (
                  <div className="bg-white border border-slate-200/90 rounded-2xl p-5 md:p-6 shadow-2xs space-y-4">
                    <div className="border-b border-slate-100 pb-3">
                      <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                        <UserIcon size={16} className="text-blue-600" />
                        Account & Credentials
                      </h2>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Authenticated session information for this workspace.
                      </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                      <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                          User Name
                        </span>
                        <span className="font-semibold text-slate-900 mt-0.5 block truncate">
                          {user.full_name}
                        </span>
                      </div>

                      <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                          Email Address
                        </span>
                        <span className="font-semibold text-slate-900 mt-0.5 block truncate">
                          {user.email}
                        </span>
                      </div>

                      <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                          Role & Privileges
                        </span>
                        <span className="font-bold text-blue-600 uppercase font-mono mt-0.5 block">
                          {user.role}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Action Buttons */}
                <div className="flex justify-end gap-3 pt-2">
                  <button
                    type="submit"
                    disabled={saving}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
                  >
                    {saving ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Save size={14} />
                    )}
                    <span>Save Preferences</span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
