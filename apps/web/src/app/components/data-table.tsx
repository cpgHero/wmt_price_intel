import { displayLabel, displayValue } from "@/lib/presentation";

import type { JsonObject } from "@/lib/api";

export function DataTable({
  rows,
  emptyMessage = "No records were supplied in this result.",
}: Readonly<{ rows: JsonObject[]; emptyMessage?: string }>) {
  if (rows.length === 0)
    return <div className="empty-inline">{emptyMessage}</div>;
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{displayLabel(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => (
                <td key={column}>{displayValue(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
