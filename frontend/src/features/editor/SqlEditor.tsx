import React, { lazy, Suspense } from "react";
import { Play, Sparkles, Trash2 } from "lucide-react";

// Lazy-load Monaco Editor for optimal bundle performance
const MonacoEditor = lazy(() => import("@monaco-editor/react"));

interface SqlEditorProps {
  value: string;
  onChange: (value: string) => void;
  onExecute: () => void;
  onOptimize: () => void;
  isExecuting?: boolean;
}

export const SqlEditor: React.FC<SqlEditorProps> = ({
  value,
  onChange,
  onExecute,
  onOptimize,
  isExecuting = false,
}) => {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Ctrl+Enter or Cmd+Enter to execute
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      if (!isExecuting && value.trim()) {
        onExecute();
      }
    }
  };

  return (
    <div
      className="flex flex-col h-full bg-slate-950 border-b border-slate-800"
      onKeyDown={handleKeyDown}
    >
      {/* Editor Toolbar */}
      <div className="px-4 py-2 border-b border-slate-800/80 bg-slate-900/40 flex items-center justify-between flex-wrap gap-2 flex-shrink-0">
        <div className="flex items-center gap-2">
          <button
            onClick={onExecute}
            disabled={isExecuting || !value.trim()}
            title="Execute query (Ctrl+Enter)"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-xs font-semibold rounded-md shadow transition-colors"
          >
            {isExecuting ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                <span>Running...</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Run Query</span>
                <span className="text-[10px] text-emerald-200 font-mono ml-1 hidden sm:inline">
                  Ctrl+Enter
                </span>
              </>
            )}
          </button>

          <button
            onClick={onOptimize}
            disabled={!value.trim()}
            title="Send query to Optimizer for plan analysis & benchmarking"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-xs font-medium rounded-md shadow transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Send to Optimizer</span>
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onChange("")}
            disabled={!value}
            title="Clear editor"
            className="p-1.5 text-slate-400 hover:text-slate-200 disabled:opacity-30 rounded hover:bg-slate-800 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Editor Surface */}
      <div className="flex-1 relative min-h-[160px]">
        <Suspense
          fallback={
            <div className="h-full flex items-center justify-center text-slate-500 text-xs font-mono">
              Loading SQL Editor...
            </div>
          }
        >
          <MonacoEditor
            height="100%"
            language="sql"
            theme="vs-dark"
            value={value}
            onChange={(val) => onChange(val || "")}
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              fontFamily: "'JetBrains Mono', 'Fira Code', 'Menlo', monospace",
              lineNumbers: "on",
              automaticLayout: true,
              scrollBeyondLastLine: false,
              wordWrap: "on",
              tabSize: 2,
              padding: { top: 8, bottom: 8 },
              scrollbar: {
                verticalScrollbarSize: 8,
                horizontalScrollbarSize: 8,
              },
            }}
          />
        </Suspense>
      </div>
    </div>
  );
};

