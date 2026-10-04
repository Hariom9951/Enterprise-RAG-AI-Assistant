"use client";

import React, { useState, useEffect } from "react";
import {
  Search,
  Sun,
  Moon,
  Bell,
  ChevronDown,
  User as UserIcon,
  LogOut,
  Settings,
  Shield,
  Menu
} from "lucide-react";
import { userApi, UserResponse } from "@/lib/api";
import { clearTokens } from "@/lib/auth";
import { useRouter } from "next/navigation";

interface AppTopbarProps {
  onToggleMobileSidebar?: () => void;
  onSearchClick?: () => void;
  onSearchSubmit?: (query: string) => void;
}

export default function AppTopbar({
  onToggleMobileSidebar,
  onSearchClick,
  onSearchSubmit
}: AppTopbarProps) {
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    let isMounted = true;
    userApi
      .me()
      .then((profile) => {
        if (isMounted) setUser(profile);
      })
      .catch(() => {
        // Unauthenticated or offline fallback
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const handleLogout = () => {
    clearTokens();
    router.push("/login");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && searchQuery.trim()) {
      if (onSearchSubmit) {
        onSearchSubmit(searchQuery.trim());
      } else {
        router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
      }
    }
  };

  // User initials
  const initials = user?.full_name
    ? user.full_name
        .split(" ")
        .map((n) => n[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "HY";

  const displayName = user?.full_name || "Hariom Yadav";

  return (
    <header className="sticky top-0 z-20 h-14 bg-white border-b border-slate-200/80 px-4 md:px-6 flex items-center justify-between shadow-xs">
      {/* ── Left Side: Mobile Menu Button & Search Bar ────────────── */}
      <div className="flex items-center gap-3 flex-1 max-w-xl">
        {onToggleMobileSidebar && (
          <button
            onClick={onToggleMobileSidebar}
            className="md:hidden p-1.5 text-slate-500 hover:text-slate-900 rounded-lg hover:bg-slate-100 transition-colors"
            aria-label="Open Navigation"
          >
            <Menu size={20} />
          </button>
        )}

        <div
          onClick={onSearchClick}
          className="relative w-full flex items-center bg-slate-50 hover:bg-slate-100/80 border border-slate-200 rounded-xl px-3 py-1.5 transition-all text-slate-500 focus-within:bg-white focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100"
        >
          <Search size={16} className="text-slate-400 shrink-0 mr-2.5" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search your documents, ask anything..."
            className="w-full bg-transparent text-xs md:text-sm text-slate-800 placeholder-slate-400 focus:outline-none"
          />
          <div className="hidden sm:flex items-center gap-1 shrink-0 ml-2">
            <kbd className="px-1.5 py-0.5 text-[10px] font-mono font-medium text-slate-500 bg-white border border-slate-200 rounded shadow-2xs">
              Ctrl K
            </kbd>
          </div>
        </div>
      </div>

      {/* ── Right Side Controls ─────────────────────────────────── */}
      <div className="flex items-center gap-2 md:gap-3 ml-4">
        {/* Theme Toggle Button */}
        <button
          onClick={() => setIsDark(!isDark)}
          className="p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer"
          title="Toggle Theme"
          aria-label="Toggle Theme"
        >
          {isDark ? <Moon size={18} /> : <Sun size={18} />}
        </button>

        {/* Notifications Bell */}
        <button
          className="relative p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer"
          title="Notifications"
          aria-label="Notifications"
        >
          <Bell size={18} />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-blue-600 ring-2 ring-white" />
        </button>

        {/* User Profile Dropdown */}
        <div className="relative">
          <button
            onClick={() => setProfileDropdownOpen(!profileDropdownOpen)}
            className="flex items-center gap-2 pl-1.5 pr-2 py-1 rounded-full hover:bg-slate-100 border border-transparent hover:border-slate-200 transition-all cursor-pointer"
          >
            <div className="w-8 h-8 rounded-full bg-[#10B981] text-white text-xs font-bold flex items-center justify-center shadow-xs">
              {initials}
            </div>
            <span className="hidden sm:inline-block text-xs font-semibold text-slate-800">
              {displayName}
            </span>
            <ChevronDown size={14} className="text-slate-400" />
          </button>

          {profileDropdownOpen && (
            <>
              <div
                className="fixed inset-0 z-30"
                onClick={() => setProfileDropdownOpen(false)}
              />
              <div className="absolute right-0 mt-2 w-56 bg-white border border-slate-200 rounded-xl shadow-lg p-1.5 z-40 text-xs">
                <div className="px-3 py-2 border-b border-slate-100">
                  <p className="font-semibold text-slate-900 truncate">
                    {displayName}
                  </p>
                  <p className="text-[11px] text-slate-500 truncate">
                    {user?.email || "user@enterprise.ai"}
                  </p>
                  <div className="mt-1 flex items-center gap-1 text-[10px] font-mono uppercase text-blue-600 font-bold">
                    <Shield size={10} />
                    <span>{user?.role || "USER"}</span>
                  </div>
                </div>

                <div className="py-1">
                  <button
                    onClick={() => {
                      setProfileDropdownOpen(false);
                      router.push("/settings");
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-slate-700 hover:bg-slate-50 rounded-lg font-medium transition-colors"
                  >
                    <Settings size={14} className="text-slate-400" />
                    <span>Account Settings</span>
                  </button>
                  <button
                    onClick={() => {
                      setProfileDropdownOpen(false);
                      router.push("/dashboard");
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-slate-700 hover:bg-slate-50 rounded-lg font-medium transition-colors"
                  >
                    <UserIcon size={14} className="text-slate-400" />
                    <span>Usage & Statistics</span>
                  </button>
                </div>

                <div className="pt-1 border-t border-slate-100">
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-red-600 hover:bg-red-50 rounded-lg font-medium transition-colors"
                  >
                    <LogOut size={14} />
                    <span>Sign Out</span>
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
