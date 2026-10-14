import React, { useState } from "react";
import { ChevronDown, ChevronRight, Layers } from "lucide-react";
import type { PlanNode } from "../../types";

interface PlanTreeViewProps {
  rootNode: PlanNode;
}

const PlanNodeItem: React.FC<{ node: PlanNode; depth?: number }> = ({
  node,
  depth = 0,
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const hasChildren = node.plans && node.plans.length > 0;
  const isSeqScan = node.node_type === "Seq Scan";

  return (
    <div className="font-mono text-xs select-none">
      <div
        className={`flex items-center gap-2 py-1 px-2 rounded hover:bg-slate-800/60 cursor-pointer transition-colors ${
          isSeqScan ? "bg-amber-950/20 text-amber-200 border-l-2 border-amber-500" : "text-slate-200"
        }`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => hasChildren && setIsExpanded(!isExpanded)}
      >
        {hasChildren ? (
          isExpanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
          )
        ) : (
          <span className="w-3.5 h-3.5 flex-shrink-0 inline-block text-slate-600 text-center">•</span>
        )}

        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <span
            className={`font-semibold ${
              isSeqScan ? "text-amber-400 font-bold" : "text-indigo-300"
            }`}
          >
            {node.node_type}
          </span>

          {node.relation_name && (
            <span className="text-slate-300 bg-slate-900 px-1.5 py-0.2 rounded border border-slate-800 text-[11px]">
              on {node.relation_name}
            </span>
          )}

          {node.index_name && (
            <span className="text-emerald-300 bg-emerald-950/80 px-1.5 py-0.2 rounded border border-emerald-800 text-[11px]">
              using {node.index_name}
            </span>
          )}

          <span className="text-slate-500 text-[11px]">
            (cost={(node.startup_cost ?? 0).toFixed(1)}..{(node.total_cost ?? 0).toFixed(1)} rows=
            {node.actual_rows !== null && node.actual_rows !== undefined
              ? `${Math.round(node.actual_rows)} [est: ${Math.round(node.plan_rows ?? 0)}]`
              : Math.round(node.plan_rows ?? 0)}
            {node.actual_total_time !== null && node.actual_total_time !== undefined
              ? ` time=${node.actual_total_time.toFixed(2)}ms`
              : ""}
            )
          </span>

          {node.rows_removed_by_filter !== null && node.rows_removed_by_filter !== undefined && (
            <span className="text-rose-400 text-[10px] bg-rose-950/60 px-1 rounded border border-rose-900">
              discarded {node.rows_removed_by_filter.toLocaleString()} rows
            </span>
          )}
        </div>
      </div>

      {hasChildren && isExpanded && (
        <div className="space-y-0.5">
          {node.plans?.map((child: PlanNode, idx: number) => (
            <PlanNodeItem key={idx} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
};

export const PlanTreeView: React.FC<PlanTreeViewProps> = ({ rootNode }) => {
  return (
    <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 my-2 overflow-x-auto">
      <div className="flex items-center gap-2 pb-2 mb-2 border-b border-slate-800 text-xs font-semibold uppercase tracking-wider text-slate-400 font-sans">
        <Layers className="w-3.5 h-3.5 text-indigo-400" />
        <span>Execution Plan Tree</span>
      </div>
      <PlanNodeItem node={rootNode} />
    </div>
  );
};
