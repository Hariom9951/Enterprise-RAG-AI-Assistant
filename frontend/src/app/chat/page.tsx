"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import {
  chatApi,
  ragApi,
  dashboardApi,
  userApi,
  ChatMessageResponse,
  RAGModelItem,
  CitationItem,
  UserResponse,
  RAGTokenUsageInfo,
  RAGLatencyInfo
} from "@/lib/api";
import {
  Send,
  MessageSquare,
  Loader2,
  AlertCircle,
  Zap,
  Copy,
  ThumbsUp,
  ThumbsDown,
  Check,
  Globe,
  Sparkles,
  Paperclip,
  FileText,
  ChevronDown,
  ChevronUp
} from "lucide-react";
import AppSidebar from "@/components/layout/AppSidebar";
import AppTopbar from "@/components/layout/AppTopbar";
import AppRightPanel from "@/components/layout/AppRightPanel";
import { renderMarkdown } from "@/lib/markdown";

export default function ChatPage() {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageResponse[]>([]);
  const [inputText, setInputText] = useState("");
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasDocuments, setHasDocuments] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // Quick settings & model state
  const [models, setModels] = useState<RAGModelItem[]>([]);
  const [selectedModel, setSelectedModel] = useState("gemini-3.5-flash");
  const [temperature, setTemperature] = useState(0.2);
  const [topK, setTopK] = useState(5);
  const [threshold, setThreshold] = useState(0.0);
  const [useReranker, setUseReranker] = useState(true);
  const [maxTokens, setMaxTokens] = useState(1000);
  const [deepResearchActive, setDeepResearchActive] = useState(false);

  // Observability details toggles
  const [expandedTraceId, setExpandedTraceId] = useState<string | null>(null);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const [activeCitations, setActiveCitations] = useState<CitationItem[]>([]);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

  // Fetch all chat sessions
  const fetchSessions = useCallback(async () => {
    try {
      const list = await chatApi.listSessions();
      if (list.length > 0 && !activeSessionId) {
        setActiveSessionId(list[0].id);
      }
    } catch (err) {
      console.error("Failed to load chat sessions:", err);
      setError("Failed to load conversation history.");
    }
  }, [activeSessionId]);

  // Load user profile & initial configurations
  useEffect(() => {
    let isMounted = true;
    const loadInitData = async () => {
      try {
        const [profile, modelList, dashboardStats] = await Promise.all([
          userApi.me().catch(() => null),
          ragApi.getModels().catch(() => []),
          dashboardApi.getStatistics().catch(() => ({ total_documents: 1 }))
        ]);

        if (!isMounted) return;
        if (profile) setUser(profile);
        setModels(modelList);
        setHasDocuments(dashboardStats.total_documents > 0);

        // Load saved preferences from localStorage
        const savedSettings = localStorage.getItem("rag_settings");
        if (savedSettings) {
          const parsed = JSON.parse(savedSettings);
          setSelectedModel(parsed.model || "gemini-3.5-flash");
          setTemperature(parsed.temperature ?? 0.2);
          setTopK(parsed.topK ?? 5);
          setThreshold(parsed.threshold ?? 0.0);
          setUseReranker(parsed.useReranker ?? true);
          setMaxTokens(parsed.maxTokens ?? 1000);
        } else if (modelList.length > 0) {
          setSelectedModel(modelList[0].model_name);
        }
      } catch (err) {
        console.error("Failed to load initial configurations:", err);
      }
    };
    void loadInitData();
    void fetchSessions();
    return () => {
      isMounted = false;
    };
  }, [fetchSessions]);

  // Load messages when active session changes
  useEffect(() => {
    if (!activeSessionId) {
      return;
    }

    const loadMessages = async () => {
      setLoadingMessages(true);
      setError(null);
      try {
        const sessionDetail = await chatApi.getSession(activeSessionId);
        const msgs = sessionDetail.messages || [];
        setMessages(msgs);

        // Find latest citations to populate right panel
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].citations && msgs[i].citations!.length > 0) {
            setActiveCitations(msgs[i].citations!);
            break;
          }
        }
      } catch (err) {
        console.error("Failed to load session messages:", err);
        setError("Could not load messages for this thread.");
      } finally {
        setLoadingMessages(false);
      }
    };

    loadMessages();
  }, [activeSessionId]);

  // Auto-scroll to bottom on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sendingMessage]);

  // Create new session
  const handleCreateSession = async () => {
    try {
      setError(null);
      const newSession = await chatApi.createSession("New Conversation");
      setActiveSessionId(newSession.id);
      setMessages([]);
      setActiveCitations([]);
    } catch (err) {
      console.error("Failed to create chat session:", err);
      setError("Failed to create new conversation.");
    }
  };


  // Copy message text helper
  const handleCopyMessage = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedMsgId(id);
    setTimeout(() => setCopiedMsgId(null), 2000);
  };

  // Scroll to citation reference in message
  const handleScrollToCitation = (idx: number) => {
    const el = document.getElementById(`inline-citation-${idx}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("ring-2", "ring-blue-500", "bg-blue-50");
      setTimeout(() => {
        el.classList.remove("ring-2", "ring-blue-500", "bg-blue-50");
      }, 3000);
    }
  };

  // Format time (e.g. "10:24 AM")
  const formatTime = (isoString?: string) => {
    if (!isoString) return "";
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
    } catch {
      return "";
    }
  };

  // Send message stream
  const executeSendMessage = async (textToSend: string) => {
    if (!textToSend.trim() || sendingMessage) return;

    let targetSessionId = activeSessionId;
    // Auto-create session if none active
    if (!targetSessionId) {
      try {
        const newSession = await chatApi.createSession(
          textToSend.slice(0, 30) + (textToSend.length > 30 ? "..." : "")
        );
        setActiveSessionId(newSession.id);
        targetSessionId = newSession.id;
      } catch (err) {
        console.error("Failed to create session on message send:", err);
        setError("Could not initialize session.");
        return;
      }
    }

    const userQuestion = textToSend.trim();
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

    let assistantText = "";
    let parsedCitations: CitationItem[] = [];

    try {
      const response = await chatApi.sendMessageStream(targetSessionId, {
        question: userQuestion,
        provider: "gemini",
        model: selectedModel,
        temperature,
        max_tokens: maxTokens,
        use_reranker: useReranker || deepResearchActive,
        threshold,
        top_k: deepResearchActive ? Math.max(topK, 8) : topK
      });

      if (!response.ok) {
        throw new Error(`Connection failed: ${response.status} ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Response body stream is not readable.");
      }

      const decoder = new TextDecoder("utf-8");
      let tokenUsage: RAGTokenUsageInfo | undefined = undefined;
      let latencyLog: RAGLatencyInfo | undefined = undefined;
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
              setActiveCitations(parsedCitations);
            } else if (event === "token") {
              const token = JSON.parse(data);
              assistantText += token;
            } else if (event === "done") {
              const donePayload = JSON.parse(data);
              tokenUsage = donePayload.tokens;
              latencyLog = donePayload.latency;
            } else if (event === "error") {
              const cleanErr = data.replace(/^LLM Streaming generation failed:\s*/i, "").trim();
              if (
                cleanErr.includes("Gemini usage limit reached") ||
                cleanErr.includes("quota") ||
                cleanErr.includes("RESOURCE_EXHAUSTED") ||
                cleanErr.includes("429")
              ) {
                assistantText =
                  "Gemini usage limit reached. Your retrieved sources are available, but a new AI response cannot be generated right now. Please try again after the quota resets.";
                setError(
                  "Gemini usage limit reached. Your retrieved sources are available, but a new AI response cannot be generated right now. Please try again after the quota resets."
                );
              } else {
                assistantText = `⚠️ **Gemini Generation Error:** ${cleanErr}`;
                setError(cleanErr);
              }
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
                    tokens: tokenUsage,
                    latency: latencyLog
                  }
                : msg
            )
          );
        }
      }

      // Refresh sessions list in background
      await chatApi.listSessions().catch(() => []);
    } catch (err: unknown) {
      console.error("Failed to stream answer:", err);
      const isQuota =
        assistantText.includes("Gemini usage limit reached") ||
        (err instanceof Error && err.message.includes("429"));
      if (isQuota) {
        setError(
          "Gemini usage limit reached. Your retrieved sources are available, but a new AI response cannot be generated right now. Please try again after the quota resets."
        );
      } else {
        setError(
          "Response interrupted. Please check your Gemini API key and backend connectivity."
        );
      }
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id === assistantMsgId) {
            const preservedContent =
              m.content ||
              assistantText ||
              "Gemini usage limit reached. Your retrieved sources are available, but a new AI response cannot be generated right now. Please try again after the quota resets.";
            return {
              ...m,
              content: preservedContent,
              citations: m.citations && m.citations.length > 0 ? m.citations : parsedCitations,
            };
          }
          return m;
        })
      );
    } finally {
      setSendingMessage(false);
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    executeSendMessage(inputText);
  };

  // User initials
  const userInitials = user?.full_name
    ? user.full_name
        .split(" ")
        .map((n) => n[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "HY";

  const firstName = user?.full_name ? user.full_name.split(" ")[0] : "Hariom";

  // Starter feature cards
  const starterCards = [
    {
      title: "Ask Questions",
      description: "Get accurate answers from your documents",
      prompt: "Summarize the key findings from the project documentation and provide the main recommendations.",
      icon: (
        <div className="w-8 h-8 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center">
          <MessageSquare size={16} />
        </div>
      )
    },
    {
      title: "Analyze Documents",
      description: "Summarize and extract key insights",
      prompt: "Extract the core requirements, architecture decisions, and potential risks mentioned in the documents.",
      icon: (
        <div className="w-8 h-8 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center">
          <FileText size={16} />
        </div>
      )
    },
    {
      title: "Compare Information",
      description: "Find relationships across multiple sources",
      prompt: "Compare the performance metrics, latency benchmarks, and retrieval strategies across the documentation.",
      icon: (
        <div className="w-8 h-8 rounded-lg bg-purple-100 text-purple-600 flex items-center justify-center">
          <Sparkles size={16} />
        </div>
      )
    },
    {
      title: "Generate Reports",
      description: "Create structured reports with citations",
      prompt: "Generate an executive summary report covering system capabilities, security guidelines, and next steps.",
      icon: (
        <div className="w-8 h-8 rounded-lg bg-purple-100 text-purple-600 flex items-center justify-center">
          <Zap size={16} />
        </div>
      )
    }
  ];

  return (
    <div className="flex h-screen bg-[#F8FAFC] text-slate-800 overflow-hidden font-sans">
      {/* ── Left Sidebar (Dark Navy) ─────────────────────────────── */}
      <AppSidebar
        onNewChat={handleCreateSession}
        isMobileOpen={mobileSidebarOpen}
        onCloseMobile={() => setMobileSidebarOpen(false)}
      />

      {/* ── Main Layout (Center + Right Panel) ───────────────────── */}
      <div className="flex-1 flex flex-col md:pl-64 h-full overflow-hidden">
        {/* Topbar */}
        <AppTopbar
          onToggleMobileSidebar={() => setMobileSidebarOpen(true)}
          onSearchSubmit={(q) => executeSendMessage(q)}
        />

        {/* Workspace Body */}
        <div className="flex-1 flex flex-row overflow-hidden relative">
          
          {/* ── Center Chat Stream & Composer ────────────────────── */}
          <main className="flex-1 flex flex-col h-full bg-[#F8FAFC] overflow-hidden relative">
            
            {/* Messages Scroll Area */}
            <div
              ref={scrollContainerRef}
              className="flex-1 overflow-y-auto px-4 md:px-8 py-6 space-y-6 scrollbar-thin max-w-4xl w-full mx-auto"
            >
              {/* No Documents Banner */}
              {!hasDocuments && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 flex items-start gap-3 text-xs text-amber-800 shadow-2xs">
                  <AlertCircle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold block">Knowledge Base is Empty</span>
                    <span className="text-[11px] text-amber-700">
                      Upload documents in the{" "}
                      <Link href="/documents" className="font-bold underline hover:text-amber-900">
                        Documents Workspace
                      </Link>{" "}
                      to enable grounded retrieval.
                    </span>
                  </div>
                </div>
              )}

              {/* Error banner */}
              {error && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-3.5 flex items-start gap-3 text-xs text-red-800 shadow-2xs">
                  <AlertCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
                  <p className="flex-1">{error}</p>
                </div>
              )}

              {/* Empty State Welcome Screen */}
              {messages.length === 0 && !loadingMessages && (
                <div className="pt-6 pb-4 space-y-8 animate-fade-in">
                  {/* Greeting Header */}
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-2xl">👋</span>
                      <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
                        Hello, {firstName}!
                      </h1>
                    </div>
                    <p className="text-xs md:text-sm text-slate-500">
                      Your Enterprise AI Assistant powered by RAG and Gemini
                    </p>
                  </div>

                  {/* 4 Feature Starter Cards Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                    {starterCards.map((card, idx) => (
                      <button
                        key={idx}
                        onClick={() => executeSendMessage(card.prompt)}
                        className="bg-white hover:bg-slate-50 border border-slate-200/90 rounded-2xl p-4 text-left transition-all duration-150 shadow-2xs hover:shadow-sm hover:border-blue-300 group cursor-pointer flex flex-col justify-between"
                      >
                        <div>
                          <div className="mb-3">{card.icon}</div>
                          <h3 className="text-xs md:text-sm font-bold text-slate-900 group-hover:text-blue-600 transition-colors">
                            {card.title}
                          </h3>
                          <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                            {card.description}
                          </p>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Loading indicator */}
              {loadingMessages && (
                <div className="py-20 flex flex-col items-center justify-center text-xs text-slate-400 gap-2">
                  <Loader2 className="animate-spin text-blue-600" size={24} />
                  <span>Loading conversation…</span>
                </div>
              )}

              {/* Messages List */}
              {messages.map((m, idx) => {
                const isUser = m.role === "user";

                if (isUser) {
                  return (
                    <div key={m.id || idx} className="flex justify-end gap-2.5 items-end pl-8">
                      <div className="flex flex-col items-end max-w-xl">
                        <div className="bg-[#E0E7FF]/70 text-slate-800 border border-indigo-100 rounded-2xl rounded-br-xs px-4 py-3 text-xs md:text-sm shadow-2xs leading-relaxed">
                          {m.content}
                        </div>
                        <span className="text-[10px] text-slate-400 mt-1 mr-1">
                          {formatTime(m.created_at)}
                        </span>
                      </div>
                      <div className="w-7 h-7 rounded-full bg-[#10B981] text-white text-[10px] font-bold flex items-center justify-center shrink-0 mb-4 shadow-2xs">
                        {userInitials}
                      </div>
                    </div>
                  );
                }

                // Assistant Message Card
                return (
                  <div key={m.id || idx} className="flex items-start gap-3 pr-2 md:pr-8">
                    {/* Cube Avatar */}
                    <div className="w-8 h-8 rounded-lg bg-[#0B132B] text-white flex items-center justify-center shrink-0 shadow-xs mt-0.5">
                      <svg
                        className="w-4 h-4 text-blue-400"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                        <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                        <line x1="12" y1="22.08" x2="12" y2="12" />
                      </svg>
                    </div>

                    <div className="flex-1 min-w-0 bg-white border border-slate-200/90 rounded-2xl p-4 md:p-5 shadow-2xs space-y-3">
                      {/* Top Action Row */}
                      <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                        <span className="text-[11px] font-semibold text-slate-700 flex items-center gap-1.5">
                          <span>Aegis Assistant</span>
                          <span className="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded font-mono font-medium">
                            Gemini
                          </span>
                        </span>

                        <div className="flex items-center gap-1 text-slate-400">
                          <button
                            onClick={() => handleCopyMessage(m.id || String(idx), m.content)}
                            className="p-1 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors"
                            title="Copy response"
                          >
                            {copiedMsgId === (m.id || String(idx)) ? (
                              <Check size={13} className="text-emerald-600" />
                            ) : (
                              <Copy size={13} />
                            )}
                          </button>
                          <button
                            className="p-1 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors"
                            title="Good response"
                          >
                            <ThumbsUp size={13} />
                          </button>
                          <button
                            className="p-1 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors"
                            title="Poor response"
                          >
                            <ThumbsDown size={13} />
                          </button>
                        </div>
                      </div>

                      {/* Message Content */}
                      <div className="text-xs md:text-sm leading-relaxed text-slate-800">
                        {m.content ? (
                          renderMarkdown(m.content, handleScrollToCitation)
                        ) : (
                          <div className="flex items-center gap-2 text-slate-400 py-2 font-medium">
                            <Loader2 className="animate-spin text-blue-600" size={16} />
                            <span>Retrieving knowledge and synthesizing response…</span>
                          </div>
                        )}
                      </div>

                      {/* Inline Citations Drawer / Cards */}
                      {m.citations && m.citations.length > 0 && (
                        <div className="pt-3 border-t border-slate-100">
                          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 mb-2">
                            <span>Sources ({m.citations.length})</span>
                          </div>

                          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                            {m.citations.map((c) => {
                              const isPdf = c.document_title.toLowerCase().endsWith(".pdf");
                              return (
                                <div
                                  key={c.citation_index}
                                  id={`inline-citation-${c.citation_index}`}
                                  className="p-2.5 bg-slate-50 border border-slate-200/80 hover:border-blue-300 rounded-xl text-left transition-all"
                                >
                                  <div className="flex items-center gap-2 mb-1">
                                    <div
                                      className={`w-5 h-5 rounded flex items-center justify-center text-[8px] font-bold uppercase ${
                                        isPdf ? "bg-red-100 text-red-600" : "bg-blue-100 text-blue-600"
                                      }`}
                                    >
                                      {isPdf ? "PDF" : "DOC"}
                                    </div>
                                    <span
                                      className="text-xs font-semibold text-slate-800 truncate flex-1"
                                      title={c.document_title}
                                    >
                                      {c.document_title}
                                    </span>
                                  </div>
                                  <div className="text-[10px] text-slate-500 font-medium">
                                    Page {c.page_number}
                                  </div>
                                  <p className="mt-1 text-[11px] text-slate-600 line-clamp-2 italic leading-relaxed">
                                    &ldquo;{c.text}&rdquo;
                                  </p>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* Observability Log Toggle */}
                      {(m.latency || m.tokens) && (
                        <div className="pt-2 border-t border-slate-100">
                          <button
                            onClick={() =>
                              setExpandedTraceId(expandedTraceId === m.id ? null : m.id)
                            }
                            className="text-[10px] font-mono font-medium text-slate-500 hover:text-blue-600 flex items-center gap-1 cursor-pointer"
                          >
                            <span>Observability Trace</span>
                            {expandedTraceId === m.id ? (
                              <ChevronUp size={10} />
                            ) : (
                              <ChevronDown size={10} />
                            )}
                          </button>

                          {expandedTraceId === m.id && (
                            <div className="mt-2 bg-slate-50 border border-slate-200 rounded-xl p-3 font-mono text-[10px] text-slate-600 space-y-1">
                              <div className="flex justify-between">
                                <span>Total Latency</span>
                                <span className="font-bold text-slate-800">
                                  {m.latency?.total_ms ?? 0} ms
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span>Retrieval Time</span>
                                <span className="text-blue-600 font-bold">
                                  {m.latency?.retrieval_ms ?? 0} ms
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span>Tokens (P / C)</span>
                                <span className="font-bold text-slate-800">
                                  {m.tokens?.prompt_tokens ?? 0} / {m.tokens?.completion_tokens ?? 0}
                                </span>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              <div ref={messagesEndRef} />
            </div>

            {/* ── Chat Composer Toolbar ────────────────────────────── */}
            <div className="p-4 md:p-6 bg-[#F8FAFC]">
              <form
                onSubmit={handleFormSubmit}
                className="max-w-4xl mx-auto bg-white border border-slate-200 rounded-2xl shadow-xs transition-all focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100"
              >
                {/* Textarea */}
                <textarea
                  rows={2}
                  value={inputText}
                  disabled={sendingMessage}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleFormSubmit(e);
                    }
                  }}
                  placeholder="Ask anything about your documents..."
                  className="w-full px-4 pt-3.5 pb-2 text-xs md:text-sm text-slate-800 placeholder-slate-400 bg-transparent resize-none focus:outline-none"
                />

                {/* Bottom Toolbar inside Composer */}
                <div className="px-3 pb-3 flex items-center justify-between border-t border-slate-100 pt-2 gap-2">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {/* Attach Document */}
                    <Link
                      href="/documents"
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors border border-slate-200/80 cursor-pointer"
                    >
                      <Paperclip size={13} />
                      <span>Attach</span>
                    </Link>

                    {/* Web Search indicator */}
                    <button
                      type="button"
                      disabled
                      title="Knowledge Base search is active"
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-slate-400 bg-slate-50 border border-slate-200/80 rounded-lg cursor-not-allowed"
                    >
                      <Globe size={13} />
                      <span>Web Search</span>
                    </button>

                    {/* Deep Research Toggle */}
                    <button
                      type="button"
                      onClick={() => setDeepResearchActive(!deepResearchActive)}
                      className={`inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg transition-all border cursor-pointer ${
                        deepResearchActive
                          ? "bg-blue-50 border-blue-200 text-blue-600 font-semibold"
                          : "text-slate-600 hover:text-slate-900 hover:bg-slate-100 border-slate-200/80"
                      }`}
                      title="Toggle deeper multi-passage reranking"
                    >
                      <Sparkles size={13} className={deepResearchActive ? "text-blue-600" : ""} />
                      <span>Deep Research</span>
                    </button>
                  </div>

                  <div className="flex items-center gap-2">
                    {/* Gemini Model Selector Pill */}
                    <div className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-50 border border-slate-200/80 text-xs font-medium text-slate-700">
                      <Sparkles size={13} className="text-blue-600 shrink-0" />
                      <select
                        value={selectedModel}
                        onChange={(e) => setSelectedModel(e.target.value)}
                        className="bg-transparent text-xs font-semibold text-slate-700 focus:outline-none cursor-pointer pr-1"
                      >
                        {models.length > 0 ? (
                          models.map((m) => (
                            <option key={m.model_name} value={m.model_name}>
                              {m.model_name}
                            </option>
                          ))
                        ) : (
                          <option value="gemini-3.5-flash">Gemini 3.5 Flash</option>
                        )}
                      </select>
                    </div>

                    {/* Send Button */}
                    <button
                      type="submit"
                      disabled={!inputText.trim() || sendingMessage}
                      className="w-8 h-8 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white flex items-center justify-center transition-all shadow-xs cursor-pointer shrink-0"
                      title="Send message"
                    >
                      {sendingMessage ? (
                        <Loader2 size={15} className="animate-spin" />
                      ) : (
                        <Send size={14} />
                      )}
                    </button>
                  </div>
                </div>
              </form>
            </div>
          </main>

          {/* ── Right Context Panel ──────────────────────────────── */}
          <div className="hidden lg:block">
            <AppRightPanel
              citations={activeCitations}
              onSuggestedQuestionClick={(q) => executeSendMessage(q)}
              onQuickActionClick={(act) => executeSendMessage(act)}
              temperature={temperature}
              setTemperature={setTemperature}
              topK={topK}
              setTopK={setTopK}
              threshold={threshold}
              setThreshold={setThreshold}
              useReranker={useReranker}
              setUseReranker={setUseReranker}
              maxTokens={maxTokens}
              setMaxTokens={setMaxTokens}
              onScrollToCitation={handleScrollToCitation}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
