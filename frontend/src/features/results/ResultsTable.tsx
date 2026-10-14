import React, { useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  AlertTriangle,
  Check,
  Copy,
  Download,
  FileSpreadsheet,
  Layers,
  Timer,
} from "lucide-react";
import { convertToCsv, downloadCsvFile, formatCellValue } from "./formatters";
import { Badge } from "../../components/Badge";

export interface ResultsTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount?: number;
  durationMs?: number;
  truncated?: boolean;
  limitInjected?: boolean;
  isLoading?: boolean;
  emptyMessage?: string;
}

export const ResultsTable: React.FC<ResultsTableProps> = ({
  columns,
  rows,
  rowCount = rows.length,
  durationMs,
  truncated = false,
  limitInjected = false,
  isLoading = false,
  emptyMessage = "No query results to display.",
}) => {
  const [copied, setCopied] = useState(false);
  const parentRef = useRef<HTMLDivElement>(null);

  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 36,
    overscan: 15,
    initialRect: { width: 1000, height: 600 },
  });


  const handleCopyCsv = () => {
    const csv = convertToCsv(columns, rows);
    navigator.clipboard.writeText(csv);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadCsv = () => {
    const csv = convertToCsv(columns, rows);
    downloadCsvFile(csv);
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-slate-400 space-y-3 h-full">
        <div className="w-6 h-6 border-2 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin" />
        <p className="text-sm font-medium">Executing read-only SQL query...</p>
      </div>
    );
  }

  if (!columns.length || !rows.length) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-slate-500 h-full space-y-2">
        <FileSpreadsheet className="w-8 h-8 text-slate-600 stroke-[1.5]" />
        <p className="text-sm">{emptyMessage}</p>
      </div>
    );
  }

  const virtualItems = rowVirtualizer.getVirtualItems();
  // Fallback for non-layout environments (e.g. JSDOM in unit tests) where clientHeight is 0
  const itemsToRender =
    virtualItems.length > 0
      ? virtualItems
      : rows.slice(0, 50).map((_, index) => ({
          index,
          start: index * 36,
          size: 36,
          key: index,
        }));

  return (
    <div className="flex flex-col h-full bg-slate-950 text-slate-100 select-text">
      {/* Results Header Toolbar */}
      <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between flex-wrap gap-2 flex-shrink-0">
        <div className="flex items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5 text-slate-300 font-mono">
            <Layers className="w-3.5 h-3.5 text-indigo-400" />
            <span className="font-semibold">{rowCount.toLocaleString()}</span>
            <span className="text-slate-500">rows</span>
          </div>

          {durationMs !== undefined && (
            <div className="flex items-center gap-1.5 text-slate-400 font-mono border-l border-slate-800 pl-3">
              <Timer className="w-3.5 h-3.5 text-slate-500" />
              <span>{durationMs.toFixed(2)} ms</span>
            </div>
          )}

          {limitInjected && (
            <Badge variant="warning" size="sm" className="font-mono">
              LIMIT injected (capped)
            </Badge>
          )}

          {truncated && (
            <Badge variant="error" size="sm" className="font-mono">
              Truncated (1,000 max)
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleCopyCsv}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded border border-slate-700 transition-colors"
            title="Copy as CSV"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-emerald-400">Copied</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5 text-slate-400" />
                <span>Copy CSV</span>
              </>
            )}
          </button>

          <button
            onClick={handleDownloadCsv}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded border border-slate-700 transition-colors"
            title="Download results as CSV file"
          >
            <Download className="w-3.5 h-3.5 text-slate-400" />
            <span>Download CSV</span>
          </button>
        </div>
      </div>

      {/* Truncation Warning Alert Banner */}
      {truncated && (
        <div className="px-4 py-2 bg-amber-950/60 border-b border-amber-800/60 flex items-center gap-2 text-xs text-amber-200">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
          <span>
            Results were truncated at <strong>1,000 rows</strong> to protect browser memory and network bandwidth. Use more specific filters or an explicit LIMIT.
          </span>
        </div>
      )}

      {/* Virtualized Table Container */}
      <div ref={parentRef} className="flex-1 overflow-auto relative">
        <table className="w-full text-left text-xs border-collapse">
          {/* Sticky Header */}
          <thead className="sticky top-0 z-10 bg-slate-900 border-b border-slate-800 text-slate-400 shadow-sm">
            <tr>
              <th className="py-2 px-3 w-12 text-slate-600 font-mono text-center font-normal border-r border-slate-850">
                #
              </th>
              {columns.map((col) => (
                <th
                  key={col}
                  className="py-2 px-3 font-semibold text-slate-200 border-r border-slate-800/80 whitespace-nowrap"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>

          {/* Virtualized Body */}
          <tbody
            style={{
              height: `${rowVirtualizer.getTotalSize()}px`,
              position: "relative",
            }}
          >
            {itemsToRender.map((virtualRow) => {
              const row = rows[virtualRow.index];
              const isEven = virtualRow.index % 2 === 0;

              return (
                <tr
                  key={virtualRow.index}
                  data-index={virtualRow.index}
                  ref={virtualItems.length > 0 ? rowVirtualizer.measureElement : undefined}
                  className={`absolute top-0 left-0 w-full flex border-b border-slate-800/40 hover:bg-indigo-950/20 transition-colors ${
                    isEven ? "bg-slate-950" : "bg-slate-900/30"
                  }`}
                  style={{
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  <td className="py-1.5 px-3 w-12 text-slate-600 text-center font-mono border-r border-slate-850 flex-shrink-0 select-none">
                    {virtualRow.index + 1}
                  </td>
                  {columns.map((col) => {
                    const rawVal = row ? row[col] : null;
                    const isNull = rawVal === null || rawVal === undefined;
                    const formatted = formatCellValue(rawVal);
                    const isNum = typeof rawVal === "number";

                    return (
                      <td
                        key={col}
                        className={`py-1.5 px-3 border-r border-slate-850 flex-1 truncate font-mono text-[11px] ${
                          isNum ? "text-right" : "text-left"
                        } ${isNull ? "text-slate-600 italic" : "text-slate-300"}`}
                      >
                        {/* INVARIANT: Rendered strictly as raw text node. Zero dangerouslySetInnerHTML */}
                        {formatted}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
