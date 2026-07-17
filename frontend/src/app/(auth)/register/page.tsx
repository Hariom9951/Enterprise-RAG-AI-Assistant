"use client";

/**
 * Register Page
 * =============
 * Premium dark-mode registration form using the existing design system.
 * Calls POST /api/v1/auth/register, then redirects to /login on success.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { authApi, type ApiError } from "@/lib/api";

// Password requirement rules for inline UI feedback
const PASSWORD_RULES = [
  { label: "At least 8 characters", test: (p: string) => p.length >= 8 },
  { label: "One uppercase letter", test: (p: string) => /[A-Z]/.test(p) },
  { label: "One lowercase letter", test: (p: string) => /[a-z]/.test(p) },
  { label: "One digit", test: (p: string) => /\d/.test(p) },
  { label: "One special character (@$!%*?&_-#^)", test: (p: string) => /[@$!%*?&_\-#^]/.test(p) },
];

// =============================================================================
// Page Component
// =============================================================================

export default function RegisterPage() {
  const router = useRouter();

  const [formData, setFormData] = useState({
    full_name: "",
    email: "",
    password: "",
    confirm_password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [passwordFocused, setPasswordFocused] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({ ...prev, [e.target.name]: e.target.value }));
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (formData.password !== formData.confirm_password) {
      setError("Passwords do not match.");
      return;
    }

    const unmetRules = PASSWORD_RULES.filter((r) => !r.test(formData.password));
    if (unmetRules.length > 0) {
      setError(`Password requirements not met: ${unmetRules.map((r) => r.label).join(", ")}.`);
      return;
    }

    setIsLoading(true);

    try {
      await authApi.register({
        full_name: formData.full_name,
        email: formData.email,
        password: formData.password,
      });
      setSuccess(true);
      setTimeout(() => router.push("/login"), 2000);
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      setError(
        apiErr?.error?.message ?? "Registration failed. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  // ==========================================================================
  // Success State
  // ==========================================================================
  if (success) {
    return (
      <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-8 backdrop-blur-sm shadow-2xl text-center">
        <div className="w-14 h-14 rounded-full bg-emerald-500/15 border border-emerald-500/20 flex items-center justify-center text-2xl mx-auto mb-4">
          ✓
        </div>
        <h2 className="text-xl font-bold text-white mb-2">Account created!</h2>
        <p className="text-white/40 text-sm mb-4">
          Redirecting you to login…
        </p>
        <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full"
            style={{ animation: "progress 2s linear forwards" }}
          />
        </div>
        <style>{`@keyframes progress { from { width: 0% } to { width: 100% } }`}</style>
      </div>
    );
  }

  // ==========================================================================
  // Registration Form
  // ==========================================================================
  return (
    <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-8 backdrop-blur-sm shadow-2xl shadow-black/50">
      {/* Header */}
      <div className="text-center mb-8">
        <h1 className="text-2xl font-bold text-white mb-2">Create account</h1>
        <p className="text-white/40 text-sm">
          Join Enterprise RAG AI Assistant
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
      <form onSubmit={handleSubmit} className="space-y-5" id="register-form">
        {/* Full Name */}
        <div className="space-y-1.5">
          <label htmlFor="reg-full-name" className="block text-xs font-medium text-white/50 uppercase tracking-wider">
            Full name
          </label>
          <input
            id="reg-full-name"
            name="full_name"
            type="text"
            autoComplete="name"
            required
            minLength={2}
            value={formData.full_name}
            onChange={handleChange}
            placeholder="Jane Doe"
            className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-white/20 text-sm
                       focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30 transition-all duration-200"
          />
        </div>

        {/* Email */}
        <div className="space-y-1.5">
          <label htmlFor="reg-email" className="block text-xs font-medium text-white/50 uppercase tracking-wider">
            Email address
          </label>
          <input
            id="reg-email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={formData.email}
            onChange={handleChange}
            placeholder="you@company.com"
            className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-white/20 text-sm
                       focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30 transition-all duration-200"
          />
        </div>

        {/* Password */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label htmlFor="reg-password" className="block text-xs font-medium text-white/50 uppercase tracking-wider">
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
            id="reg-password"
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            required
            value={formData.password}
            onChange={handleChange}
            onFocus={() => setPasswordFocused(true)}
            onBlur={() => setPasswordFocused(false)}
            placeholder="••••••••"
            className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-white/20 text-sm
                       focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30 transition-all duration-200"
          />

          {/* Password strength indicator */}
          {(passwordFocused || formData.password.length > 0) && (
            <div className="mt-2 p-3 rounded-xl bg-white/[0.02] border border-white/5 space-y-1.5">
              {PASSWORD_RULES.map((rule) => {
                const met = rule.test(formData.password);
                return (
                  <div key={rule.label} className="flex items-center gap-2">
                    <span className={`text-xs ${met ? "text-emerald-400" : "text-white/20"}`}>
                      {met ? "✓" : "○"}
                    </span>
                    <span className={`text-xs ${met ? "text-emerald-400" : "text-white/30"}`}>
                      {rule.label}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Confirm Password */}
        <div className="space-y-1.5">
          <label htmlFor="reg-confirm-password" className="block text-xs font-medium text-white/50 uppercase tracking-wider">
            Confirm password
          </label>
          <input
            id="reg-confirm-password"
            name="confirm_password"
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            required
            value={formData.confirm_password}
            onChange={handleChange}
            placeholder="••••••••"
            className={`w-full px-4 py-3 rounded-xl bg-white/5 border text-white placeholder-white/20 text-sm
                        focus:outline-none focus:ring-1 transition-all duration-200
                        ${
                          formData.confirm_password && formData.password !== formData.confirm_password
                            ? "border-red-500/40 focus:border-red-500/60 focus:ring-red-500/20"
                            : "border-white/10 focus:border-indigo-500/60 focus:ring-indigo-500/30"
                        }`}
          />
          {formData.confirm_password && formData.password !== formData.confirm_password && (
            <p className="text-xs text-red-400">Passwords do not match.</p>
          )}
        </div>

        {/* Submit */}
        <button
          id="register-submit-btn"
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
              Creating account…
            </span>
          ) : (
            "Create account →"
          )}
        </button>
      </form>

      {/* Divider */}
      <div className="flex items-center gap-3 my-6">
        <div className="flex-1 h-px bg-white/5" />
        <span className="text-white/20 text-xs">or</span>
        <div className="flex-1 h-px bg-white/5" />
      </div>

      {/* Login link */}
      <p className="text-center text-sm text-white/40">
        Already have an account?{" "}
        <Link
          href="/login"
          id="link-to-login"
          className="text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
        >
          Sign in →
        </Link>
      </p>

      {/* API hint */}
      <div className="mt-6 pt-5 border-t border-white/5">
        <p className="text-center text-[10px] text-white/20 font-mono">
          API: POST /api/v1/auth/register
        </p>
      </div>
    </div>
  );
}
