export function exportCsv(columns: string[], rows: (string | number | null)[][], filename = "query-result.csv"): void {
  const quote = (v: string | number | null) => '"' + String(v ?? "").replaceAll('"', '""') + '"';
  const lines = [columns.map(quote).join(",")];
  for (const row of rows) lines.push(row.map(quote).join(","));
  const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
