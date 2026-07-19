"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import {
  chatApi,
  ragApi,
  dashboardApi,
  ChatSessionResponse,
  ChatMessageResponse,
  RAGModelItem,
  CitationItem
} from "@/lib/api";
import {
  Send,
  Plus,
  Trash2,
  Cpu,
  Sliders,
  MessageSquare,
  Loader2,
  AlertCircle,
  Clock,
  Zap,
  DollarSign,
  BookOpen,
  ChevronDown,
  ChevronUp,
  X
} from "lucide-react";
import Navigation from "@/components/Navigation";
import { renderMarkdown } from "@/lib/markdown";

export default function ChatPage() {
  const [sessions, setSessions] = useState<ChatSessionResponse[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageResponse[]>([]);
  const [inputText, setInputText] = useState("");
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasDocuments, setHasDocuments] = useState(true);

  // Quick settings drawer toggle & options state
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [models, setModels] = useState<RAGModelItem[]>([]);
  const [provider, setProvider] = useState("gemini");
  const [selectedModel, setSelectedModel] = useState("gemini-3.5-flash");
  const [temperature, setTemperature] = useState(0.2);
  const [topK, setTopK] = useState(5);
  const [threshold, setThreshold] = useState(0.0);
  const [useReranker, setUseReranker] = useState(true);
  const [maxTokens, setMaxTokens] = useState(1000);

  // Observability details toggles
  const [expandedTraceId, setExpandedTraceId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const citationRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Fetch all chat sessions
  const fetchSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const list = await chatApi.listSessions();
      setSessions(list);
      if (list.length > 0 && !activeSessionId) {
        setActiveSessionId(list[0].id);
      }
    } catch (err) {
      console.error("Failed to load chat sessions:", err);
      setError("Failed to load conversation history.");
    } finally {
      setLoadingSessions(false);
    }
  }, [activeSessionId]);

  // Load configurations and check corpus size
  useEffect(() => {
    const loadInitData = async () => {
      try {
        const [modelList, dashboardStats] = await Promise.all([
          ragApi.getModels(),
          dashboardApi.getStatistics()
        ]);
        setModels(modelList);
        setHasDocuments(dashboardStats.total_documents > 0);

        // Load localStorage preferences
        const savedSettings = localStorage.getItem("rag_settings");
        if (savedSettings) {
          const parsed = JSON.parse(savedSettings);
          setProvider(parsed.provider || "gemini");
          setSelectedModel(parsed.model || "gemini-3.5-flash");
          setTemperature(parsed.temperature ?? 0.2);
          setTopK(parsed.topK ?? 5);
          setThreshold(parsed.threshold ?? 0.0);
          setUseReranker(parsed.useReranker ?? true);
          setMaxTokens(parsed.maxTokens ?? 1000);
        } else if (modelList.length > 0) {
          const geminiModels = modelList.filter((m) => m.provider === "gemini");
          if (geminiModels.length > 0) {
            setProvider("gemini");
            setSelectedModel(geminiModels[0].model_name);
          } else {
            setProvider(modelList[0].provider);
            setSelectedModel(modelList[0].model_name);
          }
        }
      } catch (err) {
        console.error("Failed to load initial configurations:", err);
      }
    };
    loadInitData();
    fetchSessions();
  }, [fetchSessions]);

  // Save configurations helper
  const saveQuickSettings = (updated: Record<string, any>) => {
    const current = {
      provider,
      model: selectedModel,
      temperature,
      topK,
      threshold,
      useReranker,
      maxTokens,
      ...updated
    };
    localStorage.setItem("rag_settings", JSON.stringify(current));
  };

  // Load messages when active session changes
  useEffect(() => {
    if (!activeSessionId) {
      setMessages([]);
      return;
    }

    const loadMessages = async () => {
      setLoadingMessages(true);
      setError(null);
      try {
        const sessionDetail = await chatApi.getSession(activeSessionId);
        setMessages(sessionDetail.messages || []);
      } catch (err) {
        console.error("Failed to load session messages:", err);
        setError("Could not load messages for this thread.");
      } finally {
        setLoadingMessages(false);
      }
    };

    loadMessages();
  }, [activeSessionId]);

  // Scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Create new session
  const handleCreateSession = async () => {
    try {
      setError(null);
      const newSession = await chatApi.createSession("New Conversation");
      setSessions((prev) => [newSession, ...prev]);
      setActiveSessionId(newSession.id);
    } catch (err) {
      console.error("Failed to create chat session:", err);
      setError("Failed to create new conversation.");
    }
  };

  // Delete session
  const handleDeleteSession = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    e.preventDefault();
    try {
      setError(null);
      await chatApi.deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (activeSessionId === id) {
        setActiveSessionId(null);
        setMessages([]);
      }
    } catch (err) {
      console.error("Failed to delete session:", err);
      setError("Failed to delete conversation.");
    }
  };

  // Click citation to scroll down to item reference
  const handleScrollToCitation = (idx: number) => {
    const targetKey = `citation-${idx}`;
    const el = citationRefs.current[targetKey];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("border-indigo-500", "bg-indigo-950/20", "scale-[1.02]");
      setTimeout(() => {
        el.classList.remove("border-indigo-500", "bg-indigo-950/20", "scale-[1.02]");
      }, 3000);
    }
  };

  // Cost calculator
  const calculateCost = (prompt: number, completion: number, prov: string): string => {
    const p = prov.toLowerCase();
    let promptRate = 0.0;
    let completionRate = 0.0;

    if (p === "gemini") {
      promptRate = 0.075 / 1000000;
      completionRate = 0.3 / 1000000;
    } else if (p === "openai") {
      promptRate = 0.15 / 1000000;
      completionRate = 0.6 / 1000000;
    }

    const cost = prompt * promptRate + completion * completionRate;
    return cost === 0 ? "$0.0000" : `$${cost.toFixed(6)}`;
  };

  // Send message stream
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || !activeSessionId || sendingMessage) return;

    const userQuestion = inputText.trim();
    setInputText("");
    setError(null);
    setSendingMessage(true);

    const userMsgId = "temp-user-" + Date.now();
    const userMsgPlaceholder: ChatMessageResponse = {
      id: userMsgId,
      role: "user",
      content: userQuestion,
      created_at: new Date().toISOString()
    };
    setMessages((prev) => [...prev, userMsgPlaceholder]);

    const assistantMsgId = "temp-assistant-" + Date.now();
    const assistantMsgPlaceholder: ChatMessageResponse = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString()
    };
    setMessages((prev) => [...prev, assistantMsgPlaceholder]);

    try {
      const response = await chatApi.sendMessageStream(activeSessionId, {
        question: userQuestion,
        provider,
        model: selectedModel,
        temperature,
        max_tokens: maxTokens,
        use_reranker: useReranker,
        threshold,
        top_k: topK
      });

      if (!response.ok) {
        throw new Error(`Connection failed: ${response.status} ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Response body stream is not readable.");
      }

      const decoder = new TextDecoder("utf-8");
      let assistantText = "";
      let parsedCitations: CitationItem[] = [];
      let tokenUsage: any = null;
      let latencyLog: any = null;
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          const lines = part.split("\n");
          let event = "";
          let data = "";

          for (const line of lines) {
            if (line.startsWith("event: ")) {
              event = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              data = line.slice(6).trim();
            }
          }

          if (!data) continue;

          try {
            if (event === "citations") {
              parsedCitations = JSON.parse(data);
            } else if (event === "token") {
              const token = JSON.parse(data);
              assistantText += token;
            } else if (event === "done") {
              const donePayload = JSON.parse(data);
              tokenUsage = donePayload.tokens;
              latencyLog = donePayload.latency;
            }
          } catch (err) {
            console.warn("Failed to parse SSE line data:", err);
          }

          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? {
                    ...msg,
                    content: assistantText,
                    citations: parsedCitations,
                    tokens: tokenUsage || undefined,
                    latency: latencyLog || undefined
                  }
                : msg
            )
          );
        }
      }

      // Re-fetch sessions list to update titles in sidebar
      const list = await chatApi.listSessions();
      setSessions(list);
    } catch (err: any) {
      console.error("Failed to stream answer:", err);
      setError("Connection closed prematurely. Try modifying temperature parameters.");
      setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId));
    } finally {
      setSendingMessage(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100 font-sans pl-0 md:pl-64">
      {/* Sidebar Navigation */}
      <Navigation />

      {/* Main Workspace Layout */}
      <div className="flex-1 flex flex-row h-screen overflow-hidden relative z-10">
        
        {/* Chat History Panel */}
        <aside className="w-80 border-r border-slate-900 bg-slate-950 flex flex-col h-full shrink-0">
          <div className="p-4 border-b border-slate-900 flex items-center justify-between">
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <MessageSquare size={16} className="text-indigo-400" />
              Conversations
            </h2>
            <button
              onClick={handleCreateSession}
              className="p-1.5 rounded-lg bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 border border-indigo-500/20 transition-all cursor-pointer"
              title="New thread"
            >
              <Plus size={15} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-1">
            {loadingSessions ? (
              <div className="flex items-center justify-center py-8 text-slate-500 text-xs gap-2">
                <Loader2 className="animate-spin text-indigo-500" size={14} />
                <span>Loading threads…</span>
              </div>
            ) : sessions.length === 0 ? (
              <div className="text-center py-12 text-slate-500 text-xs">
                No conversations yet.
              </div>
            ) : (
              sessions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => setActiveSessionId(s.id)}
                  className={`group flex items-center justify-between px-3.5 py-3 rounded-xl cursor-pointer border text-xs font-semibold transition-all ${
                    activeSessionId === s.id
                      ? "bg-slate-900/60 border-slate-800 text-white"
                      : "bg-transparent border-transparent text-slate-400 hover:bg-slate-900/30 hover:text-slate-300"
                  }`}
                >
                  <div className="truncate pr-2 font-medium flex-1">
                    {s.title}
                  </div>
                  <button
                    onClick={(e) => handleDeleteSession(e, s.id)}
                    className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-500/10 border border-transparent hover:border-red-500/25 text-slate-500 hover:text-red-400 rounded transition-all cursor-pointer"
                    title="Delete thread"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* Chat Thread Panel */}
        <main className="flex-1 flex flex-col h-full bg-slate-950/40 relative">
          
          {/* Top Config Bar */}
          <header className="px-6 py-4 border-b border-slate-900 flex items-center justify-between bg-slate-950/60 backdrop-blur-md">
            <div>
              <h1 className="text-base font-bold text-white">RAG Chat Workspace</h1>
              <p className="text-[10px] text-slate-500 mt-0.5">Grounded SaaS retrieval chat with source citations.</p>
            </div>
            
            {/* Quick parameter display toggles */}
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300">
                <Cpu size={13} className="text-indigo-400" />
                <span className="font-mono text-[10px]">
                  {selectedModel} ({provider})
                </span>
              </div>
              <button
                onClick={() => setIsConfigOpen(!isConfigOpen)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-850 border border-slate-800 text-xs text-slate-300 transition-colors cursor-pointer"
              >
                <Sliders size={13} className="text-indigo-400" />
                <span>Configure</span>
              </button>
            </div>
          </header>

          {/* Quick Settings Dropdown Overlay */}
          {isConfigOpen && (
            <div className="absolute top-16 right-6 w-80 bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-2xl z-20 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                <h3 className="text-xs font-bold text-white flex items-center gap-2">
                  <Sliders size={14} className="text-indigo-400" />
                  Grounded Parameters
                </h3>
                <button
                  onClick={() => setIsConfigOpen(false)}
                  className="text-slate-400 hover:text-white"
                >
                  <X size={14} />
                </button>
              </div>

              <div className="space-y-3.5 text-xs">
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
                        setSelectedModel(filtered[0].model_name);
                        saveQuickSettings({ provider: p, model: filtered[0].model_name });
                      } else {
                        saveQuickSettings({ provider: p });
                      }
                    }}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white focus:outline-none"
                  >
                    <option value="gemini">Google Gemini</option>
                    <option value="openai">OpenAI GPT</option>
                    <option value="ollama">Ollama (Local)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1.5">
                    Model selection
                  </label>
                  <select
                    value={selectedModel}
                    onChange={(e) => {
                      setSelectedModel(e.target.value);
                      saveQuickSettings({ model: e.target.value });
                    }}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white focus:outline-none"
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

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">
                      Temperature ({temperature})
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.1"
                      value={temperature}
                      onChange={(e) => {
                        const v = parseFloat(e.target.value);
                        setTemperature(v);
                        saveQuickSettings({ temperature: v });
                      }}
                      className="w-full accent-indigo-500 cursor-pointer"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">
                      Top Chunks ({topK})
                    </label>
                    <input
                      type="range"
                      min="1"
                      max="15"
                      step="1"
                      value={topK}
                      onChange={(e) => {
                        const v = parseInt(e.target.value);
                        setTopK(v);
                        saveQuickSettings({ topK: v });
                      }}
                      className="w-full accent-indigo-500 cursor-pointer"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Messages Logs Area */}
          <div
            ref={scrollContainerRef}
            className="flex-1 overflow-y-auto px-6 py-6 space-y-6 scrollbar-thin"
          >
            {!hasDocuments && (
              <div className="bg-amber-950/20 border border-amber-900/40 rounded-xl p-4 flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs font-semibold text-white">No documents uploaded</p>
                  <p className="text-[11px] text-amber-300 mt-0.5">
                    Grounded citations require context. Upload PDF/text files in the{" "}
                    <Link href="/documents" className="underline font-bold text-white">
                      Documents Workspace
                    </Link>{" "}
                    first.
                  </p>
                </div>
              </div>
            )}

            {error && (
              <div className="bg-rose-950/20 border border-rose-900/40 rounded-xl p-4 flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-rose-400 shrink-0 mt-0.5" />
                <p className="text-xs text-rose-300">{error}</p>
              </div>
            )}

            {!activeSessionId ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-500 space-y-3">
                <MessageSquare size={32} className="opacity-25" />
                <div className="text-sm font-medium">Create or select a thread to begin</div>
              </div>
            ) : loadingMessages ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-500 text-xs gap-2">
                <Loader2 className="animate-spin text-indigo-500" size={20} />
                <span>Loading chat history…</span>
              </div>
            ) : messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-500 space-y-3">
                <MessageSquare size={24} className="opacity-25" />
                <div className="text-xs text-slate-400">
                  No messages in this workspace. Ask your first query below!
                </div>
              </div>
            ) : (
              messages.map((m, idx) => {
                const isUser = m.role === "user";
                return (
                  <div
                    key={m.id || idx}
                    className={`flex flex-col max-w-[85%] ${
                      isUser ? "ml-auto items-end" : "mr-auto items-start"
                    }`}
                  >
                    <span className="text-[10px] text-slate-500 mb-1 font-semibold uppercase tracking-wider">
                      {isUser ? "You" : "Assistant"}
                    </span>
                    <div
                      className={`px-4 py-3.5 rounded-2xl text-sm leading-relaxed border shadow-sm ${
                        isUser
                          ? "bg-indigo-600/10 border-indigo-500/20 text-white rounded-br-none"
                          : "bg-slate-900/40 border-slate-900 text-slate-200 rounded-bl-none font-sans"
                      }`}
                    >
                      {isUser ? (
                        <p className="text-xs md:text-sm font-sans">{m.content}</p>
                      ) : m.content ? (
                        renderMarkdown(m.content, handleScrollToCitation)
                      ) : (
                        <span className="flex items-center gap-1.5 text-xs text-slate-500">
                          <Loader2 className="animate-spin text-indigo-500" size={12} />
                          Reasoning over documents…
                        </span>
                      )}

                      {/* Expandable Citations Section */}
                      {!isUser && m.citations && m.citations.length > 0 && (
                        <div className="mt-4 pt-3 border-t border-slate-900/80 space-y-2">
                          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                            Grounding sources:
                          </span>
                          <div className="grid grid-cols-1 gap-2">
                            {m.citations.map((c) => (
                              <div
                                key={c.citation_index}
                                ref={(el) => {
                                  citationRefs.current[`citation-${c.citation_index}`] = el;
                                }}
                                className="bg-slate-950/60 border border-slate-850 hover:border-slate-800 rounded-xl p-3 text-xs flex flex-col gap-1.5 transition-all duration-300"
                              >
                                <div className="flex items-center justify-between gap-4">
                                  <div className="flex items-center gap-1.5">
                                    <span className="w-4.5 h-4.5 rounded bg-indigo-950 border border-indigo-900/40 text-[9px] text-indigo-400 flex items-center justify-center font-mono font-bold">
                                      {c.citation_index}
                                    </span>
                                    <span className="text-[10px] text-slate-400 font-mono">
                                      Similarity: {c.score.toFixed(4)}
                                    </span>
                                  </div>
                                  <Link
                                    href={`/documents/${c.document_id}`}
                                    className="text-[10px] font-semibold text-indigo-400 hover:text-indigo-300 truncate max-w-[150px]"
                                    title={c.document_title}
                                  >
                                    {c.document_title} · p.{c.page_number}
                                  </Link>
                                </div>
                                <p className="text-[11px] text-slate-300 leading-relaxed font-sans bg-slate-900/20 border border-slate-900/50 rounded-lg p-2">
                                  {c.text}
                                </p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Developer debug trace footer */}
                      {!isUser && (m.latency || m.tokens) && (
                        <div className="mt-3 pt-2.5 border-t border-slate-900/50">
                          <button
                            onClick={() =>
                              setExpandedTraceId(expandedTraceId === m.id ? null : m.id)
                            }
                            className="text-[9px] font-mono text-indigo-400 hover:text-indigo-300 flex items-center gap-1 cursor-pointer font-bold uppercase tracking-wider"
                          >
                            <span>Observability Log</span>
                            {expandedTraceId === m.id ? (
                              <ChevronUp size={10} />
                            ) : (
                              <ChevronDown size={10} />
                            )}
                          </button>

                          {expandedTraceId === m.id && (
                            <div className="mt-2.5 bg-slate-950/60 border border-slate-850/80 rounded-xl p-3.5 font-mono text-[10px] text-slate-400 space-y-1.5 shadow-inner">
                              <div className="flex justify-between border-b border-slate-900 pb-1">
                                <span>LLM Model</span>
                                <span className="text-white font-bold">{selectedModel}</span>
                              </div>
                              <div className="flex justify-between border-b border-slate-900 pb-1">
                                <span>Total Latency</span>
                                <span className="text-white flex items-center gap-1 font-bold">
                                  <Clock size={10} className="text-amber-400" />
                                  {m.latency?.total_ms ?? 0} ms
                                </span>
                              </div>
                              <div className="flex justify-between border-b border-slate-900 pb-1">
                                <span>Retrieval Time</span>
                                <span className="text-white flex items-center gap-1 font-bold">
                                  <Zap size={10} className="text-indigo-400" />
                                  {m.latency?.retrieval_ms ?? 0} ms
                                </span>
                              </div>
                              <div className="flex justify-between border-b border-slate-900 pb-1">
                                <span>LLM Time</span>
                                <span className="text-white font-bold">
                                  {m.latency?.llm_ms ?? 0} ms
                                </span>
                              </div>
                              <div className="flex justify-between border-b border-slate-900 pb-1">
                                <span>Tokens (P / C)</span>
                                <span className="text-white font-bold">
                                  {m.tokens?.prompt_tokens ?? 0} /{" "}
                                  {m.tokens?.completion_tokens ?? 0}
                                </span>
                              </div>
                              <div className="flex justify-between pt-0.5">
                                <span>Est. Execution Cost</span>
                                <span className="text-emerald-400 font-bold flex items-center">
                                  <DollarSign size={10} />
                                  {calculateCost(
                                    m.tokens?.prompt_tokens ?? 0,
                                    m.tokens?.completion_tokens ?? 0,
                                    provider
                                  )}
                                </span>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}

            {/* Bouncing Dots Loading bubble */}
            {sendingMessage &&
              messages.length > 0 &&
              messages[messages.length - 1].content === "" && (
                <div className="flex flex-col mr-auto items-start max-w-[85%]">
                  <span className="text-[10px] text-slate-500 mb-1 font-semibold uppercase tracking-wider">
                    Assistant
                  </span>
                  <div className="bg-slate-900/40 border border-slate-900 text-slate-200 rounded-2xl rounded-bl-none px-4 py-3 flex items-center gap-1">
                    <span className="text-xs text-slate-500 font-mono flex items-center gap-2">
                      <Loader2 className="animate-spin text-indigo-500" size={12} />
                      Synthesizing cited answer…
                    </span>
                  </div>
                </div>
              )}
            <div ref={messagesEndRef} />
          </div>

          {/* Chat Form Footer */}
          <footer className="p-4 border-t border-slate-900 bg-slate-950/60 backdrop-blur-md">
            <form
              onSubmit={handleSendMessage}
              className="max-w-4xl mx-auto flex items-center gap-2 relative"
            >
              <input
                type="text"
                disabled={!activeSessionId || sendingMessage}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder={
                  activeSessionId
                    ? "Ask anything about your documents…"
                    : "Select a thread to start chatting"
                }
                className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3.5 text-xs md:text-sm text-white placeholder-slate-500
                           focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/25 transition-all
                           disabled:opacity-50 disabled:cursor-not-allowed"
              />
              <button
                type="submit"
                disabled={!activeSessionId || !inputText.trim() || sendingMessage}
                className="p-3.5 bg-gradient-to-br from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700
                           border border-indigo-500/20 hover:border-indigo-500/40 text-white rounded-xl shadow-lg hover:scale-105 transition-all
                           disabled:opacity-50 disabled:cursor-not-allowed disabled:scale-100 cursor-pointer"
              >
                <Send size={15} />
              </button>
            </form>
          </footer>
        </main>
      </div>
    </div>
  );
}
