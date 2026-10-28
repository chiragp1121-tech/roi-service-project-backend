import { useState } from 'react';
import { projectService } from '../api/projectService';
import DataTable from '../components/DataTable';
import {
  Search,
  RefreshCw,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';

export default function PlannedVsActual() {
  const [projectId, setProjectId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [apiData, setApiData] = useState(null);
  const [showMoreDetails, setShowMoreDetails] = useState(false);

  // Fetch Planned vs Actual from API
  const handleFetchData = async (e) => {
    if (e) e.preventDefault();
    if (!projectId.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const response = await projectService.getProjectServiceActual(projectId.trim());
      setApiData(response);
    } catch (err) {
      console.error('API Error:', err);
      setError(err.message || 'Failed to fetch Planned vs Actual data from API.');
    } finally {
      setLoading(false);
    }
  };

  const tables = apiData?.tables || {};

  return (
    <div className="space-y-6 pb-12">
      {/* 1. Project ID Input Card */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <form onSubmit={handleFetchData} className="max-w-xl">
          <div className="space-y-2">
            <label
              htmlFor="projectId"
              className="block text-sm font-semibold text-gray-800"
            >
              Project ID
            </label>

            <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
              <div className="relative flex-1">
                <input
                  id="projectId"
                  type="text"
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                  placeholder="Enter Project ID"
                  className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm text-gray-900 transition placeholder:text-gray-400 focus:border-[#0c72af] focus:outline-none focus:ring-2 focus:ring-[#0c72af]/20"
                  required
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg bg-[#0c72af] px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-[#0a6094] active:bg-[#084e79] disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    <span>Fetching...</span>
                  </>
                ) : (
                  <>
                    <Search className="h-4 w-4" />
                    <span>Get Planned vs Actual</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-500" />
          <div>
            <p className="font-semibold text-red-900">API Error</p>
            <p className="mt-0.5 text-xs text-red-700">{error}</p>
          </div>
        </div>
      )}

      {/* 2. Main Planned vs Actual Table (Default Top View) */}
      {apiData && (
        <div>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-lg font-bold text-gray-900">Planned vs Actual</h2>
            <span className="font-mono text-xs text-gray-500">
              Project ID: #{apiData.project_id}
            </span>
          </div>

          <DataTable
            data={tables.planned_vs_actual}
            emptyMessage="No planned vs actual comparison records found for this project."
          />

          {/* 3. "Show more details" Collapsible Accordion */}
          <div className="mt-8 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <button
              type="button"
              onClick={() => setShowMoreDetails(!showMoreDetails)}
              className="flex w-full cursor-pointer items-center justify-between border-b border-transparent bg-white px-5 py-4 text-left transition hover:bg-gray-50 data-[expanded=true]:border-gray-200"
              data-expanded={showMoreDetails}
            >
              <div className="flex items-center gap-2 text-sm font-semibold text-gray-800">
                {showMoreDetails ? (
                  <ChevronDown className="h-4 w-4 text-gray-500" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-gray-500" />
                )}
                <span>Show more details</span>
              </div>
            </button>

            {/* Expanded Detailed Tables */}
            {showMoreDetails && (
              <div className="space-y-8 border-t border-gray-200 bg-gray-50/40 p-5 sm:p-6">
                {/* Actual Services */}
                <div>
                  <h3 className="mb-3 text-base font-bold text-gray-900">
                    Actual Services
                  </h3>
                  <DataTable data={tables.actual} />
                </div>

                {/* Current Services */}
                <div>
                  <h3 className="mb-3 text-base font-bold text-gray-900">
                    Current Services (matching current services)
                  </h3>
                  <DataTable data={tables.current_services} />
                </div>

                {/* Future Services */}
                <div>
                  <h3 className="mb-3 text-base font-bold text-gray-900">
                    Future Services
                  </h3>
                  <DataTable data={tables.future_services} />
                </div>

                {/* Cost and Schedule */}
                <div>
                  <h3 className="mb-3 text-base font-bold text-gray-900">
                    Cost and Schedule
                  </h3>
                  <DataTable data={tables.cost_schedule} />
                </div>

                {/* Future - Current Margin Contribution */}
                <div>
                  <h3 className="mb-3 text-base font-bold text-gray-900">
                    Future - Current Margin Contribution
                  </h3>
                  <DataTable data={tables.future_current_margin} />
                </div>

                {/* Summary Table */}
                <div>
                  <h3 className="mb-3 text-base font-bold text-gray-900">
                    Summary Overview
                  </h3>
                  <DataTable data={tables.summary} />
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
