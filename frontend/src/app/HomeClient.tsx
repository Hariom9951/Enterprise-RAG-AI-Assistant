"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  FileText,
  UploadCloud,
  MessageSquare,
  Search,
  FlaskConical,
  Cpu,
  Settings,
  LogOut,
  ArrowRight,
  Shield,
  Activity,
  CheckCircle
} from "lucide-react";
import { isAuthenticated, clearTokens } from "@/lib/auth";

// =============================================================================
// Feature Cards Data (Preserved)
// =============================================================================
const features = [
  {
    icon: "🧠",
    title: "Retrieval-Augmented Generation",
    description:
      "Ground every answer in your actual documents — no hallucinations, always cited.",
    phase: "Phase 4",
  },
  {
    icon: "📂",
    title: "Document Ingestion",
    description:
      "Upload PDF, DOCX, and TXT files. Automatic chunking, embedding, and indexing.",
    phase: "Phase 4",
  },
  {
    icon: "🔍",
    title: "Semantic Search",
    description:
      "Vector similarity search across your knowledge base with pgvector.",
    phase: "Phase 3",
  },
  {
    icon: "🔐",
    title: "Enterprise Security",
    description:
      "JWT authentication, role-based access control, and audit logging built in.",
    phase: "Phase 2",
  },
  {
    icon: "⚡",
    title: "High Performance",
    description:
      "Async FastAPI backend with Redis caching handles thousands of concurrent requests.",
    phase: "Phase 3",
  },
  {
    icon: "🐳",
    title: "Production Ready",
    description:
      "Docker, health checks, structured logging, and Nginx reverse proxy included.",
    phase: "Phase 1 ✅",
  },
];

// =============================================================================
// Tech Stack Badges (Preserved)
// =============================================================================
const techStack = [
  { name: "Python 3.12", color: "from-blue-500 to-cyan-500" },
  { name: "FastAPI", color: "from-green-500 to-teal-500" },
  { name: "Next.js 15", color: "from-slate-500 to-slate-300" },
  { name: "TypeScript", color: "from-blue-600 to-blue-400" },
  { name: "Tailwind CSS", color: "from-cyan-500 to-sky-500" },
  { name: "Docker", color: "from-blue-500 to-indigo-500" },
  { name: "PostgreSQL", color: "from-blue-700 to-blue-500" },
  { name: "pgvector", color: "from-purple-600 to-purple-400" },
];

export default function HomeClient() {
  const [authStatus, setAuthStatus] = useState<boolean>(false);
  const [healthStatus, setHealthStatus] = useState<"loading" | "healthy" | "offline">("loading");
  const [backendVersion, setBackendVersion] = useState<string>("");

  useEffect(() => {
    // Check initial auth state
    setAuthStatus(isAuthenticated());

    // Live Health Polling
    const checkHealth = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/v1/health");
        if (res.ok) {
          const data = await res.json();
          setHealthStatus("healthy");
          setBackendVersion(data.version || "0.2.0");
        } else {
          setHealthStatus("offline");
        }
      } catch (err) {
        setHealthStatus("offline");
      }
    };
    checkHealth();
  }, []);

  const handleLogout = () => {
    clearTokens();
    setAuthStatus(false);
  };

  // Quick Action List (Target URLs mapped to requested paths)
  const quickActions = [
    {
      title: "Documents",
      description: "Manage, browse, and verify uploaded documents.",
      path: "/documents",
      icon: FileText,
      color: "text-indigo-400 bg-indigo-500/10 border-indigo-500/20 group-hover:border-indigo-500/40"
    },
    {
      title: "Upload Documents",
      description: "Ingest new PDFs, text, or docx files.",
      path: "/documents",
      icon: UploadCloud,
      color: "text-sky-400 bg-sky-500/10 border-sky-500/20 group-hover:border-sky-500/40"
    },
    {
      title: "Chat Assistant",
      description: "Interactive conversation with cited answers.",
      path: "/chat",
      icon: MessageSquare,
      color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20 group-hover:border-emerald-500/40"
    },
    {
      title: "Semantic Search",
      description: "Search knowledge base via vector similarity.",
      path: "/search",
      icon: Search,
      color: "text-amber-400 bg-amber-500/10 border-amber-500/20 group-hover:border-amber-500/40"
    },
    {
      title: "RAG Playground",
      description: "Tweak LLM models, top-k filters and parameters.",
      path: "/playground",
      icon: FlaskConical,
      color: "text-purple-400 bg-purple-500/10 border-purple-500/20 group-hover:border-purple-500/40"
    },
    {
      title: "AI Agent",
      description: "Reasoning-capable agent with tool execution.",
      path: "/agent",
      icon: Cpu,
      color: "text-rose-400 bg-rose-500/10 border-rose-500/20 group-hover:border-rose-500/40"
    },
    {
      title: "Settings",
      description: "View credentials, limits, and configurations.",
      path: "/settings",
      icon: Settings,
      color: "text-slate-400 bg-slate-500/10 border-slate-500/20 group-hover:border-slate-500/40"
    }
  ];

  return (
    <main className="min-h-screen bg-[#030712] text-white overflow-x-hidden">
      
      {/* ── Animated Background Grid ──────────────────────────────────────── */}
      <div
        className="fixed inset-0 opacity-[0.03] pointer-events-none"
        style={{
          backgroundImage:
            "linear-gradient(#ffffff 1px, transparent 1px), linear-gradient(90deg, #ffffff 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
      />

      {/* ── Gradient Orbs ─────────────────────────────────────────────────── */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div
          className="absolute -top-40 -right-40 w-[600px] h-[600px] rounded-full opacity-20 blur-3xl animate-pulse"
          style={{ background: "radial-gradient(circle, #6366f1, transparent 70%)" }}
        />
        <div
          className="absolute -bottom-40 -left-40 w-[500px] h-[500px] rounded-full opacity-15 blur-3xl"
          style={{
            background: "radial-gradient(circle, #06b6d4, transparent 70%)",
            animationDuration: "4s",
          }}
        />
      </div>

      {/* ── Navigation ────────────────────────────────────────────────────── */}
      <nav className="relative z-10 flex items-center justify-between px-8 py-5 border-b border-white/5 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-sm font-bold shadow-lg shadow-indigo-500/30">
            R
          </div>
          <span className="font-semibold text-sm text-white/80 tracking-wide">
            Enterprise RAG
          </span>
        </div>
        <div className="flex items-center gap-6">
          {authStatus ? (
            <>
              <Link href="/dashboard" className="text-sm font-semibold text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1.5">
                Go to Workspace <ArrowRight size={14} />
              </Link>
              <button
                onClick={handleLogout}
                className="text-sm font-medium text-slate-400 hover:text-white transition-colors flex items-center gap-1"
              >
                <LogOut size={13} /> Sign Out
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="text-sm font-medium text-slate-400 hover:text-white transition-colors">
                Sign In
              </Link>
              <Link
                href="/login"
                className="px-4 py-1.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 transition-colors"
              >
                Get Started
              </Link>
            </>
          )}
        </div>
      </nav>

      {/* ── Hero Section ──────────────────────────────────────────────────── */}
      <section className="relative z-10 flex flex-col items-center text-center px-6 pt-24 pb-16">
        
        {/* Status Badge */}
        <div className="mb-8 inline-flex items-center gap-2 px-4 py-2 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs font-medium tracking-widest uppercase">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse inline-block" />
          Production Ready · Phase 1 Complete
        </div>

        {/* Main Heading */}
        <h1 className="text-5xl md:text-7xl font-extrabold mb-6 leading-tight tracking-tight">
          <span
            className="bg-clip-text text-transparent"
            style={{
              backgroundImage: "linear-gradient(135deg, #ffffff 0%, #a5b4fc 50%, #818cf8 100%)",
            }}
          >
            Enterprise RAG
          </span>
          <br />
          <span
            className="bg-clip-text text-transparent"
            style={{
              backgroundImage: "linear-gradient(135deg, #818cf8 0%, #06b6d4 100%)",
            }}
          >
            AI Assistant
          </span>
        </h1>

        {/* Sub-headline */}
        <p className="text-lg md:text-xl text-white/50 max-w-2xl mb-8 leading-relaxed">
          Ask questions against your company&apos;s knowledge base.
          Get grounded, cited answers powered by Retrieval-Augmented Generation.
        </p>

        {/* Live Backend Status Indicator */}
        <div className="mb-10 flex items-center gap-2.5 px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-xs md:text-sm shadow-inner">
          <span className={`w-2 h-2 rounded-full ${
            healthStatus === "loading" ? "bg-amber-400" : healthStatus === "healthy" ? "bg-emerald-400" : "bg-rose-500"
          } animate-pulse`} />
          <span className="text-white/60">
            {healthStatus === "loading" ? "Checking Backend Status..." : healthStatus === "healthy" ? "Backend Healthy & Connected" : "Backend Offline"}
          </span>
          {healthStatus === "healthy" && (
            <>
              <span className="text-white/20">·</span>
              <span className="text-indigo-400 font-mono">v{backendVersion}</span>
            </>
          )}
          <span className="text-white/25">·</span>
          <span className="text-white/40 font-mono">localhost:8000</span>
        </div>

        {/* Primary & Secondary CTA Buttons */}
        <div className="flex flex-wrap gap-4 justify-center">
          <Link
            href={authStatus ? "/dashboard" : "/login"}
            id="btn-workspace-cta"
            className="px-8 py-3.5 rounded-xl font-bold text-sm text-white transition-all duration-200 hover:scale-105 hover:shadow-lg hover:shadow-indigo-500/25 flex items-center gap-2 group"
            style={{
              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
            }}
          >
            Open Workspace <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
          </Link>
          
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            id="btn-api-docs"
            className="px-6 py-3.5 rounded-xl font-semibold text-sm text-white/80 border border-white/10 bg-white/5 hover:bg-white/10 hover:scale-105 transition-all duration-200"
          >
            Explore API Docs
          </a>
        </div>
      </section>

      {/* ── Quick Actions Grid Section ────────────────────────────────────── */}
      <section className="relative z-10 px-8 pb-20 max-w-6xl mx-auto">
        <div className="text-center md:text-left mb-8 border-b border-white/5 pb-4">
          <h2 className="text-xl font-bold text-white/95 tracking-wide">Quick Action Workspace</h2>
          <p className="text-white/40 text-xs md:text-sm mt-1">Jump directly into any module in the Enterprise RAG toolkit.</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {quickActions.map((action) => {
            const IconComponent = action.icon;
            return (
              <Link
                key={action.title}
                href={authStatus ? action.path : "/login"}
                className="group p-5 rounded-2xl bg-white/[0.02] border border-white/5 backdrop-blur-sm hover:bg-white/[0.05] hover:border-indigo-500/20 transition-all duration-300 hover:-translate-y-1 flex flex-col justify-between"
              >
                <div>
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center border mb-4 transition-colors ${action.color}`}>
                    <IconComponent size={20} />
                  </div>
                  <h3 className="font-semibold text-white/90 text-sm mb-1.5 flex items-center gap-1 group-hover:text-indigo-400 transition-colors">
                    {action.title}
                  </h3>
                  <p className="text-white/40 text-xs leading-relaxed">
                    {action.description}
                  </p>
                </div>
                <div className="mt-4 flex items-center text-[10px] font-semibold tracking-wider text-white/30 group-hover:text-indigo-400 uppercase gap-1 self-start transition-colors">
                  Launch <ArrowRight size={10} className="group-hover:translate-x-0.5 transition-transform" />
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      {/* ── Stats Row (Preserved) ─────────────────────────────────────────── */}
      <section className="relative z-10 px-6 pb-20">
        <div className="max-w-4xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { value: "< 50ms", label: "API Response" },
            { value: "99.9%", label: "Uptime Target" },
            { value: "v1", label: "API Version" },
            { value: "MIT", label: "License" },
          ].map((stat) => (
            <div
              key={stat.label}
              className="p-4 rounded-2xl bg-white/[0.03] border border-white/5 text-center backdrop-blur-sm hover:bg-white/[0.06] transition-colors"
            >
              <div className="text-2xl font-bold text-white mb-1">{stat.value}</div>
              <div className="text-xs text-white/40 uppercase tracking-wider">{stat.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Feature Cards (Preserved) ─────────────────────────────────────── */}
      <section className="relative z-10 px-6 pb-24">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-2xl font-bold text-center text-white/80 mb-2">
            Built for Production
          </h2>
          <p className="text-center text-white/40 text-sm mb-12">
            Every feature engineered to enterprise standards from day one.
          </p>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="group p-6 rounded-2xl bg-white/[0.03] border border-white/5 backdrop-blur-sm hover:bg-white/[0.06] hover:border-indigo-500/20 transition-all duration-300 hover:-translate-y-1"
              >
                <div className="flex items-start justify-between mb-4">
                  <span className="text-3xl">{feature.icon}</span>
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                    {feature.phase}
                  </span>
                </div>
                <h3 className="font-semibold text-white/90 mb-2 text-base">
                  {feature.title}
                </h3>
                <p className="text-white/40 text-sm leading-relaxed">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Tech Stack (Preserved) ────────────────────────────────────────── */}
      <section className="relative z-10 px-6 pb-24">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-center text-sm font-medium text-white/30 uppercase tracking-widest mb-8">
            Technology Stack
          </h2>
          <div className="flex flex-wrap gap-3 justify-center">
            {techStack.map((tech) => (
              <div
                key={tech.name}
                className="group relative px-4 py-2 rounded-xl bg-white/[0.04] border border-white/5 hover:border-white/15 transition-all duration-200 cursor-default hover:scale-105"
              >
                <span className="text-sm font-medium text-white/70 group-hover:text-white/90 transition-colors">
                  {tech.name}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Architecture Preview (Preserved) ──────────────────────────────── */}
      <section className="relative z-10 px-6 pb-24">
        <div className="max-w-4xl mx-auto">
          <div className="p-8 rounded-3xl bg-white/[0.02] border border-white/5 backdrop-blur-sm">
            <h2 className="text-lg font-semibold text-white/80 mb-6 flex items-center gap-2">
              <span className="w-6 h-6 rounded-md bg-indigo-500/20 text-indigo-400 flex items-center justify-center text-xs">▤</span>
              Phase 1 Architecture
            </h2>
            <div className="font-mono text-xs text-white/40 leading-relaxed space-y-1">
              <div>
                <span className="text-indigo-400">Browser</span>
                <span className="text-white/20"> ──HTTP──▶ </span>
                <span className="text-cyan-400">Next.js :3000</span>
                <span className="text-white/20"> ──API──▶ </span>
                <span className="text-green-400">FastAPI :8000</span>
              </div>
              <div className="pl-4 text-white/20">
                └─ GET /api/v1/&nbsp;&nbsp;&nbsp;&nbsp;→ 200 &#123;&quot;message&quot;: &quot;...&quot;&#125;
              </div>
              <div className="pl-4 text-white/20">
                └─ GET /api/v1/health → 200 &#123;&quot;status&quot;: &quot;healthy&quot;&#125;
              </div>
              <div className="pl-4 text-white/20">
                └─ GET /docs &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;→ Swagger UI
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Footer (Preserved) ────────────────────────────────────────────── */}
      <footer className="relative z-10 border-t border-white/5 px-8 py-8">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-xs font-bold">
              R
            </div>
            <span className="text-white/30 text-sm">
              Enterprise RAG AI Assistant
            </span>
          </div>
          <div className="text-white/20 text-xs">
            Phase 1 Complete · v0.1.0 · MIT License
          </div>
          <div className="flex gap-6">
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-white/30 hover:text-white/60 text-xs transition-colors"
            >
              API Docs
            </a>
            <a
              href="http://localhost:8000/api/v1/health"
              target="_blank"
              rel="noopener noreferrer"
              className="text-white/30 hover:text-white/60 text-xs transition-colors"
            >
              Health
            </a>
            <a
              href="/docs"
              className="text-white/30 hover:text-white/60 text-xs transition-colors"
            >
              Docs
            </a>
          </div>
        </div>
      </footer>

    </main>
  );
}
