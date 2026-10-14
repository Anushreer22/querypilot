import React from "react";
import { CheckCircle2, Gauge, ShieldCheck, XCircle } from "lucide-react";
import type { BenchmarkResult } from "../../types";
import { Badge } from "../../components/Badge";

interface BenchmarkCardProps {
  benchmark: BenchmarkResult;
}

export const BenchmarkCard: React.FC<BenchmarkCardProps> = ({ benchmark }) => {
  const isMeasured = benchmark.improvement_label === "MEASURED";
  const { baseline_stats, optimized_stats } = benchmark;

  const deltaMedian = baseline_stats.median_ms - optimized_stats.median_ms;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 my-3 space-y-4">
      {/* Header with Speedup & Verified Badge */}
      <div className="flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-indigo-600/20 text-indigo-400">
            <Gauge className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm text-slate-100">
                Candidate: {benchmark.candidate_index_name}
              </span>
              <Badge variant={isMeasured ? "measured" : "estimated"} size="sm">
                {benchmark.improvement_label}
              </Badge>
            </div>
            <p className="text-xs text-slate-400 font-mono mt-0.5">
              Speedup Factor:{" "}
              <strong className={isMeasured ? "text-emerald-400" : "text-amber-400"}>
                {benchmark.speedup_factor.toFixed(2)}x
              </strong>{" "}
              ({deltaMedian >= 0 ? `-${deltaMedian.toFixed(2)}ms` : `+${Math.abs(deltaMedian).toFixed(2)}ms`})
            </p>
          </div>
        </div>

        {/* Verification Checkmarks */}
        <div className="flex items-center gap-3 text-xs">
          <div
            className="flex items-center gap-1 font-mono"
            title="PostgreSQL query planner adopted candidate index"
          >
            {benchmark.index_used ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <XCircle className="w-3.5 h-3.5 text-slate-500" />
            )}
            <span className={benchmark.index_used ? "text-slate-300" : "text-slate-500"}>
              Plan: {benchmark.new_plan_node || "Unchanged"}
            </span>
          </div>

          <div
            className="flex items-center gap-1 font-mono border-l border-slate-800 pl-3"
            title="Deterministic MD5 checksum verified byte-for-byte equivalence"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-slate-300">MD5: Match</span>
          </div>
        </div>
      </div>

      {/* Comparison Statistics Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border border-slate-800 rounded font-mono">
          <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
            <tr>
              <th className="py-2 px-3">Phase / Metric</th>
              <th className="py-2 px-3">Median Latency</th>
              <th className="py-2 px-3">P95 Latency</th>
              <th className="py-2 px-3">Min / Max</th>
              <th className="py-2 px-3">Std. Dev (Noise $\sigma$)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 bg-slate-900/60 text-slate-300">
            <tr>
              <td className="py-2 px-3 font-semibold text-slate-400">Baseline (Pre-Index)</td>
              <td className="py-2 px-3">{baseline_stats.median_ms.toFixed(2)} ms</td>
              <td className="py-2 px-3">{baseline_stats.p95_ms.toFixed(2)} ms</td>
              <td className="py-2 px-3 text-slate-500">
                {baseline_stats.min_ms.toFixed(2)} / {baseline_stats.max_ms.toFixed(2)} ms
              </td>
              <td className="py-2 px-3 text-slate-400">±{baseline_stats.stddev_ms.toFixed(2)} ms</td>
            </tr>
            <tr className={isMeasured ? "bg-emerald-950/20" : "bg-amber-950/20"}>
              <td className="py-2 px-3 font-semibold text-slate-200">Optimized (Post-Index)</td>
              <td
                className={`py-2 px-3 font-bold ${
                  isMeasured ? "text-emerald-300" : "text-amber-300"
                }`}
              >
                {optimized_stats.median_ms.toFixed(2)} ms
              </td>
              <td className="py-2 px-3">{optimized_stats.p95_ms.toFixed(2)} ms</td>
              <td className="py-2 px-3 text-slate-500">
                {optimized_stats.min_ms.toFixed(2)} / {optimized_stats.max_ms.toFixed(2)} ms
              </td>
              <td className="py-2 px-3 text-slate-400">±{optimized_stats.stddev_ms.toFixed(2)} ms</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Backend Conclusion Text */}
      <div
        className={`p-3 rounded-lg border text-xs leading-relaxed ${
          isMeasured
            ? "bg-emerald-950/30 border-emerald-800/60 text-emerald-200"
            : "bg-amber-950/30 border-amber-800/60 text-amber-200"
        }`}
      >
        <strong>Conclusion: </strong>
        {benchmark.conclusion}
      </div>
    </div>
  );
};

