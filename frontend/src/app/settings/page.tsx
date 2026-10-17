"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import {
  userApi,
  ragApi,
  oauthApi,
  UserResponse,
  RAGModelItem,
  OAuthConnectionMetadata,
  getApiErrorMessage,
} from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import {
  User as UserIcon,
  Settings as SettingsIcon,
  Database,
  Loader2,
  CheckCircle,
  AlertCircle,
  Sliders,
  Save,
  Sparkles,
  Brain,
  Link2,
  Unlink,
  ExternalLink,
  ShieldCheck,
  X,
  RefreshCw,
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

  // OAuth Connected Apps state
  const [connections, setConnections] = useState<OAuthConnectionMetadata[]>([]);
  const [connectionsLoading, setConnectionsLoading] = useState(false);
  const [connectingApp, setConnectingApp] = useState(false);
  const [disconnectingProvider, setDisconnectingProvider] = useState<string | null>(null);
  const [oauthToast, setOauthToast] = useState<{
    type: "success" | "error" | "info";
    message: string;
  } | null>(null);

  const callbackHandledRef = useRef(false);

  const loadConnections = useCallback(async () => {
    try {
      setConnectionsLoading(true);
      const res = await oauthApi.listConnections().catch(() => ({ connections: [], total: 0 }));
      setConnections(res.connections || []);
    } catch (err) {
      console.error("Failed to load connected apps:", err);
    } finally {
      setConnectionsLoading(false);
    }
  }, []);

  // Main settings load
  useEffect(() => {
    let isMounted = true;
    const loadSettingsData = async () => {
      try {
        const [profile, modelList] = await Promise.all([
          userApi.me().catch(() => null),
          ragApi.getModels().catch(() => []),
          loadConnections(),
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
  }, [loadConnections]);

  // OAuth Callback Handoff Handler with Immediate URL Scrubbing
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (callbackHandledRef.current) return;

    const params = new URLSearchParams(window.location.search);
    const action = params.get("action");
    const provider = params.get("provider");
    const code = params.get("code");
    const state = params.get("state");
    const error = params.get("error");
    const errorDescription = params.get("error_description");

    const hasCallbackParams =
      action === "link" || Boolean(error) || (Boolean(code) && Boolean(state));

    if (!hasCallbackParams) return;

    // Prevent React StrictMode duplicate execution
    callbackHandledRef.current = true;

    // IMMEDIATE URL CLEANUP: Scrub credentials from browser address bar & history
    try {
      const cleanUrl = window.location.pathname;
      window.history.replaceState({}, document.title, cleanUrl);
    } catch {
      // Non-standard history fallback
    }

    // 1. Provider-reported error (e.g. user consent denial)
    if (error) {
      const desc = errorDescription || error;
      setOauthToast({
        type: "error",
        message: `OAuth authorization cancelled or denied: ${desc}`,
      });
      return;
    }

    // 2. Validate action and provider
    if (action !== "link" || provider !== "github" || !code || !state) {
      setOauthToast({
        type: "error",
        message: "Invalid or incomplete OAuth callback parameters received.",
      });
      return;
    }

    // 3. Authenticated check: NEVER submit callback if unauthenticated
    if (!getAccessToken()) {
      setOauthToast({
        type: "error",
        message:
          "You must be signed in to connect an application. Please log in and restart the authorization flow.",
      });
      return;
    }

    // 4. Submit authenticated POST callback to backend
    setConnectingApp(true);
    oauthApi
      .completeCallback("github", { code, state })
      .then((res) => {
        setOauthToast({
          type: "success",
          message: res.message || "Successfully connected GitHub application.",
        });
        return loadConnections();
      })
      .catch((err) => {
        const msg = getApiErrorMessage(err, "Failed to connect GitHub application.");
        setOauthToast({
          type: "error",
          message: `GitHub connection failed: ${msg}`,
        });
      })
      .finally(() => {
        setConnectingApp(false);
      });
  }, [loadConnections]);

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

  const handleConnectGitHub = async () => {
    try {
      setConnectingApp(true);
      const res = await oauthApi.getAuthorizeUrl("github", "/settings");
      if (res.authorization_url) {
        window.location.href = res.authorization_url;
      }
    } catch (err) {
      setOauthToast({
        type: "error",
        message: `Could not initiate GitHub authorization: ${getApiErrorMessage(err)}`,
      });
      setConnectingApp(false);
    }
  };

  const handleDisconnect = async (providerName: string) => {
    try {
      setDisconnectingProvider(providerName);
      const res = await oauthApi.disconnect(providerName);
      setOauthToast({
        type: "info",
        message: res.message || `Disconnected ${providerName}.`,
      });
      await loadConnections();
    } catch (err) {
      setOauthToast({
        type: "error",
        message: `Failed to disconnect ${providerName}: ${getApiErrorMessage(err)}`,
      });
    } finally {
      setDisconnectingProvider(null);
    }
  };

  const getProviderConnection = (providerName: string) =>
    connections.find((c) => c.provider.toLowerCase() === providerName.toLowerCase());

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

            {/* Navigation Tabs */}
            <div className="flex items-center gap-2 border-b border-slate-200">
              <Link
                href="/settings"
                className="px-4 py-2.5 text-xs font-semibold text-blue-600 border-b-2 border-blue-600 transition-colors flex items-center gap-1.5"
              >
                <SettingsIcon size={14} />
                <span>System Settings</span>
              </Link>
              <Link
                href="/settings/memory"
                className="px-4 py-2.5 text-xs font-semibold text-slate-500 hover:text-slate-900 border-b-2 border-transparent transition-colors flex items-center gap-1.5"
              >
                <Brain size={14} />
                <span>Persistent Memories</span>
              </Link>
            </div>

            {/* Saved Toast Alert */}
            {showSavedToast && (
              <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 px-4 py-3 rounded-xl flex items-center gap-2 text-xs font-semibold shadow-xs animate-fade-in">
                <CheckCircle size={16} className="text-emerald-600" />
                <span>Configuration preferences saved successfully.</span>
              </div>
            )}

            {/* OAuth Status Notification Banner */}
            {oauthToast && (
              <div
                className={`p-3.5 rounded-xl border flex items-center justify-between text-xs transition-all shadow-xs ${
                  oauthToast.type === "success"
                    ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                    : oauthToast.type === "error"
                    ? "bg-red-50 border-red-200 text-red-800"
                    : "bg-blue-50 border-blue-200 text-blue-800"
                }`}
              >
                <div className="flex items-center gap-2">
                  {oauthToast.type === "success" && <CheckCircle size={16} className="text-emerald-600 shrink-0" />}
                  {oauthToast.type === "error" && <AlertCircle size={16} className="text-red-600 shrink-0" />}
                  {oauthToast.type === "info" && <ShieldCheck size={16} className="text-blue-600 shrink-0" />}
                  <span className="font-medium">{oauthToast.message}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setOauthToast(null)}
                  className="text-slate-400 hover:text-slate-600 p-1 cursor-pointer"
                  aria-label="Dismiss notification"
                >
                  <X size={14} />
                </button>
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

                {/* 4. Connected Personal Applications Card */}
                <div className="bg-white border border-slate-200/90 rounded-2xl p-5 md:p-6 shadow-2xs space-y-4">
                  <div className="border-b border-slate-100 pb-3 flex items-center justify-between">
                    <div>
                      <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                        <Link2 size={16} className="text-blue-600" />
                        Connected Personal Applications
                      </h2>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Manage third-party OAuth connections for agent search tools with AES-256-GCM vault security.
                      </p>
                    </div>
                    {connectionsLoading && <Loader2 size={14} className="animate-spin text-slate-400" />}
                  </div>

                  <div className="space-y-3">
                    {/* GitHub Application */}
                    {(() => {
                      const ghConn = getProviderConnection("github");
                      const isConnected = ghConn?.connection_status === "connected";
                      const isExpired = ghConn?.connection_status === "expired";
                      const isRevoked = ghConn?.connection_status === "revoked" || !ghConn;

                      return (
                        <div className="p-4 bg-slate-50 border border-slate-200/80 rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-3">
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-slate-900 text-xs">GitHub</span>
                              {isConnected && (
                                <span className="text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full font-bold uppercase tracking-wider flex items-center gap-1">
                                  <ShieldCheck size={11} /> Connected
                                </span>
                              )}
                              {isExpired && (
                                <span className="text-[10px] bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-bold uppercase tracking-wider flex items-center gap-1">
                                  <AlertCircle size={11} /> Expired
                                </span>
                              )}
                              {isRevoked && (
                                <span className="text-[10px] bg-slate-200/70 text-slate-600 border border-slate-300 px-2 py-0.5 rounded-full font-medium">
                                  Not Connected
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-500">
                              Read-only evidence search for private/public repositories, issues, and PRs via GitHubSearchTool.
                            </p>
                            {isConnected && ghConn && (
                              <div className="text-[10px] text-slate-400 flex items-center gap-3 pt-0.5">
                                <span>Scopes: {ghConn.scopes.join(", ") || "repo"}</span>
                                <span>Linked: {new Date(ghConn.created_at).toLocaleDateString()}</span>
                              </div>
                            )}
                          </div>

                          <div className="flex items-center gap-2 self-start md:self-auto">
                            {isConnected ? (
                              <button
                                type="button"
                                onClick={() => handleDisconnect("github")}
                                disabled={disconnectingProvider === "github"}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-200 bg-red-50 hover:bg-red-100 text-red-700 text-xs font-semibold transition-colors cursor-pointer disabled:opacity-50"
                              >
                                {disconnectingProvider === "github" ? (
                                  <Loader2 size={13} className="animate-spin" />
                                ) : (
                                  <Unlink size={13} />
                                )}
                                <span>Disconnect</span>
                              </button>
                            ) : isExpired ? (
                              <div className="flex items-center gap-2">
                                <button
                                  type="button"
                                  onClick={handleConnectGitHub}
                                  disabled={connectingApp}
                                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold shadow-2xs transition-colors cursor-pointer disabled:opacity-50"
                                >
                                  {connectingApp ? (
                                    <Loader2 size={13} className="animate-spin" />
                                  ) : (
                                    <RefreshCw size={13} />
                                  )}
                                  <span>Reconnect</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleDisconnect("github")}
                                  disabled={disconnectingProvider === "github"}
                                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 text-xs font-semibold transition-colors cursor-pointer"
                                >
                                  <span>Revoke</span>
                                </button>
                              </div>
                            ) : (
                              <button
                                type="button"
                                onClick={handleConnectGitHub}
                                disabled={connectingApp}
                                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shadow-2xs transition-colors cursor-pointer disabled:opacity-50"
                              >
                                {connectingApp ? (
                                  <Loader2 size={13} className="animate-spin" />
                                ) : (
                                  <ExternalLink size={13} />
                                )}
                                <span>Connect GitHub</span>
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })()}

                    {/* Coming Soon Providers (Phase 5.6.3+) */}
                    <div className="p-3 bg-slate-50/70 border border-slate-200/60 rounded-xl flex items-center justify-between opacity-75">
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-700 text-xs">Gmail & Google Drive</span>
                          <span className="text-[9px] bg-slate-200 text-slate-600 px-1.5 py-0.2 rounded font-medium">
                            Coming in Phase 5.6.3+
                          </span>
                        </div>
                        <p className="text-[10px] text-slate-500">
                          Personal message and drive document search (Google OAuth 2.0).
                        </p>
                      </div>
                      <button
                        type="button"
                        disabled
                        className="px-2.5 py-1 rounded-md text-[11px] font-medium bg-slate-100 text-slate-400 cursor-not-allowed border border-slate-200"
                      >
                        Unavailable
                      </button>
                    </div>

                    <div className="p-3 bg-slate-50/70 border border-slate-200/60 rounded-xl flex items-center justify-between opacity-75">
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-700 text-xs">LinkedIn</span>
                          <span className="text-[9px] bg-slate-200 text-slate-600 px-1.5 py-0.2 rounded font-medium">
                            Coming in Phase 5.6.3+
                          </span>
                        </div>
                        <p className="text-[10px] text-slate-500">
                          OIDC profile verification and member search.
                        </p>
                      </div>
                      <button
                        type="button"
                        disabled
                        className="px-2.5 py-1 rounded-md text-[11px] font-medium bg-slate-100 text-slate-400 cursor-not-allowed border border-slate-200"
                      >
                        Unavailable
                      </button>
                    </div>

                    {/* Inactive Notion & Jira Notice */}
                    <div className="p-2.5 bg-slate-100/60 border border-slate-200/60 rounded-lg">
                      <span className="text-[10px] text-slate-500 font-medium block">
                        Notion & Jira: Integrations remain inactive in configuration per Phase 5.6 requirements.
                      </span>
                    </div>
                  </div>
                </div>

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
