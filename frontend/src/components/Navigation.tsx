"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  UploadCloud,
  MessageSquare,
  Search,
  FlaskConical,
  Bot,
  Settings,
  LogOut,
  User as UserIcon,
  Shield,
  Menu,
  X
} from "lucide-react";
import { userApi, UserResponse } from "@/lib/api";
import { clearTokens } from "@/lib/auth";

export default function Navigation() {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const profile = await userApi.me();
        setUser(profile);
      } catch (err) {
        console.error("Failed to fetch user profile in navigation:", err);
      }
    };
    fetchUser();
  }, []);

  const handleLogout = () => {
    clearTokens();
    router.push("/login");
  };

  const navItems = [
    { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, desc: "System stats & activity history" },
    { href: "/documents", label: "Documents", icon: FileText, desc: "Manage ingested files" },
    { href: "/upload", label: "Upload Documents", icon: UploadCloud, desc: "Ingest new files" },
    { href: "/chat", label: "Chat Assistant", icon: MessageSquare, desc: "Grounded Q&A agent" },
    { href: "/search", label: "Semantic Search", icon: Search, desc: "Vector similarity search" },
    { href: "/playground", label: "RAG Playground", icon: FlaskConical, desc: "Test different models" },
    { href: "/agent", label: "AI Agent", icon: Bot, desc: "Autonomous agent execution" },
    { href: "/settings", label: "Settings", icon: Settings, desc: "Profile & configuration" },
  ];

  return (
    <>
      {/* Mobile Top Header */}
      <header className="md:hidden sticky top-0 z-40 w-full flex items-center justify-between px-6 py-4 bg-slate-950/80 border-b border-slate-800 backdrop-blur-md">
        <Link href="/" className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-sm font-bold shadow-lg shadow-indigo-500/30 text-white">
            R
          </div>
          <span className="font-bold bg-gradient-to-r from-indigo-400 via-sky-400 to-emerald-400 bg-clip-text text-transparent text-base">
            Enterprise RAG
          </span>
        </Link>
        <button
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          className="text-slate-400 hover:text-white p-1"
        >
          {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </header>

      {/* Mobile Menu Dropdown */}
      {isMobileMenuOpen && (
        <div className="md:hidden fixed inset-0 z-30 pt-16 bg-slate-950/95 backdrop-blur-lg flex flex-col justify-between p-6">
          <nav className="flex flex-col gap-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`flex items-center gap-3 px-4 py-3.5 rounded-xl border text-sm font-medium transition-all ${
                    isActive
                      ? "bg-indigo-500/10 border-indigo-500/30 text-indigo-300"
                      : "bg-transparent border-transparent text-slate-400 hover:bg-slate-900 hover:text-white"
                  }`}
                >
                  <Icon size={18} />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          <div className="border-t border-slate-800 pt-6 flex flex-col gap-4">
            {user && (
              <div className="flex items-center gap-3 px-2">
                <div className="w-10 h-10 rounded-full bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                  <UserIcon size={18} />
                </div>
                <div>
                  <div className="text-sm font-semibold text-white truncate max-w-[200px]">
                    {user.full_name}
                  </div>
                  <div className="text-xs text-slate-400 flex items-center gap-1">
                    <Shield size={10} className="text-indigo-400" />
                    <span>{user.role}</span>
                  </div>
                </div>
              </div>
            )}
            <button
              onClick={handleLogout}
              className="flex items-center justify-center gap-2 w-full py-3 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-red-400 hover:text-red-300 text-sm font-medium rounded-xl transition-all"
            >
              <LogOut size={16} />
              <span>Log out</span>
            </button>
          </div>
        </div>
      )}

      {/* Desktop Sidebar */}
      <aside className="hidden md:flex fixed top-0 bottom-0 left-0 w-64 border-r border-slate-800 bg-slate-950 flex-col justify-between p-6 z-30">
        <div className="flex flex-col gap-8">
          {/* Logo / Header */}
          <Link href="/" className="flex items-center gap-3 group">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-sm font-bold shadow-lg shadow-indigo-500/30 text-white group-hover:scale-105 transition-transform">
              R
            </div>
            <div>
              <span className="font-bold bg-gradient-to-r from-indigo-400 via-sky-400 to-emerald-400 bg-clip-text text-transparent text-md">
                Enterprise RAG
              </span>
              <span className="block text-[10px] text-slate-500 font-mono tracking-wider uppercase mt-0.5">
                AI Assistant
              </span>
            </div>
          </Link>

          {/* Navigation Links */}
          <nav className="flex flex-col gap-1.5">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  title={item.desc}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-sm font-semibold transition-all group ${
                    isActive
                      ? "bg-indigo-500/10 border-indigo-500/20 text-indigo-300"
                      : "bg-transparent border-transparent text-slate-400 hover:bg-slate-900 hover:text-white hover:border-slate-800"
                  }`}
                >
                  <Icon
                    size={16}
                    className={`transition-colors ${
                      isActive ? "text-indigo-400" : "text-slate-500 group-hover:text-white"
                    }`}
                  />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        {/* User Card & Logout */}
        <div className="flex flex-col gap-4 border-t border-slate-900 pt-6">
          {user && (
            <div className="flex items-center gap-3 px-2">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500/10 to-purple-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 shrink-0 shadow-inner">
                <UserIcon size={16} />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-bold text-white truncate" title={user.full_name}>
                  {user.full_name}
                </div>
                <div className="text-[10px] text-indigo-400 font-mono flex items-center gap-1 font-semibold uppercase mt-0.5">
                  <Shield size={10} />
                  <span>{user.role}</span>
                </div>
              </div>
            </div>
          )}
          <button
            onClick={handleLogout}
            className="flex items-center justify-center gap-2 w-full py-2.5 bg-red-950/20 hover:bg-red-950/40 border border-red-500/10 hover:border-red-500/30 text-red-400 hover:text-red-300 text-xs font-semibold rounded-xl transition-all"
          >
            <LogOut size={13} />
            <span>Log out</span>
          </button>
        </div>
      </aside>
    </>
  );
}
