import React, { useEffect, useState } from "react";
import { getHealth, HealthResponse } from "../api/client";
import { Activity, Database, RefreshCw, Server, AlertCircle, CheckCircle2, XCircle } from "lucide-react";

export const HealthStatus: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const checkHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getHealth();
      setHealth(data);
      setLastUpdated(new Date());
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to connect to backend server.");
      }
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const data = await getHealth();
        if (mounted) {
          setHealth(data);
          setLastUpdated(new Date());
        }
      } catch (err: unknown) {
        if (mounted) {
          if (err instanceof Error) {
            setError(err.message);
          } else {
            setError("Failed to connect to backend server.");
          }
          setHealth(null);
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="max-w-2xl mx-auto p-6">
      <div className="bg-slate-800 border border-slate-700 rounded-xl shadow-2xl p-6 sm:p-8">
        {/* Header */}
        <div className="flex items-center justify-between pb-6 border-b border-slate-700">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-indigo-600/20 text-indigo-400 rounded-lg">
              <Activity className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-wide">QueryPilot Status</h1>
              <p className="text-xs text-slate-400">System Architecture & Health Monitor</p>
            </div>
          </div>
          <button
            onClick={checkHealth}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 disabled:opacity-50 text-xs font-medium rounded-lg transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-indigo-400" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>

        {/* Content States */}
        {loading && !health ? (
          <div className="py-12 flex flex-col items-center justify-center text-slate-400 space-y-3">
            <RefreshCw className="w-8 h-8 animate-spin text-indigo-500" />
            <p className="text-sm">Connecting to backend service...</p>
          </div>
        ) : error ? (
          <div className="py-8">
            <div className="p-4 bg-red-950/40 border border-red-800/60 rounded-lg flex items-start space-x-3 text-red-300">
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-400" />
              <div>
                <h3 className="text-sm font-semibold text-red-200">Backend Unreachable</h3>
                <p className="text-xs mt-1 text-red-300/80">{error}</p>
                <p className="text-xs mt-2 text-slate-400">
                  Ensure the FastAPI backend is running on{" "}
                  <code className="text-slate-300 bg-slate-900 px-1 py-0.5 rounded">
                    {import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"}
                  </code>
                </p>
              </div>
            </div>
          </div>
        ) : health ? (
          <div className="py-6 space-y-4">
            {/* Backend API Service */}
            <div className="flex items-center justify-between p-4 bg-slate-900/60 border border-slate-700/60 rounded-lg">
              <div className="flex items-center space-x-3">
                <Server className="w-5 h-5 text-slate-400" />
                <div>
                  <div className="text-sm font-medium text-slate-200">FastAPI Backend</div>
                  <div className="text-xs text-slate-400">REST API & Lifespan Service</div>
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <span
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    health.status === "ok"
                      ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800"
                      : "bg-rose-950/80 text-rose-400 border border-rose-800"
                  }`}
                >
                  {health.status === "ok" ? (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Healthy
                    </>
                  ) : (
                    <>
                      <XCircle className="w-3.5 h-3.5 mr-1" /> Error
                    </>
                  )}
                </span>
              </div>
            </div>

            {/* App Database */}
            <div className="flex items-center justify-between p-4 bg-slate-900/60 border border-slate-700/60 rounded-lg">
              <div className="flex items-center space-x-3">
                <Database className="w-5 h-5 text-indigo-400" />
                <div>
                  <div className="text-sm font-medium text-slate-200">App Database (querypilot_app)</div>
                  <div className="text-xs text-slate-400">Role: app_rw (read/write access)</div>
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <span
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    health.app_db === "ok"
                      ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800"
                      : "bg-rose-950/80 text-rose-400 border border-rose-800"
                  }`}
                >
                  {health.app_db === "ok" ? (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Connected
                    </>
                  ) : (
                    <>
                      <XCircle className="w-3.5 h-3.5 mr-1" /> Disconnected
                    </>
                  )}
                </span>
              </div>
            </div>

            {/* Sample Shop Database */}
            <div className="flex items-center justify-between p-4 bg-slate-900/60 border border-slate-700/60 rounded-lg">
              <div className="flex items-center space-x-3">
                <Database className="w-5 h-5 text-amber-400" />
                <div>
                  <div className="text-sm font-medium text-slate-200">Sample Shop Database (sample_shop)</div>
                  <div className="text-xs text-slate-400">Role: readonly_user (read-only query target)</div>
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <span
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    health.shop_db === "ok"
                      ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800"
                      : "bg-rose-950/80 text-rose-400 border border-rose-800"
                  }`}
                >
                  {health.shop_db === "ok" ? (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Connected
                    </>
                  ) : (
                    <>
                      <XCircle className="w-3.5 h-3.5 mr-1" /> Disconnected
                    </>
                  )}
                </span>
              </div>
            </div>
          </div>
        ) : null}

        {/* Footer */}
        <div className="mt-4 pt-4 border-t border-slate-700 flex items-center justify-between text-xs text-slate-500">
          <span>PostgreSQL Host: 127.0.0.1:5436</span>
          {lastUpdated && <span>Last checked: {lastUpdated.toLocaleTimeString()}</span>}
        </div>
      </div>
    </div>
  );
};

