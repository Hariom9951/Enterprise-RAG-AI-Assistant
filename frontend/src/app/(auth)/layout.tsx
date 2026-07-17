/**
 * Auth Route Group Layout
 * =======================
 * Shared layout for /login and /register pages.
 * Centers the auth card on a dark gradient background
 * that matches the Phase 1 design system.
 */

import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: {
    template: "%s | Enterprise RAG AI Assistant",
    default: "Auth",
  },
};

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-[#030712] flex flex-col items-center justify-center px-4 relative overflow-hidden">
      {/* Ambient gradient orbs — matches homepage design */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div
          className="absolute -top-40 -right-40 w-[500px] h-[500px] rounded-full opacity-15 blur-3xl"
          style={{ background: "radial-gradient(circle, #6366f1, transparent 70%)" }}
        />
        <div
          className="absolute -bottom-40 -left-40 w-[400px] h-[400px] rounded-full opacity-10 blur-3xl"
          style={{ background: "radial-gradient(circle, #06b6d4, transparent 70%)" }}
        />
      </div>

      {/* Background grid */}
      <div
        className="fixed inset-0 opacity-[0.025] pointer-events-none"
        style={{
          backgroundImage:
            "linear-gradient(#ffffff 1px, transparent 1px), linear-gradient(90deg, #ffffff 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
      />

      {/* Logo */}
      <Link href="/" className="relative z-10 flex items-center gap-2 mb-8 group">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-sm font-bold shadow-lg shadow-indigo-500/30 group-hover:scale-110 transition-transform">
          R
        </div>
        <span className="text-white/60 text-sm font-medium group-hover:text-white/80 transition-colors">
          Enterprise RAG
        </span>
      </Link>

      {/* Auth card */}
      <div className="relative z-10 w-full max-w-md">
        {children}
      </div>

      {/* Footer */}
      <p className="relative z-10 mt-8 text-white/20 text-xs">
        © 2025 Enterprise RAG AI Assistant · Phase 2
      </p>
    </div>
  );
}
