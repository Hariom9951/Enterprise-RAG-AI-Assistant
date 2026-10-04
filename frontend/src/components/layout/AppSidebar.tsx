"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Search,
  FileText,
  Bot,
  History,
  BarChart3,
  Settings,
  Plus,
  ChevronDown,
  ChevronRight,
  LogOut,
  X
} from "lucide-react";
import { userApi, dashboardApi, UserResponse, DashboardData } from "@/lib/api";
import { clearTokens } from "@/lib/auth";

interface AppSidebarProps {
  onNewChat?: () => void;
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export default function AppSidebar({
  onNewChat,
  isMobileOpen = false,
  onCloseMobile
}: AppSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [dashboardStats, setDashboardStats] = useState<DashboardData | null>(null);
  const [workspacesOpen, setWorkspacesOpen] = useState(true);
  const [activeWorkspace, setActiveWorkspace] = useState("general");

  useEffect(() => {
    let isMounted = true;
    userApi
      .me()
      .then((profile) => {
        if (isMounted) setUser(profile);
      })
      .catch(() => {});

    dashboardApi
      .getStatistics()
      .then((stats) => {
        if (isMounted) setDashboardStats(stats);
      })
      .catch(() => {});

    return () => {
      isMounted = false;
    };
  }, []);

  const handleLogout = () => {
    clearTokens();
    router.push("/login");
  };

  // Explicit route matching for high visual accuracy
  const navLinks = [
    {
      id: "search",
      href: "/search",
      label: "Search",
      icon: Search,
      isActive: pathname === "/search" || pathname.startsWith("/search/"),
    },
    {
      id: "documents",
      href: "/documents",
      label: "Documents",
      icon: FileText,
      isActive: pathname === "/documents" || pathname.startsWith("/documents/"),
    },
    {
      id: "agents",
      href: "/agent",
      label: "Agents",
      icon: Bot,
      isActive: pathname === "/agent" || pathname.startsWith("/agent/"),
    },
    {
      id: "chat",
      href: "/chat",
      label: "Chat History",
      icon: History,
      isActive: pathname === "/chat" || pathname.startsWith("/chat/"),
    },
    {
      id: "analytics",
      href: "/dashboard",
      label: "Analytics",
      icon: BarChart3,
      isActive: pathname === "/dashboard" || pathname.startsWith("/dashboard/"),
    },
    {
      id: "settings",
      href: "/settings",
      label: "Settings",
      icon: Settings,
      isActive: pathname === "/settings" || pathname.startsWith("/settings/"),
    },
  ];

  const workspaces = [
    { id: "general", name: "General", initial: "G", color: "bg-blue-600 text-white" },
    { id: "product", name: "Product", initial: "P", color: "bg-purple-600 text-white" },
    { id: "research", name: "Research", initial: "R", color: "bg-orange-600 text-white" },
    { id: "team", name: "Team", initial: "T", color: "bg-violet-600 text-white" },
  ];

  // Real queries served from backend
  const queriesServed = dashboardStats?.todays_queries ?? 0;
  const queriesLimit = 5000;
  const usagePercentage = Math.min(
    Math.round((queriesServed / queriesLimit) * 100),
    100
  );

  const sidebarContent = (
    <div className="flex flex-col h-full bg-[#0B132B] text-slate-200 select-none">
      {/* ── Brand Header ────────────────────────────────────────── */}
      <div className="px-5 pt-5 pb-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-3 group">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center text-white shadow-md shadow-blue-500/20 group-hover:scale-105 transition-transform">
            <svg
              className="w-5 h-5 text-white"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
              <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
              <line x1="12" y1="22.08" x2="12" y2="12" />
            </svg>
          </div>
          <div>
            <span className="font-bold text-white text-base tracking-tight block">
              Aegis RAG
            </span>
            <span className="text-[11px] text-slate-400 font-medium block">
              Enterprise AI Assistant
            </span>
          </div>
        </Link>
        {onCloseMobile && (
          <button
            onClick={onCloseMobile}
            className="md:hidden text-slate-400 hover:text-white p-1"
          >
            <X size={20} />
          </button>
        )}
      </div>

      {/* ── New Chat CTA Button ──────────────────────────────────── */}
      <div className="px-4 py-2">
        <button
          onClick={() => {
            if (onNewChat) {
              onNewChat();
            } else {
              router.push("/chat");
            }
            if (onCloseMobile) onCloseMobile();
          }}
          className={`w-full flex items-center gap-2.5 px-4 py-2.5 rounded-xl font-medium text-sm shadow-sm transition-all duration-150 cursor-pointer ${
            pathname === "/chat"
              ? "bg-blue-600 hover:bg-blue-500 text-white ring-2 ring-blue-400/40"
              : "bg-blue-600 hover:bg-blue-500 text-white"
          }`}
        >
          <Plus size={18} strokeWidth={2.5} />
          <span>New Chat</span>
        </button>
      </div>

      {/* ── Primary Navigation ──────────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto px-3 py-2 space-y-0.5 scrollbar-thin">
        {navLinks.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.id}
              href={item.href}
              onClick={() => onCloseMobile && onCloseMobile()}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                item.isActive
                  ? "bg-[#1E293B] text-white font-semibold shadow-2xs border-l-2 border-blue-500"
                  : "text-slate-300 hover:bg-[#15203B] hover:text-white"
              }`}
            >
              <Icon
                size={18}
                className={item.isActive ? "text-blue-400" : "text-slate-400"}
              />
              <span>{item.label}</span>
            </Link>
          );
        })}

        {/* ── Workspaces Collapsible Section ────────────────────── */}
        <div className="pt-4">
          <button
            onClick={() => setWorkspacesOpen(!workspacesOpen)}
            className="w-full flex items-center justify-between px-3 py-1.5 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors"
          >
            <span>Workspaces</span>
            {workspacesOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>

          {workspacesOpen && (
            <div className="mt-1 space-y-0.5">
              {workspaces.map((ws) => {
                const isWsActive = activeWorkspace === ws.id;
                return (
                  <button
                    key={ws.id}
                    onClick={() => setActiveWorkspace(ws.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-medium transition-all ${
                      isWsActive
                        ? "bg-[#1E293B] text-white"
                        : "text-slate-300 hover:bg-[#15203B] hover:text-white"
                    }`}
                  >
                    <span
                      className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${ws.color}`}
                    >
                      {ws.initial}
                    </span>
                    <span className="truncate">{ws.name}</span>
                  </button>
                );
              })}

              <button
                type="button"
                className="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-xs text-slate-400 hover:text-white hover:bg-[#15203B] transition-colors"
              >
                <Plus size={14} />
                <span>Create Workspace</span>
              </button>
            </div>
          )}
        </div>
      </nav>

      {/* ── Bottom Usage Widget (Real Data) ─────────────────────── */}
      <div className="p-3 border-t border-slate-800/80">
        <div className="bg-[#121B35] border border-slate-800 rounded-xl p-3">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-semibold text-white">Usage</span>
            <span className="px-1.5 py-0.5 text-[9px] font-bold tracking-wider uppercase bg-blue-600 text-white rounded">
              Pro
            </span>
          </div>
          <div className="text-[11px] text-slate-300 font-medium mb-2">
            {queriesServed.toLocaleString()} / {queriesLimit.toLocaleString()} queries
          </div>
          {/* Real progress bar */}
          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-blue-500 h-full rounded-full transition-all duration-300"
              style={{ width: `${Math.max(usagePercentage, 2)}%` }}
            />
          </div>
          <div className="mt-2 text-[10px] text-slate-400">
            Resets in 28 days
          </div>
        </div>

        {/* User Account / Logout row */}
        {user && (
          <div className="mt-3 pt-2 border-t border-slate-800/60 flex items-center justify-between px-1">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-7 h-7 rounded-full bg-emerald-600 text-white text-[11px] font-bold flex items-center justify-center shrink-0">
                {user.full_name
                  ? user.full_name
                      .split(" ")
                      .map((n) => n[0])
                      .slice(0, 2)
                      .join("")
                      .toUpperCase()
                  : "U"}
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium text-white truncate">
                  {user.full_name}
                </p>
                <p className="text-[10px] text-slate-400 uppercase tracking-wider font-mono">
                  {user.role}
                </p>
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="text-slate-400 hover:text-red-400 p-1 rounded-lg transition-colors cursor-pointer"
              title="Sign Out"
            >
              <LogOut size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Sidebar (Fixed Left) */}
      <aside className="hidden md:block fixed top-0 bottom-0 left-0 w-64 border-r border-slate-800/60 z-30">
        {sidebarContent}
      </aside>

      {/* Mobile Drawer */}
      {isMobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div
            className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm"
            onClick={onCloseMobile}
          />
          <div className="relative w-72 max-w-[85vw] h-full shadow-2xl z-10">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
}
