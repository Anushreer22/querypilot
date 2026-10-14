import React, { useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Layers,
  Terminal,
  XCircle,
} from "lucide-react";
import type { AgentActionItem } from "../../types";
import { Badge } from "../../components/Badge";

interface AgentTimelineProps {
  steps: AgentActionItem[];
  runId?: string;
  onReloadRun?: (runId: string) => void;
  isReloading?: boolean;
}

export const AgentTimeline: React.FC<AgentTimelineProps> = ({
  steps,
  runId,
  onReloadRun,
  isReloading = false,
}) => {
  const [expandedSteps, setExpandedSteps] = useState<Record<number, boolean>>({});

  const toggleStep = (stepNumber: number) => {
    setExpandedSteps((prev) => ({
      ...prev,
      [stepNumber]: !prev[stepNumber],
    }));
  };

  if (!steps.length) return null;

  return (
    <div className="bg-slate-950 border border-slate-800 rounded-lg p-4 my-3 text-slate-200">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-3">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-indigo-400" />
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Agent Reasoning Timeline
          </h4>
          <span className="text-[11px] text-slate-500 font-mono">({steps.length} steps)</span>
        </div>

        {runId && onReloadRun && (
          <button
            onClick={() => onReloadRun(runId)}
            disabled={isReloading}
            className="text-[11px] font-mono text-indigo-400 hover:text-indigo-300 transition-colors disabled:opacity-50 flex items-center gap-1"
            title="Reload full audit log for this agent run"
          >
            <span>Run: {runId.slice(0, 8)}...</span>
            {isReloading && (
              <span className="w-2.5 h-2.5 border border-indigo-400/20 border-t-indigo-400 rounded-full animate-spin" />
            )}
          </button>
        )}
      </div>

      <div className="space-y-2 relative before:absolute before:inset-0 before:left-3.5 before:w-0.5 before:bg-slate-800 before:pointer-events-none">
        {steps.map((step) => {
          const isExpanded = !!expandedSteps[step.step];
          const isError = step.status === "error";
          const isRejected = step.status === "rejected";

          return (
            <div
              key={step.step}
              className={`relative pl-8 transition-colors ${
                isError
                  ? "bg-rose-950/20 border-l-2 border-rose-500 rounded-r"
                  : isRejected
                  ? "bg-amber-950/20 border-l-2 border-amber-500 rounded-r"
                  : ""
              }`}
            >
              {/* Step Marker Dot */}
              <div
                className={`absolute left-2 top-2 w-3.5 h-3.5 rounded-full flex items-center justify-center -translate-x-1/2 border z-10 ${
                  isError
                    ? "bg-rose-950 border-rose-500 text-rose-400"
                    : isRejected
                    ? "bg-amber-950 border-amber-500 text-amber-400"
                    : "bg-slate-900 border-indigo-500 text-indigo-400"
                }`}
              >
                {isError ? (
                  <XCircle className="w-2.5 h-2.5" />
                ) : isRejected ? (
                  <AlertCircle className="w-2.5 h-2.5" />
                ) : (
                  <CheckCircle2 className="w-2.5 h-2.5" />
                )}
              </div>

              {/* Step Header */}
              <div
                onClick={() => toggleStep(step.step)}
                className="flex items-center justify-between p-2 rounded-md hover:bg-slate-900/60 cursor-pointer transition-colors"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-[11px] font-mono text-slate-500">#{step.step}</span>
                  <Terminal className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                  <span className="text-xs font-mono font-medium text-slate-200 truncate">
                    {step.tool}
                  </span>
                  <Badge
                    variant={isError ? "error" : isRejected ? "warning" : "success"}
                    size="sm"
                    className="uppercase text-[9px]"
                  >
                    {step.status}
                  </Badge>
                </div>

                <div className="flex items-center gap-2 text-[11px] text-slate-500 font-mono">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3 text-slate-600" />
                    {step.duration_ms.toFixed(1)} ms
                  </span>
                  {isExpanded ? (
                    <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                  )}
                </div>
              </div>

              {/* Step Expanded Content */}
              {isExpanded && (
                <div className="p-3 my-1 ml-2 bg-slate-900 border border-slate-800 rounded-md text-xs space-y-2 font-mono">
                  {step.summary && (
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase font-sans font-semibold">
                        Summary
                      </span>
                      <p className="text-slate-300 text-[11px] whitespace-pre-wrap">
                        {step.summary}
                      </p>
                    </div>
                  )}

                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase font-sans font-semibold mb-1">
                      Arguments
                    </span>
                    <pre className="p-2 bg-slate-950 rounded border border-slate-800 text-slate-300 overflow-x-auto text-[11px]">
                      {JSON.stringify(step.arguments, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

