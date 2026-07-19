"use client";

import React, { useEffect, useState } from "react";
import { userApi, ragApi, UserResponse, RAGModelItem } from "@/lib/api";
import {
  User as UserIcon,
  Shield,
  Mail,
  Cpu,
  Settings as SettingsIcon,
  Calendar,
  Lock,
  Database,
  Loader2,
  CheckCircle,
  Sliders,
  SlidersHorizontal,
  Save,
  Check
} from "lucide-react";
import Navigation from "@/components/Navigation";

export default function SettingsPage() {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [models, setModels] = useState<RAGModelItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Form states
  const [provider, setProvider] = useState("gemini");
  const [model, setModel] = useState("gemini-3.5-flash");
  const [temperature, setTemperature] = useState(0.2);
  const [topK, setTopK] = useState(5);
  const [topP, setTopP] = useState(0.9);
  const [maxTokens, setMaxTokens] = useState(1024);
  const [systemPrompt, setSystemPrompt] = useState(
    "You are a professional, helpful Enterprise AI Assistant. Base your answers only on the context provided."
  );
  const [embeddingModel, setEmbeddingModel] = useState("text-embedding-004");
  const [reranker, setReranker] = useState("freshness");
  const [chunkSize, setChunkSize] = useState(1000);
  const [chunkOverlap, setChunkOverlap] = useState(200);
  const [streamingToggle, setStreamingToggle] = useState(true);

  const [saving, setSaving] = useState(false);
  const [showSavedToast, setShowSavedToast] = useState(false);

  useEffect(() => {
    const loadSettingsData = async () => {
      try {
        const [profile, modelList] = await Promise.all([
          userApi.me(),
          ragApi.getModels()
        ]);
        setUser(profile);
        setModels(modelList);

        // Load config values from localStorage
        const saved = localStorage.getItem("rag_settings");
        if (saved) {
          const parsed = JSON.parse(saved);
          setProvider(parsed.provider ?? "gemini");
          setModel(parsed.model ?? "gemini-3.5-flash");
          setTemperature(parsed.temperature ?? 0.2);
          setTopK(parsed.topK ?? 5);
          setTopP(parsed.topP ?? 0.9);
          setMaxTokens(parsed.maxTokens ?? 1024);
          setSystemPrompt(
            parsed.systemPrompt ??
              "You are a professional, helpful Enterprise AI Assistant. Base your answers only on the context provided."
          );
          setEmbeddingModel(parsed.embeddingModel ?? "text-embedding-004");
          setReranker(parsed.reranker ?? "freshness");
          setChunkSize(parsed.chunkSize ?? 1000);
          setChunkOverlap(parsed.chunkOverlap ?? 200);
          setStreamingToggle(parsed.streamingToggle ?? true);
        } else if (modelList.length > 0) {
          const geminiModels = modelList.filter((m) => m.provider === "gemini");
          if (geminiModels.length > 0) {
            setProvider("gemini");
            setModel(geminiModels[0].model_name);
          } else {
            setProvider(modelList[0].provider);
            setModel(modelList[0].model_name);
          }
        }
      } catch (err) {
        console.error("Failed to load settings data:", err);
      } finally {
        setLoading(false);
      }
    };
    loadSettingsData();
  }, []);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const config = {
        provider,
        model,
        temperature,
        topK,
        topP,
        maxTokens,
        systemPrompt,
        embeddingModel,
        reranker,
        chunkSize,
        chunkOverlap,
        streamingToggle
      };
      localStorage.setItem("rag_settings", JSON.stringify(config));
      setShowSavedToast(true);
      setTimeout(() => setShowSavedToast(false), 3000);
    } catch (err) {
      console.error("Failed to save settings:", err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100 font-sans pl-0 md:pl-64">
      {/* Sidebar Navigation */}
      <Navigation />

      {/* Main Workspace Console */}
      <main className="flex-1 max-w-5xl mx-auto px-6 py-8 relative z-10 overflow-y-auto">
        <div className="mb-8 flex justify-between items-start">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-2.5">
              <SettingsIcon className="text-indigo-400" size={28} />
              System Configuration
            </h1>
            <p className="mt-2 text-sm text-slate-400">
              Configure system parameter overrides, token boundaries, and review credentials.
            </p>
          </div>
          {showSavedToast && (
            <div className="flex items-center gap-2 bg-emerald-950 border border-emerald-800 text-emerald-400 text-xs font-bold rounded-xl px-4 py-2.5 animate-bounce shadow-lg shadow-emerald-900/10">
              <Check size={14} />
              <span>Pipeline configs saved successfully!</span>
            </div>
          )}
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20 text-slate-500 text-xs gap-2">
            <Loader2 className="animate-spin text-indigo-500" size={24} />
            <span>Loading configurations…</span>
          </div>
        ) : (
          <div className="space-y-8">
            {/* 1. Interactive Configurations Form */}
            <form onSubmit={handleSave} className="space-y-6">
              <div className="grid md:grid-cols-2 gap-6">
                {/* Panel A: GenAI Tuning */}
                <div className="bg-slate-900/40 border border-slate-900 rounded-2xl p-6 space-y-4">
                  <h2 className="text-sm font-bold text-white flex items-center gap-2 border-b border-slate-850 pb-3">
                    <Sliders className="text-indigo-400" size={16} />
                    GenAI Answer Tuning
                  </h2>

                  <div>
                    <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1.5">
                      LLM Provider
                    </label>
                    <select
                      value={provider}
                      onChange={(e) => {
                        const p = e.target.value;
                        setProvider(p);
                        const filtered = models.filter((m) => m.provider === p);
                        if (filtered.length > 0) {
                          setModel(filtered[0].model_name);
                        }
                      }}
                      className="w-full bg-slate-950 border border-slate-850 rounded-lg p-2.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                    >
                      <option value="gemini">Google Gemini</option>
                      <option value="openai">OpenAI GPT</option>
                      <option value="ollama">Ollama (Local)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1.5">
                      Target Model selection
                    </label>
                    <select
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-850 rounded-lg p-2.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                    >
                      {models
                        .filter((m) => m.provider === provider)
                        .map((m) => (
                          <option key={m.model_name} value={m.model_name}>
                            {m.model_name}
                          </option>
                        ))}
                    </select>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">
                        Temperature ({temperature})
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="1.5"
                        step="0.1"
                        value={temperature}
                        onChange={(e) => setTemperature(parseFloat(e.target.value))}
                        className="w-full accent-indigo-500 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">
                        Top-P Nucleus ({topP})
                      </label>
                      <input
                        type="range"
                        min="0.5"
                        max="1"
                        step="0.05"
                        value={topP}
                        onChange={(e) => setTopP(parseFloat(e.target.value))}
                        className="w-full accent-indigo-500 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1.5">
                        Max Output Tokens
                      </label>
                      <input
                        type="number"
                        min="128"
                        max="8192"
                        value={maxTokens}
                        onChange={(e) => setMaxTokens(parseInt(e.target.value))}
                        className="w-full bg-slate-950 border border-slate-850 rounded-lg p-2.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-3">
                        Token streaming
                      </label>
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] text-slate-500">Enable SSE logs</span>
                        <label className="relative inline-flex items-center cursor-pointer select-none">
                          <input
                            type="checkbox"
                            checked={streamingToggle}
                            onChange={(e) => setStreamingToggle(e.target.checked)}
                            className="sr-only peer"
                          />
                          <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-slate-300 after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600 peer-checked:after:bg-white" />
                        </label>
                      </div>
                    </div>
                  </div>

                  <div>
                    <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1.5">
                      System Instruction Prompt
                    </label>
                    <textarea
                      rows={3}
                      value={systemPrompt}
                      onChange={(e) => setSystemPrompt(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-850 rounded-lg p-2.5 text-xs text-white focus:outline-none focus:border-indigo-500 font-mono resize-none leading-relaxed"
                    />
                  </div>
                </div>

                {/* Panel B: Ingestion & Retrieval */}
                <div className="bg-slate-900/40 border border-slate-900 rounded-2xl p-6 space-y-4">
                  <h2 className="text-sm font-bold text-white flex items-center gap-2 border-b border-slate-850 pb-3">
                    <Database className="text-indigo-400" size={16} />
                    Retrieval & Embedding Config
                  </h2>

                  <div>
                    <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1.5">
                      Embedding Vector Model
                    </label>
                    <select
                      value={embeddingModel}
                      onChange={(e) => setEmbeddingModel(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-850 rounded-lg p-2.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                    >
                      <option value="text-embedding-004">Google text-embedding-004</option>
                      <option value="text-embedding-3-small">OpenAI text-embedding-3-small</option>
                      <option value="all-minilm">Ollama all-minilm (Local)</option>
                    </select>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1.5">
                        Chunk Size (chars)
                      </label>
                      <input
                        type="number"
                        min="200"
                        max="5000"
                        value={chunkSize}
                        onChange={(e) => setChunkSize(parseInt(e.target.value))}
                        className="w-full bg-slate-950 border border-slate-850 rounded-lg p-2.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1.5">
                        Chunk Overlap (chars)
                      </label>
                      <input
                        type="number"
                        min="20"
                        max="1000"
                        value={chunkOverlap}
                        onChange={(e) => setChunkOverlap(parseInt(e.target.value))}
                        className="w-full bg-slate-950 border border-slate-850 rounded-lg p-2.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">
                        Retrieval Top-K ({topK})
                      </label>
                      <input
                        type="range"
                        min="1"
                        max="20"
                        step="1"
                        value={topK}
                        onChange={(e) => setTopK(parseInt(e.target.value))}
                        className="w-full accent-indigo-500 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1.5">
                        Reranker Algorithm
                      </label>
                      <select
                        value={reranker}
                        onChange={(e) => setReranker(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-850 rounded-lg p-2.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                      >
                        <option value="freshness">Freshness Decay & Priority</option>
                        <option value="cosine">Pure Cosine Similarity</option>
                        <option value="cohere">Cohere Rerank Model</option>
                      </select>
                    </div>
                  </div>

                  <div className="pt-6">
                    <button
                      type="submit"
                      disabled={saving}
                      className="w-full py-3 bg-gradient-to-br from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 border border-indigo-500/20 text-white rounded-xl shadow-lg hover:scale-102 active:scale-98 transition-all flex items-center justify-center gap-2 cursor-pointer font-bold text-xs uppercase tracking-wider"
                    >
                      {saving ? (
                        <Loader2 className="animate-spin" size={14} />
                      ) : (
                        <Save size={14} />
                      )}
                      <span>Save configurations</span>
                    </button>
                  </div>
                </div>
              </div>
            </form>

            {/* User Profile Info */}
            <section className="bg-slate-900/40 border border-slate-900 rounded-2xl p-6">
              <h2 className="text-sm font-bold text-white flex items-center gap-2 mb-4 border-b border-slate-850 pb-3">
                <UserIcon className="text-indigo-400" size={16} />
                User Profile Information
              </h2>
              {user ? (
                <div className="grid md:grid-cols-2 gap-6">
                  <div className="space-y-4">
                    <div>
                      <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                        Full Name
                      </span>
                      <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
                        <span>{user.full_name}</span>
                      </div>
                    </div>

                    <div>
                      <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                        Email Address
                      </span>
                      <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
                        <Mail size={14} className="text-slate-400" />
                        <span>{user.email}</span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                        System Privileges (RBAC)
                      </span>
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-[10px] font-bold uppercase tracking-wider">
                        <Shield size={12} />
                        <span>{user.role}</span>
                      </div>
                    </div>

                    <div>
                      <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                        Account Verification Status
                      </span>
                      <div className="flex items-center gap-1 text-xs font-semibold text-emerald-400">
                        <CheckCircle size={14} />
                        <span>Verified Account</span>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-xs text-slate-500">Failed to load profile.</div>
              )}
            </section>

            {/* Model configurations info list */}
            <section className="bg-slate-900/40 border border-slate-900 rounded-2xl p-6">
              <h2 className="text-sm font-bold text-white flex items-center gap-2 mb-4 border-b border-slate-850 pb-3">
                <Cpu className="text-indigo-400" size={16} />
                Loaded Large Language Models
              </h2>
              <div className="grid md:grid-cols-2 gap-4">
                {models.length === 0 ? (
                  <div className="col-span-2 text-center text-xs text-slate-500 py-6">
                    No models registered in backend database.
                  </div>
                ) : (
                  models.map((m) => (
                    <div
                      key={m.model_name}
                      className="p-4 rounded-xl border border-slate-900 bg-slate-950/20 hover:border-slate-800 transition-colors"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="font-bold text-xs text-slate-200">{m.model_name}</h3>
                        <span className="px-2 py-0.5 rounded bg-slate-950 border border-slate-900 text-[8px] font-bold uppercase text-indigo-400">
                          {m.provider}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500 leading-relaxed mb-3">
                        Grounded, tool-augmented answer compilation matching target context files.
                      </p>
                      <div className="flex items-center gap-3 text-[9px] text-slate-400 font-mono">
                        <div>Context: 128k</div>
                        <div>Output: 8k</div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>

            {/* Security Config Policies */}
            <section className="bg-slate-900/40 border border-slate-900 rounded-2xl p-6">
              <h2 className="text-sm font-bold text-white flex items-center gap-2 mb-4 border-b border-slate-850 pb-3">
                <Lock className="text-indigo-400" size={16} />
                Secret Key & Session Policies
              </h2>
              <div className="space-y-4 text-xs text-slate-400">
                <div className="flex justify-between items-center text-xs border-b border-slate-900 pb-2">
                  <span>JWT Token Life Span</span>
                  <span className="font-mono text-slate-300">30 minutes</span>
                </div>
                <div className="flex justify-between items-center text-xs border-b border-slate-900 pb-2">
                  <span>JWT Refresh Life Span</span>
                  <span className="font-mono text-slate-300">7 days</span>
                </div>
                <div className="flex justify-between items-center text-xs pb-1">
                  <span>Vector Indexing Dialect</span>
                  <span className="font-mono text-slate-300">pgvector HNSW cosine</span>
                </div>
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
