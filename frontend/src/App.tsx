import React, { useState } from "react";
import {
  QueryClient,
  QueryClientProvider,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Bot,
  Code2,
  FileSpreadsheet,
  History as HistoryIcon,
  Sparkles,
} from "lucide-react";

import { api, ApiClientError } from "./api/client";
import { Header } from "./components/Header";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { SchemaBrowser } from "./features/schema/SchemaBrowser";
import { SqlEditor } from "./features/editor/SqlEditor";
import { AskPanel } from "./features/ask/AskPanel";
import { ResultsTable } from "./features/results/ResultsTable";
import { OptimizerPanel } from "./features/plan/OptimizerPanel";
import { HistoryPanel } from "./features/history/HistoryPanel";

import type {
  AppWorkspaceMode,
  BottomTab,
  ExecuteQueryResponse,
} from "./types";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const DEFAULT_SQL = `-- QueryPilot Interactive SQL Workspace
-- Try querying users, products, orders, or order_items:
SELECT 
  id, 
  user_id, 
  status, 
  total_amount, 
  created_at 
FROM orders 
WHERE created_at >= '2026-01-01' 
ORDER BY created_at DESC 
LIMIT 25;`;

const AppContent: React.FC = () => {
  const qc = useQueryClient();

  // Top Workspace Mode
  const [workspaceMode, setWorkspaceMode] = useState<AppWorkspaceMode>("ask");
  // Bottom Tab
  const [bottomTab, setBottomTab] = useState<BottomTab>("results");

  // SQL Editor State
  const [editorSql, setEditorSql] = useState(DEFAULT_SQL);
  const [isExecutingSql, setIsExecutingSql] = useState(false);
  const [executionError, setExecutionError] = useState<string | null>(null);

  // Results State
  const [queryResults, setQueryResults] = useState<ExecuteQueryResponse | null>(null);

  // Execute SQL from Editor
  const handleExecuteSql = async (sqlToRun = editorSql) => {
    const trimmed = sqlToRun.trim();
    if (!trimmed || isExecutingSql) return;

    setIsExecutingSql(true);
    setExecutionError(null);

    try {
      const res = await api.executeQuery({ sql: trimmed, source: "manual" });
      setQueryResults(res);
      setBottomTab("results");
      // Auto-refresh query history ledger
      qc.invalidateQueries({ queryKey: ["queryHistory"] });
    } catch (err) {
      if (err instanceof ApiClientError) {
        setExecutionError(err.userMessage);
      } else if (err instanceof Error) {
        setExecutionError(err.message);
      } else {
        setExecutionError("Failed to execute SQL query.");
      }
      setBottomTab("results");
    } finally {
      setIsExecutingSql(false);
    }
  };

  // Click-to-insert text from Schema Browser
  const handleInsertSchemaText = (text: string) => {
    setEditorSql((prev) => {
      if (!prev.trim()) return text;
      return `${prev} ${text}`;
    });
  };

  // Handle results received from AskPanel
  const handleResultsReceived = (res: ExecuteQueryResponse) => {
    setQueryResults(res);
    setExecutionError(null);
    setBottomTab("results");
    qc.invalidateQueries({ queryKey: ["queryHistory"] });
  };

  // Open SQL from Ask or History into the Editor
  const handleOpenInEditor = (sql: string) => {
    setEditorSql(sql);
    setWorkspaceMode("editor");
  };

  // Send query to optimizer tab
  const handleSendToOptimizer = () => {
    setBottomTab("plan");
  };

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-100 font-sans overflow-hidden">
      {/* Top Header */}
      <Header />

      {/* Main Container: Sidebar + Workspace Split */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar: Schema Browser */}
        <ErrorBoundary fallbackTitle="Schema Browser Error">
          <SchemaBrowser onInsertText={handleInsertSchemaText} />
        </ErrorBoundary>

        {/* Center Workspace & Bottom Panels */}
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden bg-slate-950">
          {/* Workspace Tabs: "Ask AI" vs "SQL Editor" */}
          <div className="h-10 border-b border-slate-800 bg-slate-900/80 px-4 flex items-center justify-between flex-shrink-0">
            <div className="flex items-center space-x-1">
              <button
                onClick={() => setWorkspaceMode("ask")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  workspaceMode === "ask"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                }`}
              >
                <Bot className="w-3.5 h-3.5" />
                <span>Ask AI</span>
              </button>

              <button
                onClick={() => setWorkspaceMode("editor")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  workspaceMode === "editor"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                }`}
              >
                <Code2 className="w-3.5 h-3.5" />
                <span>SQL Editor</span>
              </button>
            </div>

            <div className="text-[11px] text-slate-500 font-mono hidden md:block">
              sample_shop database (read-only)
            </div>
          </div>

          {/* Top Panel Surface (Dynamic based on workspaceMode) */}
          <div className="h-1/2 min-h-[220px] flex flex-col overflow-hidden border-b border-slate-800">
            <ErrorBoundary fallbackTitle="Workspace Panel Error">
              {workspaceMode === "ask" ? (
                <AskPanel
                  onExecuteSql={handleOpenInEditor}
                  onResultsReceived={handleResultsReceived}
                />
              ) : (
                <SqlEditor
                  value={editorSql}
                  onChange={setEditorSql}
                  onExecute={() => handleExecuteSql()}
                  onOptimize={handleSendToOptimizer}
                  isExecuting={isExecutingSql}
                />
              )}
            </ErrorBoundary>
          </div>

          {/* Bottom Panel Surface: Tabs (Results | Plan & Optimization | History) */}
          <div className="flex-1 flex flex-col min-h-0 bg-slate-950">
            {/* Bottom Panel Tabs */}
            <div className="h-10 border-b border-slate-800 bg-slate-900/60 px-4 flex items-center justify-between flex-shrink-0">
              <div className="flex items-center space-x-1">
                <button
                  onClick={() => setBottomTab("results")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    bottomTab === "results"
                      ? "bg-slate-800 text-slate-100 border border-slate-700 shadow-sm"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <FileSpreadsheet className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Results</span>
                  {queryResults && (
                    <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-700 text-slate-300 font-mono ml-0.5">
                      {queryResults.row_count}
                    </span>
                  )}
                </button>

                <button
                  onClick={() => setBottomTab("plan")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    bottomTab === "plan"
                      ? "bg-slate-800 text-slate-100 border border-slate-700 shadow-sm"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Plan & Optimization</span>
                </button>

                <button
                  onClick={() => setBottomTab("history")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    bottomTab === "history"
                      ? "bg-slate-800 text-slate-100 border border-slate-700 shadow-sm"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <HistoryIcon className="w-3.5 h-3.5 text-amber-400" />
                  <span>History</span>
                </button>
              </div>

              {bottomTab === "results" && executionError && (
                <div className="text-xs text-rose-400 truncate max-w-md font-mono">
                  {executionError}
                </div>
              )}
            </div>

            {/* Bottom Tab Content */}
            <div className="flex-1 overflow-hidden">
              <ErrorBoundary fallbackTitle="Inspector Panel Error">
                {bottomTab === "results" && (
                  executionError ? (
                    <div className="p-6 text-xs text-rose-300 bg-rose-950/20 m-4 rounded-lg border border-rose-900/60 font-mono space-y-2">
                      <div className="font-bold text-rose-400 text-sm">Execution Error:</div>
                      <p>{executionError}</p>
                    </div>
                  ) : (
                    <ResultsTable
                      columns={queryResults?.columns || []}
                      rows={queryResults?.rows || []}
                      rowCount={queryResults?.row_count}
                      durationMs={queryResults?.duration_ms}
                      truncated={queryResults?.truncated}
                      limitInjected={queryResults?.limit_injected}
                      isLoading={isExecutingSql}
                      emptyMessage="Run a SQL query or ask a question to see tabular results here."
                    />
                  )
                )}

                {bottomTab === "plan" && (
                  <OptimizerPanel sql={editorSql} />
                )}

                {bottomTab === "history" && (
                  <HistoryPanel onSelectSql={handleOpenInEditor} />
                )}
              </ErrorBoundary>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
};

export default App;
