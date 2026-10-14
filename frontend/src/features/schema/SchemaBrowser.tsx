import React, { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Database,
  Key,
  Link as LinkIcon,
  Search,
  Table as TableIcon,
} from "lucide-react";
import { useSchema } from "./useSchema";
import type { TableInfo } from "../../types";

interface SchemaBrowserProps {
  onInsertText: (text: string) => void;
}

export const SchemaBrowser: React.FC<SchemaBrowserProps> = ({ onInsertText }) => {
  const { data, isLoading, isError, error } = useSchema();
  const [searchTerm, setSearchTerm] = useState("");
  const [collapsedTables, setCollapsedTables] = useState<Record<string, boolean>>({});

  const toggleTable = (tableName: string) => {
    setCollapsedTables((prev) => ({
      ...prev,
      [tableName]: !prev[tableName],
    }));
  };

  const filteredTables: TableInfo[] = (data?.tables || []).filter((table) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.toLowerCase();
    const tableMatches = table.name.toLowerCase().includes(term);
    const columnMatches = table.columns.some((c) =>
      c.name.toLowerCase().includes(term) || c.type.toLowerCase().includes(term)
    );
    return tableMatches || columnMatches;
  });

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-900/60 flex flex-col h-full flex-shrink-0 text-slate-200 select-none">
      <div className="p-3 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Database className="w-4 h-4 text-indigo-400" />
          <span className="text-xs font-semibold tracking-wider uppercase text-slate-300">
            Schema Browser
          </span>
        </div>
        <span className="text-[10px] text-slate-500 font-mono">
          {data?.tables ? `${data.tables.length} tables` : ""}
        </span>
      </div>

      {/* Search Input */}
      <div className="p-2 border-b border-slate-800/80">
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5 pointer-events-none" />
          <input
            type="text"
            placeholder="Filter tables & columns..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-md pl-8 pr-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
          />
        </div>
      </div>

      {/* Tables List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {isLoading ? (
          <div className="p-4 text-center text-xs text-slate-500 space-y-2">
            <div className="w-4 h-4 border-2 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin mx-auto" />
            <p>Loading schema...</p>
          </div>
        ) : isError ? (
          <div className="p-3 text-xs text-rose-400 bg-rose-950/40 rounded border border-rose-900/50">
            Failed to load schema: {error instanceof Error ? error.message : "Error"}
          </div>
        ) : filteredTables.length === 0 ? (
          <div className="p-4 text-center text-xs text-slate-500">
            No tables or columns match "{searchTerm}".
          </div>
        ) : (
          filteredTables.map((table) => {
            const isCollapsed = !!collapsedTables[table.name];
            return (
              <div
                key={table.name}
                className="border border-slate-800/80 rounded-md overflow-hidden bg-slate-950/40"
              >
                {/* Table Header */}
                <div className="flex items-center justify-between px-2 py-1.5 hover:bg-slate-800/60 transition-colors">
                  <button
                    onClick={() => toggleTable(table.name)}
                    className="flex items-center gap-1.5 text-left flex-1 min-w-0"
                    title={`Toggle ${table.name} columns`}
                  >
                    {isCollapsed ? (
                      <ChevronRight className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
                    )}
                    <TableIcon className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" />
                    <span className="text-xs font-medium text-slate-200 truncate">
                      {table.name}
                    </span>
                  </button>

                  <button
                    onClick={() => onInsertText(table.name)}
                    title={`Insert table "${table.name}" into editor`}
                    className="text-[10px] text-slate-500 hover:text-indigo-300 px-1 py-0.5 rounded hover:bg-slate-800 transition-colors"
                  >
                    +add
                  </button>
                </div>

                {/* Columns List */}
                {!isCollapsed && (
                  <div className="px-2 py-1 bg-slate-950/80 border-t border-slate-900 space-y-0.5">
                    {table.columns.map((col) => {
                      const isPk = table.primary_key.includes(col.name);
                      const fkInfo = table.foreign_keys.find((fk) =>
                        fk.constrained_columns.includes(col.name)
                      );

                      return (
                        <div
                          key={col.name}
                          onClick={() => onInsertText(col.name)}
                          title={`Click to insert column "${col.name}" into editor`}
                          className="flex items-center justify-between py-1 px-1.5 rounded hover:bg-slate-800/80 cursor-pointer transition-colors group text-[11px]"
                        >
                          <div className="flex items-center gap-1.5 min-w-0">
                            {isPk ? (
                              <span title="Primary Key">
                                <Key className="w-3 h-3 text-amber-400 flex-shrink-0" />
                              </span>
                            ) : fkInfo ? (
                              <span title={`Foreign Key -> ${fkInfo.referred_table}.${fkInfo.referred_columns.join(",")}`}>
                                <LinkIcon className="w-3 h-3 text-sky-400 flex-shrink-0" />
                              </span>
                            ) : (
                              <span className="w-3 h-3 flex-shrink-0 inline-block text-slate-600 text-center">
                                •
                              </span>
                            )}
                            <span className="text-slate-300 group-hover:text-slate-100 truncate font-mono">
                              {col.name}
                            </span>
                          </div>

                          <div className="flex items-center gap-1 flex-shrink-0 text-[10px] text-slate-500 font-mono">
                            <span>{col.type.toLowerCase()}</span>
                            {isPk && (
                              <span className="px-1 rounded bg-amber-950 text-amber-300 text-[9px] border border-amber-800">
                                PK
                              </span>
                            )}
                            {fkInfo && (
                              <span
                                className="px-1 rounded bg-sky-950 text-sky-300 text-[9px] border border-sky-800"
                                title={`FK -> ${fkInfo.referred_table}`}
                              >
                                FK
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};
