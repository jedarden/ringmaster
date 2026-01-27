import { LogsViewer } from "../components/LogsViewer";

export function LogsPage() {
  return (
    <div className="page logs-page">
      <div className="page-header">
        <h2>System Logs</h2>
        <p className="page-description">
          View logs from all Ringmaster components. Filter by level, component, or search messages.
        </p>
      </div>
      <LogsViewer autoRefresh refreshInterval={5000} />
    </div>
  );
}
