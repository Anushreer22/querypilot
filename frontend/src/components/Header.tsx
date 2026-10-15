import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Database, RefreshCw, Server, AlertCircle } from "lucide-react";
import { api } from "../api/client";

export const Header: React.FC = () => {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.getHealth(),
    refetchInterval: 10000,
    retry: 1,
  });

  const isHealthy = data?.status === "ok" && data.app_db === "ok" && data.shop_db === "ok";

  return (
    <header className="h-14 border-b border-slate-800 bg-slate-900/90 backdrop-blur px-4 flex items-center justify-between flex-shrink-0 z-20">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold shadow-md shadow-indigo-600/30">
            <Database className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-base text-slate-100 tracking-tight">QueryPilot</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800 font-mono">
                v0.1.0
              </span>
              {import.meta.env.VITE_DEMO_MODE === "true" && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-700/60 font-semibold tracking-wide uppercase">
                  Demo
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-400 leading-none">AI Database Engineer & Optimizer</p>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Health Indicator Pill */}
        <div className="flex items-center gap-2 bg-slate-950/60 border border-slate-800 rounded-lg px-2.5 py-1 text-xs">
          <Activity className="w-3.5 h-3.5 text-slate-400" />
          {isLoading ? (
            <span className="text-slate-400 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-slate-400 animate-pulse" />
              Connecting...
            </span>
          ) : isError ? (
            <span className="text-rose-400 flex items-center gap-1.5 font-medium">
              <span className="w-2 h-2 rounded-full bg-rose-500" />
              Backend Offline
            </span>
          ) : isHealthy ? (
            <div className="flex items-center gap-2 text-slate-300">
              <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50" />
              <span className="font-medium text-emerald-400">All Systems Operational</span>
              <span className="text-slate-600">|</span>
              <span className="text-[11px] text-slate-400 flex items-center gap-1">
                <Server className="w-3 h-3 text-slate-500" /> API: ok
              </span>
              <span className="text-[11px] text-slate-400 flex items-center gap-1">
                <Database className="w-3 h-3 text-slate-500" /> DB: ok
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-amber-400 font-medium">
              <AlertCircle className="w-3.5 h-3.5" />
              <span>Degraded: app_db={data?.app_db}, shop_db={data?.shop_db}</span>
            </div>
          )}

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Refresh system health"
            title="Refresh system health"
            className="ml-1 p-1 hover:text-slate-100 text-slate-400 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${isFetching ? "animate-spin text-indigo-400" : ""}`} />
          </button>
        </div>
      </div>
    </header>
  );
};

