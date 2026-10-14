import React, { useState } from "react";
import {
  Bot,
  Check,
  Code,
  Copy,
  HelpCircle,
  Play,
  Send,
  Sparkles,
  Zap,
} from "lucide-react";
import { api, ApiClientError } from "../../api/client";
import { AgentTimeline } from "./AgentTimeline";
import type {
  AgentActionItem,
  AgentAskResponse,
  AskEngineType,
  AskResponse,
  ExecuteQueryResponse,
} from "../../types";

interface AskPanelProps {
  onExecuteSql: (sql: string) => void;
  onResultsReceived: (res: ExecuteQueryResponse) => void;
}

const SAMPLE_QUESTIONS = [
  "What are our top 5 most expensive products?",
  "Show the total revenue and order count for delivered orders.",
  "Which users have placed more than 3 orders?",
  "List monthly gross revenue trends.",
];

export const AskPanel: React.FC<AskPanelProps> = ({
  onExecuteSql,
  onResultsReceived,
}) => {
  const [engine, setEngine] = useState<AskEngineType>("agent");
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Simple Mode Response
  const [simpleResponse, setSimpleResponse] = useState<AskResponse | null>(null);
  // Agent Mode Response
  const [agentResponse, setAgentResponse] = useState<AgentAskResponse | null>(null);
  // Re-loaded run details if reloaded via timeline
  const [reloadedSteps, setReloadedSteps] = useState<AgentActionItem[] | null>(null);
  const [isReloadingRun, setIsReloadingRun] = useState(false);
  const [copiedSql, setCopiedSql] = useState(false);

  const handleSubmit = async (q = question) => {
    const trimmed = q.trim();
    if (!trimmed || isLoading) return;

    setIsLoading(true);
    setError(null);
    setSimpleResponse(null);
    setAgentResponse(null);
    setReloadedSteps(null);

    try {
      if (engine === "agent") {
        const res = await api.askAgent({ question: trimmed });
        setAgentResponse(res);

        // If agent executed a query and returned rows, push to results table
        if (res.results && res.sql) {
          onResultsReceived({
            columns: res.results.columns ?? [],
            rows: res.results.rows ?? [],
            row_count: res.results.row_count,
            duration_ms: res.results.duration_ms,
            limit_injected: false,
            truncated: res.results.truncated,
            sanitized_sql: res.sql,
          });
        }
      } else {
        const res = await api.askSimple({ question: trimmed });
        setSimpleResponse(res);

        // If simple mode produced results, push to results table
        if (res.results && res.sql) {
          onResultsReceived({
            columns: res.results.columns,
            rows: res.results.rows,
            row_count: res.results.row_count,
            duration_ms: res.results.duration_ms,
            limit_injected: false,
            truncated: res.results.truncated,
            sanitized_sql: res.sql,
          });
        }
      }
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.userMessage);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unknown error occurred while submitting question.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleReloadRun = async (runId: string) => {
    setIsReloadingRun(true);
    try {
      const detail = await api.getAgentRun(runId);
      setReloadedSteps(detail.actions || []);
    } catch (err) {
      console.error("Failed to reload agent run:", err);
    } finally {
      setIsReloadingRun(false);
    }
  };

  const handleCopySql = (sql: string) => {
    navigator.clipboard.writeText(sql);
    setCopiedSql(true);
    setTimeout(() => setCopiedSql(false), 2000);
  };

  const activeSql = agentResponse?.sql || simpleResponse?.sql;
  const activeAnswer = agentResponse?.final_answer || simpleResponse?.explanation;
  const activeAssumptions = agentResponse?.assumptions || simpleResponse?.assumptions || [];
  const clarificationQuestion = simpleResponse?.clarification?.clarification_question;

  return (
    <div className="flex flex-col h-full bg-slate-950 p-4 overflow-y-auto">
      {/* Engine Toggle & Description */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400 font-medium">Model Engine:</span>
          <div className="flex p-0.5 bg-slate-900 border border-slate-800 rounded-lg">
            <button
              onClick={() => setEngine("agent")}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                engine === "agent"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Bot className="w-3.5 h-3.5" />
              <span>Agent Mode</span>
              <span className="text-[10px] opacity-75 font-mono ml-0.5">(Multi-step)</span>
            </button>
            <button
              onClick={() => setEngine("simple")}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                engine === "simple"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Zap className="w-3.5 h-3.5" />
              <span>Simple Mode</span>
              <span className="text-[10px] opacity-75 font-mono ml-0.5">(One-shot)</span>
            </button>
          </div>
        </div>

        <p className="text-[11px] text-slate-500">
          {engine === "agent"
            ? "Autonomous reasoning loop with schema discovery, explain, and self-correction."
            : "Direct natural language translation with single prompt-and-repair flow."}
        </p>
      </div>

      {/* Question Input Box */}
      <div className="relative mb-3">
        <textarea
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
              e.preventDefault();
              handleSubmit();
            }
          }}
          placeholder="Ask a question in plain English (e.g. 'What are our top 5 most expensive products?')"
          disabled={isLoading}
          className="w-full bg-slate-900 border border-slate-800 rounded-lg p-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors resize-none disabled:opacity-50"
        />

        <div className="flex items-center justify-between mt-2">
          {/* Sample Prompts */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] text-slate-500 flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-indigo-400" /> Examples:
            </span>
            {SAMPLE_QUESTIONS.slice(0, 2).map((sq) => (
              <button
                key={sq}
                onClick={() => {
                  setQuestion(sq);
                  handleSubmit(sq);
                }}
                disabled={isLoading}
                className="text-[11px] text-slate-400 hover:text-indigo-300 bg-slate-900 border border-slate-800 hover:border-slate-700 px-2 py-0.5 rounded transition-colors truncate max-w-xs"
              >
                {sq}
              </button>
            ))}
          </div>

          <button
            onClick={() => handleSubmit()}
            disabled={isLoading || !question.trim()}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-xs font-semibold rounded-lg shadow transition-colors flex-shrink-0"
          >
            {isLoading ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                <span>Thinking...</span>
              </>
            ) : (
              <>
                <Send className="w-3.5 h-3.5" />
                <span>Ask Database</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error Message Banner */}
      {error && (
        <div className="p-3 my-2 bg-rose-950/40 border border-rose-800/80 rounded-lg text-rose-300 text-xs">
          <strong>Error: </strong> {error}
        </div>
      )}

      {/* Clarification Box */}
      {clarificationQuestion && (
        <div className="p-4 my-2 bg-amber-950/40 border border-amber-800/60 rounded-lg text-amber-200 text-xs space-y-2">
          <div className="flex items-center gap-2 font-semibold">
            <HelpCircle className="w-4 h-4 text-amber-400 flex-shrink-0" />
            <span>Clarification Needed:</span>
          </div>
          <p className="text-slate-300">{clarificationQuestion}</p>
          <div className="pt-2">
            <button
              onClick={() => {
                setQuestion(clarificationQuestion);
              }}
              className="px-2.5 py-1 bg-amber-900/60 hover:bg-amber-900 text-amber-200 text-[11px] font-medium rounded border border-amber-700 transition-colors"
            >
              Adopt Suggestion
            </button>
          </div>
        </div>
      )}

      {/* Agent Timeline (Agent Mode Only) */}
      {agentResponse && (
        <AgentTimeline
          steps={reloadedSteps || agentResponse.steps || []}
          runId={agentResponse.run_id}
          onReloadRun={handleReloadRun}
          isReloading={isReloadingRun}
        />
      )}

      {/* Synthesized Answer & SQL Preview Card */}
      {activeAnswer && (
        <div className="p-4 my-3 bg-slate-900 border border-slate-800 rounded-lg space-y-3">
          <div>
            <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400 block mb-1">
              Answer & Synthesis
            </span>
            <p className="text-sm text-slate-100 whitespace-pre-wrap leading-relaxed">
              {activeAnswer}
            </p>
          </div>

          {activeAssumptions.length > 0 && (
            <div>
              <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400 block mb-1">
                Assumptions Made
              </span>
              <ul className="list-disc list-inside text-xs text-slate-400 space-y-0.5">
                {activeAssumptions.map((asm, i) => (
                  <li key={i}>{asm}</li>
                ))}
              </ul>
            </div>
          )}

          {activeSql && (
            <div className="pt-2 border-t border-slate-800">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400 flex items-center gap-1 font-mono">
                  <Code className="w-3 h-3 text-indigo-400" /> Generated SQL
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleCopySql(activeSql)}
                    className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center gap-1 transition-colors"
                  >
                    {copiedSql ? (
                      <>
                        <Check className="w-3 h-3 text-emerald-400" />
                        <span className="text-emerald-400">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>

                  <button
                    onClick={() => onExecuteSql(activeSql)}
                    className="text-[11px] text-indigo-400 hover:text-indigo-300 font-medium flex items-center gap-1 transition-colors"
                  >
                    <Play className="w-3 h-3 fill-current" />
                    <span>Open in Editor</span>
                  </button>
                </div>
              </div>

              <pre className="p-3 bg-slate-950 rounded border border-slate-800/80 text-xs font-mono text-emerald-300 overflow-x-auto whitespace-pre-wrap">
                {activeSql}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
