"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Brain, Settings as SettingsIcon } from "lucide-react";
import AppSidebar from "@/components/layout/AppSidebar";
import AppTopbar from "@/components/layout/AppTopbar";
import MemoryManager from "@/components/memory/MemoryManager";

export default function SettingsMemoryPage() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState<boolean>(false);

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
                <Brain className="text-purple-600" size={24} />
                Persistent Memories
              </h1>
              <p className="text-xs md:text-sm text-slate-500 mt-1">
                Manage personal knowledge, user preferences, and goals that ground your AI assistant across sessions.
              </p>
            </div>

            {/* Navigation Tabs */}
            <div className="flex items-center gap-2 border-b border-slate-200">
              <Link
                href="/settings"
                className="px-4 py-2.5 text-xs font-semibold text-slate-500 hover:text-slate-900 border-b-2 border-transparent transition-colors flex items-center gap-1.5"
              >
                <SettingsIcon size={14} />
                <span>System Settings</span>
              </Link>
              <Link
                href="/settings/memory"
                className="px-4 py-2.5 text-xs font-semibold text-purple-700 border-b-2 border-purple-600 transition-colors flex items-center gap-1.5"
              >
                <Brain size={14} />
                <span>Persistent Memories</span>
              </Link>
            </div>

            {/* Memory Manager Main Content */}
            <MemoryManager />
          </div>
        </main>
      </div>
    </div>
  );
}
