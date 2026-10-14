/**
 * Format database primitives safely for plain text display in table cells.
 */
export function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "NULL";
  }

  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }

  if (typeof value === "number") {
    // Check if integer
    if (Number.isInteger(value)) {
      return value.toLocaleString();
    }
    // Float/Decimal
    return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  if (typeof value === "string") {
    // Check if ISO date string (YYYY-MM-DD or full timestamp)
    if (/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?/.test(value)) {
      const d = new Date(value);
      if (!isNaN(d.getTime())) {
        return d.toLocaleString();
      }
    }
    return value;
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
}

/**
 * Generate CSV string from columns and rows.
 */
export function convertToCsv(columns: string[], rows: Record<string, unknown>[]): string {
  if (!columns.length || !rows.length) return "";

  const escapeField = (val: unknown): string => {
    if (val === null || val === undefined) return "";
    const str = typeof val === "object" ? JSON.stringify(val) : String(val);
    if (str.includes(",") || str.includes('"') || str.includes("\n")) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };

  const headerLine = columns.map(escapeField).join(",");
  const dataLines = rows.map((row) => columns.map((col) => escapeField(row[col])).join(","));

  return [headerLine, ...dataLines].join("\n");
}

/**
 * Trigger client-side file download for CSV content.
 */
export function downloadCsvFile(csvContent: string, filename = "query_results.csv"): void {
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  link.style.visibility = "hidden";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

