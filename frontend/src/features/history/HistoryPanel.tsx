import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Filter,
  History as HistoryIcon,
  Play,
  RefreshCw,
  Search,
} from "lucide-react";
import { api } from "../../api/client";
import { Badge } from "../../components/Badge";
import type { QueryHistoryItem } from "../../types";

interface HistoryPanelProps {
  onSelectSql: (sql: string) => void;
}

type StatusFilter = "all" | "success" | "rejected" | "error" | "timeout" | "clarification";

export const HistoryPanel: React.FC<HistoryPanelProps> = ({ onSelectSql }) => {
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["queryHistory"],
    queryFn: () => api.getQueryHistory(50, 0),
    refetchInterval: 15000,
  });

  const items = data?.items || [];

  const filteredItems = items.filter((item) => {
    // Status filter
    if (filter !== "all" && item.status.toLowerCase() !== filter) {
      return false;
    }
    // Search filter
    if (search.trim()) {
      const term = search.toLowerCase();
      const sqlMatch = item.sql_text.toLowerCase().includes(term);
      const questionMatch = item.question?.toLowerCase().includes(term);
      return sqlMatch || questionMatch;
    }
    return true;
  });

  const getStatusVariant = (status: string) => {
    switch (status.toLowerCase()) {
      case "success":
        return "success";
      case "rejected":
        return "warning";
      case "error":
        return "error";
      case "timeout":
        return "error";
      case "clarification":
        return "info";
      default:
        return "neutral";
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-950 p-4 text-slate-100 overflow-hidden select-text">
      {/* Top Toolbar */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800 flex-wrap gap-2 flex-shrink-0">
        <div className="flex items-center gap-2">
          <HistoryIcon className="w-4 h-4 text-indigo-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Query Audit Ledger
          </span>
          <span className="text-[11px] text-slate-500 font-mono">
            ({filteredItems.length} of {data?.total || 0})
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2 pointer-events-none" />
            <input
              type="text"
              placeholder="Search history..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-slate-900 border border-slate-800 rounded pl-8 pr-2 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors w-44"
            />
          </div>

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-1.5 text-slate-400 hover:text-slate-100 rounded hover:bg-slate-800 transition-colors disabled:opacity-50"
            title="Refresh history"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin text-indigo-400" : ""}`} />
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1.5 pb-2 mb-2 border-b border-slate-800/60 overflow-x-auto flex-shrink-0">
        {(["all", "success", "rejected", "error", "timeout", "clarification"] as StatusFilter[]).map(
          (st) => (
            <button
              key={st}
              onClick={() => setFilter(st)}
              className={`px-2.5 py-1 rounded text-xs font-medium capitalize transition-colors ${
                filter === st
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
              }`}
            >
              {st}
            </button>
          )
        )}
      </div>

      {/* History Items List */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center p-12 text-slate-500 space-y-2">
            <div className="w-5 h-5 border-2 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin" />
            <p className="text-xs">Loading audit ledger...</p>
          </div>
        ) : isError ? (
          <div className="p-3 text-xs text-rose-300 bg-rose-950/40 rounded border border-rose-900">
            Failed to load query history.
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 text-slate-500 space-y-1">
            <Filter className="w-6 h-6 text-slate-600" />
            <p className="text-xs">No query history matching filter criteria.</p>
          </div>
        ) : (
          filteredItems.map((item: QueryHistoryItem) => (
            <div
              key={item.id}
              className="p-3 bg-slate-900/60 hover:bg-slate-900 border border-slate-800/80 rounded-lg transition-colors space-y-2 text-xs"
            >
              {/* Row Header */}
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <Badge variant={getStatusVariant(item.status)} size="sm" className="uppercase text-[9px]">
                    {item.status}
                  </Badge>
                  <span className="text-[11px] text-slate-500 font-mono">
                    source: <strong className="text-slate-300">{item.source}</strong>
                  </span>
                  {item.duration_ms !== null && item.duration_ms !== undefined && (
                    <span className="text-[11px] text-slate-500 font-mono border-l border-slate-800 pl-2">
                      {item.duration_ms.toFixed(1)} ms
                    </span>
                  )}
                  {item.row_count !== null && item.row_count !== undefined && (
                    <span className="text-[11px] text-slate-500 font-mono border-l border-slate-800 pl-2">
                      {item.row_count} rows
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-500 font-mono">
                    {new Date(item.created_at).toLocaleTimeString()}
                  </span>
                  <button
                    onClick={() => onSelectSql(item.sql_text)}
                    className="inline-flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 px-2 py-0.5 rounded hover:bg-slate-800 transition-colors"
                    title="Load SQL into editor"
                  >
                    <Play className="w-3 h-3 fill-current" />
                    <span>Load to Editor</span>
                  </button>
                </div>
              </div>

              {/* Natural Language Question (if ask/agent) */}
              {item.question && (
                <p className="text-slate-400 text-[11px] italic">
                  "{item.question}"
                </p>
              )}

              {/* SQL Code Block */}
              <pre className="p-2 bg-slate-950 rounded border border-slate-800/80 font-mono text-[11px] text-slate-300 overflow-x-auto whitespace-pre-wrap">
                {item.sql_text}
              </pre>

              {/* Error Message if rejected/error */}
              {item.error_message && (
                <div className="text-[11px] text-rose-400 bg-rose-950/40 p-1.5 rounded border border-rose-900/60 font-mono">
                  {item.error_message}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
