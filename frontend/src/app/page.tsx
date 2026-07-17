/**
 * Enterprise RAG AI Assistant — Homepage
 *
 * A premium, dark-mode landing page showcasing the assistant's capabilities.
 * Uses Tailwind CSS for styling with glassmorphism cards, animated gradients,
 * and smooth micro-animations.
 *
 * Phase 1: Static content with placeholder backend status indicator.
 * Phase 2: Replace placeholder with real /api/v1/health polling.
 */

import type { Metadata } from "next";

// =============================================================================
// Metadata
// =============================================================================
export const metadata: Metadata = {
  title: "Home",
  description:
    "Enterprise RAG AI Assistant — upload documents and get instant, grounded AI answers.",
};

// =============================================================================
// Feature Cards Data
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
// Tech Stack Badges
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

// =============================================================================
// Page Component
// =============================================================================
export default function HomePage() {
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
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] rounded-full opacity-10 blur-3xl"
          style={{ background: "radial-gradient(ellipse, #8b5cf6, transparent 60%)" }}
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
        <div className="flex items-center gap-2">
          <span className="px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse inline-block" />
            v0.1.0 Phase 1
          </span>
        </div>
      </nav>

      {/* ── Hero Section ──────────────────────────────────────────────────── */}
      <section className="relative z-10 flex flex-col items-center text-center px-6 pt-28 pb-20">

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
        <p className="text-lg md:text-xl text-white/50 max-w-2xl mb-4 leading-relaxed">
          Ask questions against your company&apos;s knowledge base.
          Get grounded, cited answers powered by Retrieval-Augmented Generation.
        </p>

        {/* Backend Status Indicator */}
        <div className="mt-4 flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-sm">
          <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
          <span className="text-white/60">Backend Connected</span>
          <span className="text-white/30">·</span>
          <span className="text-white/40 font-mono text-xs">localhost:8000</span>
          <span className="ml-2 px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-400 text-xs font-medium border border-amber-500/20">
            placeholder
          </span>
        </div>

        {/* CTA Buttons */}
        <div className="flex flex-wrap gap-4 mt-10 justify-center">
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            id="btn-api-docs"
            className="px-6 py-3 rounded-xl font-semibold text-sm text-white transition-all duration-200 hover:scale-105 hover:shadow-lg hover:shadow-indigo-500/25"
            style={{
              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
            }}
          >
            Explore API Docs →
          </a>
          <a
            href="http://localhost:8000/api/v1/health"
            target="_blank"
            rel="noopener noreferrer"
            id="btn-health-check"
            className="px-6 py-3 rounded-xl font-semibold text-sm text-white/80 border border-white/10 bg-white/5 hover:bg-white/10 hover:scale-105 transition-all duration-200"
          >
            Health Check
          </a>
        </div>
      </section>

      {/* ── Stats Row ─────────────────────────────────────────────────────── */}
      <section className="relative z-10 px-6 pb-16">
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

      {/* ── Feature Cards ─────────────────────────────────────────────────── */}
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

      {/* ── Tech Stack ────────────────────────────────────────────────────── */}
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

      {/* ── Architecture Preview ──────────────────────────────────────────── */}
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

      {/* ── Footer ────────────────────────────────────────────────────────── */}
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
