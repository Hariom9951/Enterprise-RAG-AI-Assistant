"use client";

/**
 * Login Page
 * ==========
 * Premium dark-mode login form using the existing design system.
 * Calls POST /api/v1/auth/login and stores the token pair on success.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { authApi, type ApiError } from "@/lib/api";
import { setTokens } from "@/lib/auth";

// =============================================================================
// Page Component
// =============================================================================

export default function LoginPage() {
  const router = useRouter();

  const [formData, setFormData] = useState({ email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({ ...prev, [e.target.name]: e.target.value }));
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const tokens = await authApi.login({
        email: formData.email,
        password: formData.password,
      });
      setTokens(tokens.access_token, tokens.refresh_token);
      router.push("/dashboard");
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      setError(
        apiErr?.error?.message ?? "Login failed. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-8 backdrop-blur-sm shadow-2xl shadow-black/50">
      {/* Header */}
      <div className="text-center mb-8">
        <h1 className="text-2xl font-bold text-white mb-2">Welcome back</h1>
        <p className="text-white/40 text-sm">
          Sign in to your Enterprise RAG account
        </p>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="mb-6 p-3 rounded-xl bg-red-500/10 border border-red-500/20 flex items-start gap-2">
          <span className="text-red-400 text-sm mt-0.5">⚠</span>
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-5" id="login-form">
        {/* Email */}
        <div className="space-y-1.5">
          <label
            htmlFor="login-email"
            className="block text-xs font-medium text-white/50 uppercase tracking-wider"
          >
            Email address
          </label>
          <input
            id="login-email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={formData.email}
            onChange={handleChange}
            placeholder="you@company.com"
            className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-white/20 text-sm
                       focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30
                       transition-all duration-200"
          />
        </div>

        {/* Password */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label
              htmlFor="login-password"
              className="block text-xs font-medium text-white/50 uppercase tracking-wider"
            >
              Password
            </label>
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>
          <input
            id="login-password"
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            required
            value={formData.password}
            onChange={handleChange}
            placeholder="••••••••"
            className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-white/20 text-sm
                       focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30
                       transition-all duration-200"
          />
        </div>

        {/* Submit */}
        <button
          id="login-submit-btn"
          type="submit"
          disabled={isLoading}
          className="w-full py-3 rounded-xl font-semibold text-sm text-white transition-all duration-200
                     hover:scale-[1.02] hover:shadow-lg hover:shadow-indigo-500/20 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
          style={{
            background: isLoading
              ? "rgba(99,102,241,0.5)"
              : "linear-gradient(135deg, #6366f1, #8b5cf6)",
          }}
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Signing in…
            </span>
          ) : (
            "Sign in →"
          )}
        </button>
      </form>

      {/* Divider */}
      <div className="flex items-center gap-3 my-6">
        <div className="flex-1 h-px bg-white/5" />
        <span className="text-white/20 text-xs">or</span>
        <div className="flex-1 h-px bg-white/5" />
      </div>

      {/* Register link */}
      <p className="text-center text-sm text-white/40">
        Don&apos;t have an account?{" "}
        <Link
          href="/register"
          id="link-to-register"
          className="text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
        >
          Create one →
        </Link>
      </p>

      {/* API hint */}
      <div className="mt-6 pt-5 border-t border-white/5">
        <p className="text-center text-[10px] text-white/20 font-mono">
          API: POST /api/v1/auth/login
        </p>
      </div>
    </div>
  );
}
