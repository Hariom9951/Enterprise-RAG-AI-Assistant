"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Brain,
  Plus,
  Search,
  X,
  Edit2,
  Trash2,
  Loader2,
  AlertCircle,
  CheckCircle,
  Info,
  RefreshCw,
  UserCheck,
  Filter,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import {
  memoryApi,
  UserMemoryItem,
  MemoryType,
  getApiErrorMessage,
} from "@/lib/api";

const MEMORY_TYPE_CONFIG: Record<
  MemoryType,
  { label: string; badgeClass: string; description: string }
> = {
  preference: {
    label: "Preference",
    badgeClass: "bg-purple-50 text-purple-700 border-purple-200/80",
    description: "Personal formatting, tone, or tool preferences (e.g., 'Prefer concise bullet points').",
  },
  fact: {
    label: "Fact",
    badgeClass: "bg-blue-50 text-blue-700 border-blue-200/80",
    description: "Static information about your role, domain, or environment.",
  },
  goal: {
    label: "Goal",
    badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200/80",
    description: "Ongoing project objectives or personal milestones.",
  },
  context: {
    label: "Context",
    badgeClass: "bg-amber-50 text-amber-700 border-amber-200/80",
    description: "Background details about your team or work structure.",
  },
};

export default function MemoryManager() {
  const [memories, setMemories] = useState<UserMemoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Filters, Search & Pagination
  const [selectedType, setSelectedType] = useState<MemoryType | "all">("all");
  const [searchInput, setSearchInput] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(10);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);

  // Active request ID reference to discard out-of-order / stale network responses
  const activeRequestIdRef = useRef<number>(0);

  // Create Modal
  const [isCreateOpen, setIsCreateOpen] = useState<boolean>(false);
  const [createContent, setCreateContent] = useState<string>("");
  const [createType, setCreateType] = useState<MemoryType>("preference");
  const [createSubmitting, setCreateSubmitting] = useState<boolean>(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Edit Modal
  const [editingMemory, setEditingMemory] = useState<UserMemoryItem | null>(null);
  const [editContent, setEditContent] = useState<string>("");
  const [editType, setEditType] = useState<MemoryType>("preference");
  const [editSubmitting, setEditSubmitting] = useState<boolean>(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Delete Confirmation Modal
  const [deletingMemory, setDeletingMemory] = useState<UserMemoryItem | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState<boolean>(false);

  // Debounce search input by 300ms to update searchQuery and reset page
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearchQuery(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Load memories
  const loadMemories = useCallback(async () => {
    setLoading(true);
    setError(null);
    const reqId = ++activeRequestIdRef.current;

    try {
      const trimmedSearch = searchQuery.trim();
      if (trimmedSearch) {
        setIsSearching(true);
        const res = await memoryApi.search(trimmedSearch, 5);
        if (reqId !== activeRequestIdRef.current) return; // Stale response discarded
        setMemories(res.items);
        setTotalCount(res.items.length);
        setTotalPages(1);
      } else {
        setIsSearching(false);
        const res = await memoryApi.list({
          memory_type: selectedType === "all" ? undefined : selectedType,
          page,
          page_size: pageSize,
        });
        if (reqId !== activeRequestIdRef.current) return; // Stale response discarded
        setMemories(res.items);
        setTotalCount(res.total);
        setTotalPages(Math.max(1, res.pages));
      }
    } catch (err) {
      if (reqId !== activeRequestIdRef.current) return;
      setError(getApiErrorMessage(err, "Failed to load memories. Please try again."));
    } finally {
      if (reqId === activeRequestIdRef.current) {
        setLoading(false);
      }
    }
  }, [searchQuery, selectedType, page, pageSize]);

  useEffect(() => {
    loadMemories();
  }, [loadMemories]);

  const showToast = (type: "success" | "error", text: string) => {
    setToastMessage({ type, text });
    setTimeout(() => {
      setToastMessage(null);
    }, 4000);
  };

  const handleTypeSelect = (type: MemoryType | "all") => {
    setSelectedType(type);
    setPage(1);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSearchQuery(searchInput);
    setPage(1);
  };

  const handleClearSearch = () => {
    setSearchInput("");
    setSearchQuery("");
    setPage(1);
  };

  // Create Memory Handler
  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const content = createContent.trim();
    if (!content) {
      setCreateError("Please enter memory content.");
      return;
    }
    setCreateSubmitting(true);
    setCreateError(null);
    try {
      await memoryApi.create({
        content,
        memory_type: createType,
      });
      setIsCreateOpen(false);
      setCreateContent("");
      setCreateType("preference");
      showToast("success", "Memory saved successfully.");
      if (page === 1) {
        loadMemories();
      } else {
        setPage(1);
      }
    } catch (err) {
      setCreateError(getApiErrorMessage(err, "Failed to save memory."));
    } finally {
      setCreateSubmitting(false);
    }
  };

  // Open Edit Modal
  const openEditModal = (mem: UserMemoryItem) => {
    setEditingMemory(mem);
    setEditContent(mem.content);
    setEditType(mem.memory_type);
    setEditError(null);
  };

  // Edit Memory Handler
  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingMemory) return;
    const content = editContent.trim();
    if (!content) {
      setEditError("Memory content cannot be empty.");
      return;
    }
    setEditSubmitting(true);
    setEditError(null);
    try {
      await memoryApi.update(editingMemory.id, {
        content,
        memory_type: editType,
      });
      setEditingMemory(null);
      showToast("success", "Memory updated successfully.");
      loadMemories();
    } catch (err) {
      setEditError(getApiErrorMessage(err, "Failed to update memory."));
    } finally {
      setEditSubmitting(false);
    }
  };

  // Delete Memory Handler
  const handleDeleteConfirm = async () => {
    if (!deletingMemory) return;
    setDeleteSubmitting(true);
    try {
      await memoryApi.delete(deletingMemory.id);
      setDeletingMemory(null);
      showToast("success", "Memory deleted.");
      if (memories.length === 1 && page > 1) {
        setPage((p) => p - 1);
      } else {
        loadMemories();
      }
    } catch (err) {
      showToast("error", getApiErrorMessage(err, "Failed to delete memory."));
    } finally {
      setDeleteSubmitting(false);
    }
  };

  const formatProvenance = (prov: string) => {
    if (prov === "user_explicit") return "You saved this";
    if (prov === "agent_extracted") return "Extracted by Agent";
    return "System";
  };

  // Filter search results on client if a category filter is active during search
  const displayedMemories =
    isSearching && selectedType !== "all"
      ? memories.filter((m) => m.memory_type === selectedType)
      : memories;

  return (
    <div className="space-y-6">
      {/* ── Toast Alert ─────────────────────────────────────────────── */}
      {toastMessage && (
        <div
          className={`p-3.5 rounded-xl border flex items-center gap-2.5 text-xs font-semibold shadow-xs animate-fade-in ${
            toastMessage.type === "success"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-red-50 border-red-200 text-red-800"
          }`}
        >
          {toastMessage.type === "success" ? (
            <CheckCircle size={16} className="text-emerald-600 shrink-0" />
          ) : (
            <AlertCircle size={16} className="text-red-600 shrink-0" />
          )}
          <span>{toastMessage.text}</span>
        </div>
      )}

      {/* ── Context & Grounding Notice Banner ────────────────────────── */}
      <div className="p-4 bg-gradient-to-r from-purple-50/70 via-blue-50/40 to-slate-50 border border-purple-200/70 rounded-2xl flex items-start gap-3 shadow-2xs">
        <div className="w-8 h-8 rounded-lg bg-purple-100 text-purple-700 flex items-center justify-center shrink-0 mt-0.5">
          <Brain size={18} />
        </div>
        <div className="flex-1 min-w-0 text-xs">
          <div className="flex items-center gap-2">
            <h3 className="font-bold text-slate-900 text-sm">Personal Knowledge & Preferences</h3>
            <span className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded-full text-[10px] font-bold">
              Active Grounding
            </span>
          </div>
          <p className="text-slate-600 mt-1 leading-relaxed">
            Persistent memories provide personal reference context across sessions. When you ask questions, relevant memories are retrieved and supplied to the assistant to tailor answers to your preferred tools, goals, and style.
          </p>
          <div className="mt-2 pt-2 border-t border-purple-200/50 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500 font-medium">
            <span className="flex items-center gap-1">
              <Info size={12} className="text-purple-600" />
              Treated strictly as passive reference data, never as system instructions.
            </span>
            <span>•</span>
            <span>The system does not record raw conversation transcripts.</span>
          </div>
        </div>
      </div>

      {/* ── Action Toolbar: Search, Filters, Add Button ───────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pt-1">
        {/* Search Bar */}
        <form onSubmit={handleSearchSubmit} className="relative flex-1 max-w-md">
          <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search memories by keyword..."
            maxLength={200}
            className="w-full pl-9 pr-8 py-2 bg-white border border-slate-200 rounded-xl text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all shadow-2xs"
          />
          {searchInput && (
            <button
              type="button"
              onClick={handleClearSearch}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-0.5"
            >
              <X size={14} />
            </button>
          )}
        </form>

        <div className="flex items-center gap-2 shrink-0">
          {/* Refresh Button */}
          <button
            type="button"
            onClick={loadMemories}
            disabled={loading}
            className="p-2 text-slate-500 hover:text-slate-800 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors shadow-2xs disabled:opacity-50"
            title="Refresh memory list"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>

          {/* Add Memory Button */}
          <button
            type="button"
            onClick={() => setIsCreateOpen(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold transition-all shadow-xs hover:shadow-sm"
          >
            <Plus size={15} />
            <span>Add Memory</span>
          </button>
        </div>
      </div>

      {/* ── Type Filter Pills ────────────────────────────────────────── */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
        <span className="text-xs text-slate-400 font-semibold flex items-center gap-1 mr-1 shrink-0">
          <Filter size={12} />
          Filter:
        </span>
        <button
          type="button"
          onClick={() => handleTypeSelect("all")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer shrink-0 ${
            selectedType === "all"
              ? "bg-slate-900 text-white shadow-2xs"
              : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
          }`}
        >
          All Types
        </button>
        {(Object.keys(MEMORY_TYPE_CONFIG) as MemoryType[]).map((type) => {
          const cfg = MEMORY_TYPE_CONFIG[type];
          const isSelected = selectedType === type;
          return (
            <button
              key={type}
              type="button"
              onClick={() => handleTypeSelect(type)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer shrink-0 ${
                isSelected
                  ? "bg-slate-900 text-white shadow-2xs"
                  : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
              }`}
            >
              {cfg.label}
            </button>
          );
        })}
      </div>

      {/* ── Search Active Notice ─────────────────────────────────────── */}
      {isSearching && (
        <div className="flex items-center justify-between px-3.5 py-2 bg-blue-50/70 border border-blue-200/80 rounded-xl text-xs text-blue-800">
          <span>
            Keyword search results for <strong>&ldquo;{searchQuery}&rdquo;</strong> ({memories.length} found, max 5).
          </span>
          <button
            type="button"
            onClick={handleClearSearch}
            className="text-blue-700 hover:text-blue-900 font-semibold underline text-[11px]"
          >
            Clear Search
          </button>
        </div>
      )}

      {/* ── Error State ──────────────────────────────────────────────── */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl flex items-center justify-between text-xs text-red-800">
          <div className="flex items-center gap-2">
            <AlertCircle size={16} className="text-red-600 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={loadMemories}
            className="px-2.5 py-1 bg-red-100 hover:bg-red-200 text-red-800 font-semibold rounded-lg text-[11px] transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* ── Loading State ────────────────────────────────────────────── */}
      {loading ? (
        <div className="py-20 flex flex-col items-center justify-center text-slate-400 gap-2.5">
          <Loader2 className="animate-spin text-blue-600" size={24} />
          <span className="text-xs font-medium">Retrieving persistent memories…</span>
        </div>
      ) : displayedMemories.length === 0 ? (
        /* ── Empty State ── */
        <div className="p-10 bg-white border border-slate-200 rounded-2xl text-center space-y-3 shadow-2xs">
          <div className="w-12 h-12 rounded-2xl bg-purple-50 text-purple-600 border border-purple-100 flex items-center justify-center mx-auto">
            <Brain size={24} />
          </div>
          <div>
            <h4 className="text-sm font-bold text-slate-800">No stored memories found</h4>
            <p className="text-xs text-slate-500 max-w-md mx-auto mt-1 leading-relaxed">
              {isSearching
                ? "No memories matched your keyword query. Try different terms or clear the search."
                : selectedType !== "all"
                ? `You have not saved any memories in the '${MEMORY_TYPE_CONFIG[selectedType]?.label}' category yet.`
                : "You have not saved any memories yet. Add your preferences, facts, or goals to inform future answers."}
            </p>
          </div>
          {!isSearching && (
            <button
              type="button"
              onClick={() => setIsCreateOpen(true)}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold transition-all shadow-xs"
            >
              <Plus size={14} />
              <span>Save Your First Memory</span>
            </button>
          )}
        </div>
      ) : (
        /* ── Memory Cards Grid ── */
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-slate-500 px-1">
            <span>
              {isSearching
                ? `Showing ${displayedMemories.length} result${displayedMemories.length === 1 ? "" : "s"}`
                : `Showing ${(page - 1) * pageSize + 1} to ${Math.min(page * pageSize, totalCount)} of ${totalCount} memories`}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3">
            {displayedMemories.map((mem) => {
              const cfg = MEMORY_TYPE_CONFIG[mem.memory_type] || {
                label: mem.memory_type,
                badgeClass: "bg-slate-50 text-slate-700 border-slate-200",
              };
              return (
                <div
                  key={mem.id}
                  className="p-4 bg-white border border-slate-200/90 rounded-2xl hover:border-slate-300 transition-all shadow-2xs group flex flex-col justify-between"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      {/* Type Badge */}
                      <span
                        className={`px-2 py-0.5 rounded-md text-[10px] font-bold border ${cfg.badgeClass}`}
                      >
                        {cfg.label}
                      </span>

                      {/* Provenance Tag */}
                      <span className="inline-flex items-center gap-1 text-[11px] text-slate-500 font-medium">
                        <UserCheck size={12} className="text-slate-400" />
                        {formatProvenance(mem.provenance)}
                      </span>

                      {/* Date */}
                      <span className="text-[11px] text-slate-400">
                        {new Date(mem.created_at).toLocaleDateString(undefined, {
                          year: "numeric",
                          month: "short",
                          day: "numeric",
                        })}
                      </span>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0 opacity-80 group-hover:opacity-100 transition-opacity">
                      <button
                        type="button"
                        onClick={() => openEditModal(mem)}
                        className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors cursor-pointer"
                        title="Edit memory"
                      >
                        <Edit2 size={13} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeletingMemory(mem)}
                        className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors cursor-pointer"
                        title="Delete memory"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>

                  {/* Content */}
                  <div className="mt-2.5 text-xs text-slate-800 leading-relaxed font-normal whitespace-pre-wrap">
                    {mem.content}
                  </div>
                </div>
              );
            })}
          </div>

          {/* ── Pagination Controls ────────────────────────────────────── */}
          {!isSearching && totalPages > 1 && (
            <div className="flex items-center justify-between pt-3 border-t border-slate-200/80 text-xs text-slate-600">
              <span className="text-[11px] text-slate-500 font-medium">
                Page {page} of {totalPages} ({totalCount} total)
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1 || loading}
                  className="inline-flex items-center gap-1 px-3 py-1.5 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed font-medium shadow-2xs"
                >
                  <ChevronLeft size={13} />
                  <span>Previous</span>
                </button>
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages || loading}
                  className="inline-flex items-center gap-1 px-3 py-1.5 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed font-medium shadow-2xs"
                >
                  <span>Next</span>
                  <ChevronRight size={13} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── CREATE MEMORY MODAL ─────────────────────────────────────── */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs animate-fade-in">
          <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-lg p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <Brain size={17} className="text-purple-600" />
                Add Persistent Memory
              </h3>
              <button
                type="button"
                onClick={() => setIsCreateOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X size={16} />
              </button>
            </div>

            {createError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-800 flex items-start gap-2">
                <AlertCircle size={15} className="text-red-600 shrink-0 mt-0.5" />
                <span>{createError}</span>
              </div>
            )}

            <form onSubmit={handleCreateSubmit} className="space-y-4">
              {/* Type Select */}
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">
                  Memory Category
                </label>
                <select
                  value={createType}
                  onChange={(e) => setCreateType(e.target.value as MemoryType)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all"
                >
                  {(Object.keys(MEMORY_TYPE_CONFIG) as MemoryType[]).map((t) => (
                    <option key={t} value={t}>
                      {MEMORY_TYPE_CONFIG[t].label} — {MEMORY_TYPE_CONFIG[t].description}
                    </option>
                  ))}
                </select>
              </div>

              {/* Content Textarea */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-bold text-slate-700">
                    Memory Content
                  </label>
                  <span className="text-[11px] text-slate-400">
                    {createContent.length} / 2,000 characters
                  </span>
                </div>
                <textarea
                  rows={4}
                  value={createContent}
                  onChange={(e) => setCreateContent(e.target.value)}
                  placeholder="e.g., I prefer summaries formatted with concise bullet points and bold action items."
                  maxLength={2000}
                  className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all resize-y"
                  required
                />
                <p className="text-[11px] text-slate-500 mt-1">
                  Do not store API credentials, secrets, or raw conversation transcripts.
                </p>
              </div>

              {/* Modal Buttons */}
              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  disabled={createSubmitting}
                  className="px-3.5 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createSubmitting || !createContent.trim()}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold transition-all disabled:opacity-50 cursor-pointer"
                >
                  {createSubmitting && <Loader2 size={13} className="animate-spin" />}
                  <span>{createSubmitting ? "Saving..." : "Save Memory"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── EDIT MEMORY MODAL ───────────────────────────────────────── */}
      {editingMemory && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs animate-fade-in">
          <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-lg p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <Edit2 size={16} className="text-blue-600" />
                Edit Stored Memory
              </h3>
              <button
                type="button"
                onClick={() => setEditingMemory(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X size={16} />
              </button>
            </div>

            {editError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-800 flex items-start gap-2">
                <AlertCircle size={15} className="text-red-600 shrink-0 mt-0.5" />
                <span>{editError}</span>
              </div>
            )}

            <form onSubmit={handleEditSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">
                  Category
                </label>
                <select
                  value={editType}
                  onChange={(e) => setEditType(e.target.value as MemoryType)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all"
                >
                  {(Object.keys(MEMORY_TYPE_CONFIG) as MemoryType[]).map((t) => (
                    <option key={t} value={t}>
                      {MEMORY_TYPE_CONFIG[t].label} — {MEMORY_TYPE_CONFIG[t].description}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-bold text-slate-700">
                    Content
                  </label>
                  <span className="text-[11px] text-slate-400">
                    {editContent.length} / 2,000 characters
                  </span>
                </div>
                <textarea
                  rows={4}
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  maxLength={2000}
                  className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all resize-y"
                  required
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setEditingMemory(null)}
                  disabled={editSubmitting}
                  className="px-3.5 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editSubmitting || !editContent.trim()}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold transition-all disabled:opacity-50 cursor-pointer"
                >
                  {editSubmitting && <Loader2 size={13} className="animate-spin" />}
                  <span>{editSubmitting ? "Updating..." : "Update Memory"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── DELETE CONFIRMATION MODAL ───────────────────────────────── */}
      {deletingMemory && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs animate-fade-in">
          <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-md p-6 shadow-xl space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-red-100 text-red-600 flex items-center justify-center shrink-0">
                <Trash2 size={20} />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900">Delete Memory?</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  This will remove the memory from your active assistant context.
                </p>
              </div>
            </div>

            <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span
                  className={`px-2 py-0.5 rounded-md text-[10px] font-bold border ${
                    MEMORY_TYPE_CONFIG[deletingMemory.memory_type]?.badgeClass ||
                    "bg-slate-100 text-slate-700"
                  }`}
                >
                  {MEMORY_TYPE_CONFIG[deletingMemory.memory_type]?.label || deletingMemory.memory_type}
                </span>
                <span className="text-[10px] text-slate-400 font-mono">
                  ID: {deletingMemory.id.slice(0, 8)}...
                </span>
              </div>
              <div className="text-xs text-slate-700 max-h-32 overflow-y-auto italic whitespace-pre-wrap">
                &ldquo;{deletingMemory.content}&rdquo;
              </div>
            </div>

            <p className="text-[11px] text-slate-500">
              Future AI responses will no longer retrieve this reference item. This operation is safe and can be undone only by adding the memory again.
            </p>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setDeletingMemory(null)}
                disabled={deleteSubmitting}
                className="px-3.5 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteConfirm}
                disabled={deleteSubmitting}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl text-xs font-semibold transition-all disabled:opacity-50 cursor-pointer"
              >
                {deleteSubmitting && <Loader2 size={13} className="animate-spin" />}
                <span>{deleteSubmitting ? "Deleting..." : "Delete Memory"}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
