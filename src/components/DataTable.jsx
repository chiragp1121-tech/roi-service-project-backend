/**
 * Reusable Data Table Component
 * Formats any array of objects dynamically into a clean, responsive table.
 */
export default function DataTable({
  title,
  subtitle,
  data,
  emptyMessage = 'No records found',
}) {
  if (!data || !Array.isArray(data) || data.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        {title && <h3 className="mb-1 text-base font-bold text-gray-900">{title}</h3>}
        {subtitle && <p className="mb-4 text-xs text-gray-500">{subtitle}</p>}
        <div className="rounded-lg border border-dashed border-gray-200 py-8 text-center text-sm text-gray-400">
          {emptyMessage}
        </div>
      </div>
    );
  }

  // Extract all unique columns from the data objects
  const columns = Array.from(
    new Set(
      data.flatMap((row) => (row && typeof row === 'object' ? Object.keys(row) : []))
    )
  );

  // Format cell values
  const formatValue = (val) => {
    if (val === null || val === undefined || val === '') {
      return <span className="font-mono text-gray-300">—</span>;
    }
    if (typeof val === 'number') {
      // Check if float has more than 2 decimal digits
      if (!Number.isInteger(val)) {
        return val.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        });
      }
      return val.toLocaleString();
    }
    return String(val);
  };

  return (
    <div className="mb-6 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      {/* Table Header / Title */}
      {(title || subtitle) && (
        <div className="border-b border-gray-200 bg-white px-5 py-4">
          {title && <h3 className="text-base font-bold text-gray-900">{title}</h3>}
          {subtitle && <p className="mt-0.5 text-xs text-gray-500">{subtitle}</p>}
        </div>
      )}

      {/* Responsive Scrollable Container */}
      <div className="w-full overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-gray-300 bg-gray-100">
              {columns.map((col) => (
                <th
                  key={col}
                  className="whitespace-nowrap px-4 py-3 font-bold tracking-tight text-gray-900"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 text-gray-800">
            {data.map((row, idx) => {
              const isTotalRow =
                row['Service Improvement'] === 'Total' ||
                row['Service Type'] === 'Total' ||
                row['Milestone'] === 'Total';

              return (
                <tr
                  key={idx}
                  className={`transition-colors ${
                    isTotalRow
                      ? 'border-t-2 border-gray-300 bg-gray-50/80 font-bold text-gray-900'
                      : 'hover:bg-gray-50/60'
                  }`}
                >
                  {columns.map((col) => {
                    const val = row[col];
                    const isTotalCell =
                      isTotalRow &&
                      (col === 'Service Improvement' || col === 'Service Type');

                    return (
                      <td
                        key={col}
                        className={`whitespace-nowrap px-4 py-3 text-xs ${
                          isTotalCell ? 'font-bold text-gray-900' : ''
                        }`}
                      >
                        {formatValue(val)}
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
}
