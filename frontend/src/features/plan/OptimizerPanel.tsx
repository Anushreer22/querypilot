import React, { useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  Copy,
  Gauge,
  Sparkles,
  StopCircle,
} from "lucide-react";
import { api, ApiClientError } from "../../api/client";
import { Badge } from "../../components/Badge";
import { ConfirmModal } from "../../components/ConfirmModal";
import { BenchmarkCard } from "./BenchmarkCard";
import type { OptimizeResponse } from "../../types";

interface OptimizerPanelProps {
  sql: string;
}

export const OptimizerPanel: React.FC<OptimizerPanelProps> = ({ sql }) => {
  const [response, setResponse] = useState<OptimizeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isBenchmarking, setIsBenchmarking] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedDdl, setCopiedDdl] = useState<string | null>(null);

  const isBenchmarkDisabled = import.meta.env.VITE_BENCHMARK_ENABLED === "false";
  const abortControllerRef = useRef<AbortController | null>(null);

  const handleAnalyze = async () => {
    if (!sql.trim() || isLoading || isBenchmarking) return;
    setIsLoading(true);
    setError(null);

    try {
      const res = await api.optimizeQuery({ sql: sql.trim(), benchmark: false });
      setResponse(res);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.userMessage);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to analyze plan.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartBenchmark = async () => {
    setShowConfirmModal(false);
    if (!sql.trim() || isBenchmarking) return;

    setIsBenchmarking(true);
    setError(null);
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const res = await api.optimizeQuery(
        { sql: sql.trim(), benchmark: true, iterations: 7 },
        controller.signal
      );
      setResponse(res);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setError("Benchmark was cancelled by user.");
      } else if (err instanceof ApiClientError) {
        setError(err.userMessage);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to execute benchmark on sample_shop_bench.");
      }
    } finally {
      setIsBenchmarking(false);
      abortControllerRef.current = null;
    }
  };

  const handleCancelBenchmark = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  const handleCopyDdl = (ddl: string) => {
    navigator.clipboard.writeText(ddl);
    setCopiedDdl(ddl);
    setTimeout(() => setCopiedDdl(null), 2000);
  };

  return (
    <div className="flex flex-col h-full bg-slate-950 p-4 overflow-y-auto text-slate-100 select-text">
      {/* Top Action Toolbar */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800 flex-wrap gap-2 flex-shrink-0">
        <div className="flex items-center gap-2">
          <button
            onClick={handleAnalyze}
            disabled={isLoading || isBenchmarking || !sql.trim()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-xs font-semibold rounded-md shadow transition-colors"
            title="Run fast plan analysis on sample_shop (read-only, ~100ms)"
          >
            {isLoading ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                <span>Analyzing Plan...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5" />
                <span>Analyze Plan (Fast)</span>
              </>
            )}
          </button>

          {isBenchmarkDisabled ? (
            <button
              disabled
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 text-slate-500 cursor-not-allowed text-xs font-semibold rounded-md shadow border border-slate-700/50"
              title="Query benchmarking is disabled on the public demo instance to conserve cloud resources. Plan analysis and index suggestions are fully available."
            >
              <Gauge className="w-3.5 h-3.5" />
              <span>Benchmark (Disabled on Demo)</span>
            </button>
          ) : !isBenchmarking ? (
            <button
              onClick={() => setShowConfirmModal(true)}
              disabled={isLoading || !sql.trim()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-xs font-semibold rounded-md shadow transition-colors"
              title="Execute full benchmark on sample_shop_bench copy database (~5-10s)"
            >
              <Gauge className="w-3.5 h-3.5" />
              <span>Run Benchmark</span>
            </button>
          ) : (
            <button
              onClick={handleCancelBenchmark}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-md shadow transition-colors"
            >
              <StopCircle className="w-3.5 h-3.5" />
              <span>Cancel Benchmark</span>
            </button>
          )}
        </div>

        <div className="text-[11px] text-slate-400 font-mono">
          Target: <span className="text-slate-200">sample_shop</span> (analysis) &{" "}
          <span className="text-emerald-400">sample_shop_bench</span> (benchmark)
        </div>
      </div>

      {/* Confirmation Dialog */}
      <ConfirmModal
        isOpen={showConfirmModal}
        title="Execute Isolated Benchmark Protocol?"
        description="This creates a candidate index on the dedicated 'sample_shop_bench' copy database, performs 2 warm-ups + 7 measured iterations before and after, checks MD5 result set integrity, and cleans up the index. This typically takes 3 to 10 seconds. Live database 'sample_shop' is never modified."
        confirmLabel="Start Benchmark"
        onConfirm={handleStartBenchmark}
        onCancel={() => setShowConfirmModal(false)}
      />

      {/* Error Message */}
      {error && (
        <div className="p-3 my-2 bg-rose-950/40 border border-rose-800 rounded-lg text-rose-300 text-xs flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Benchmarking Progress Banner */}
      {isBenchmarking && (
        <div className="p-4 my-2 bg-indigo-950/40 border border-indigo-800/80 rounded-lg flex items-center justify-between text-xs text-indigo-200">
          <div className="flex items-center gap-2">
            <span className="w-4 h-4 border-2 border-indigo-400/20 border-t-indigo-400 rounded-full animate-spin flex-shrink-0" />
            <span>
              Benchmarking in progress on <strong>sample_shop_bench</strong> (2 warm-ups + 7 runs, verifying MD5 equivalence)...
            </span>
          </div>
          <button
            onClick={handleCancelBenchmark}
            className="text-[11px] px-2 py-1 bg-rose-900/60 hover:bg-rose-900 text-rose-200 rounded border border-rose-700 transition-colors"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Empty State */}
      {!response && !isLoading && !isBenchmarking && !error && (
        <div className="flex flex-col items-center justify-center p-12 text-slate-500 h-full space-y-2">
          <Gauge className="w-8 h-8 text-slate-600 stroke-[1.5]" />
          <p className="text-sm">Click "Analyze Plan" or "Run Benchmark" to evaluate current query.</p>
        </div>
      )}

      {/* Optimization Results */}
      {response && (
        <div className="space-y-4">
          {/* Plan Summary Bar */}
          <div className="p-3 bg-slate-900 border border-slate-800 rounded-lg flex items-center justify-between flex-wrap gap-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-200">{response.plan_summary}</span>
              <Badge
                variant={
                  response.improvement_label === "MEASURED"
                    ? "measured"
                    : response.improvement_label === "ESTIMATED"
                    ? "estimated"
                    : "neutral"
                }
                size="sm"
              >
                {response.improvement_label}
              </Badge>
            </div>

            <div className="flex items-center gap-3 text-slate-400 font-mono text-[11px]">
              <span>Cost: {response.total_cost.toFixed(1)}</span>
              <span>Planning: {response.planning_time_ms.toFixed(2)}ms</span>
              {response.execution_time_ms != null && (
                <span>Execution: {response.execution_time_ms.toFixed(2)}ms</span>
              )}
            </div>
          </div>

          {/* Benchmark Card (if benchmark ran) */}
          {response.benchmark && <BenchmarkCard benchmark={response.benchmark} />}

          {/* Bottleneck Findings */}
          {response.findings && response.findings.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                Detected Bottlenecks ({response.findings.length})
              </h4>
              <div className="space-y-1.5">
                {response.findings.map((finding, idx) => (
                  <div
                    key={idx}
                    className={`p-3 rounded-lg border text-xs flex items-start justify-between gap-3 ${
                      finding.severity === "critical"
                        ? "bg-rose-950/20 border-rose-900/60 text-rose-200"
                        : finding.severity === "warning"
                        ? "bg-amber-950/20 border-amber-900/60 text-amber-200"
                        : "bg-slate-900 border-slate-800 text-slate-300"
                    }`}
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={
                            finding.severity === "critical"
                              ? "error"
                              : finding.severity === "warning"
                              ? "warning"
                              : "info"
                          }
                          size="sm"
                          className="uppercase text-[9px]"
                        >
                          {finding.severity}
                        </Badge>
                        <span className="font-mono font-semibold">{finding.type}</span>
                        {finding.table && (
                          <span className="text-[11px] text-slate-400 font-mono">
                            on {finding.table}
                          </span>
                        )}
                      </div>
                      <p className="text-slate-300 text-[11px] leading-relaxed">
                        {finding.explanation}
                      </p>
                    </div>

                    <div className="text-[10px] text-slate-500 font-mono text-right flex-shrink-0">
                      Node: {finding.plan_node}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Index Suggestions */}
          {response.suggestions && response.suggestions.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                Application Index Recommendations ({response.suggestions.length})
              </h4>
              <div className="space-y-2">
                {response.suggestions.map((suggestion) => (
                  <div
                    key={suggestion.id}
                    className="p-3 bg-slate-900 border border-slate-800 rounded-lg space-y-2 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-200 font-mono">
                          {suggestion.id}
                        </span>
                        {suggestion.existing ? (
                          <Badge variant="neutral" size="sm">
                            Already Exists
                          </Badge>
                        ) : (
                          <Badge variant="info" size="sm">
                            New Candidate
                          </Badge>
                        )}
                      </div>

                      <button
                        onClick={() => handleCopyDdl(suggestion.ddl)}
                        className="inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200 transition-colors"
                      >
                        {copiedDdl === suggestion.ddl ? (
                          <>
                            <Check className="w-3 h-3 text-emerald-400" />
                            <span className="text-emerald-400">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3 h-3" />
                            <span>Copy DDL</span>
                          </>
                        )}
                      </button>
                    </div>

                    {/* DDL Code Box */}
                    <pre className="p-2 bg-slate-950 rounded border border-slate-800/80 text-emerald-300 font-mono text-[11px] overflow-x-auto whitespace-pre-wrap">
                      {suggestion.ddl}
                    </pre>

                    <p className="text-slate-300 text-[11px] leading-relaxed">
                      {suggestion.reasoning}
                    </p>

                    <div className="text-[10px] text-slate-400 flex items-center justify-between pt-1 border-t border-slate-800/60 flex-wrap gap-1">
                      <span>Benefit: {suggestion.estimated_benefit}</span>
                      <span>Risk: {suggestion.estimated_risk}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Plan Tree View (if plan data present) */}
          {/* Note: backend returns plan summary; PlanTreeView parses raw root if available */}
        </div>
      )}
    </div>
  );
};
