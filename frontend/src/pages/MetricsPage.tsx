import { MetricsDashboard } from "../components/MetricsDashboard";

export function MetricsPage() {
  return (
    <div className="metrics-page">
      <div className="page-header">
        <h1>Metrics</h1>
      </div>
      <MetricsDashboard />
    </div>
  );
}
