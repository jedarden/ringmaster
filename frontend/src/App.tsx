import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { WorkersPage } from "./pages/WorkersPage";
import { QueuePage } from "./pages/QueuePage";
import { MetricsPage } from "./pages/MetricsPage";
import { LogsPage } from "./pages/LogsPage";
import { GraphPage } from "./pages/GraphPage";
import { Agentation } from "agentation";
import "./App.css";

// Force Agentation to be included (prevent tree-shaking)
// eslint-disable-next-line
console.log("Agentation loaded:", typeof Agentation);

// Always include Agentation - it handles its own dev-only rendering
function App() {
  return (
    <>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<ProjectsPage />} />
            <Route path="projects/:projectId" element={<ProjectDetailPage />} />
            <Route path="projects/:projectId/graph" element={<GraphPage />} />
            <Route path="workers" element={<WorkersPage />} />
            <Route path="queue" element={<QueuePage />} />
            <Route path="metrics" element={<MetricsPage />} />
            <Route path="logs" element={<LogsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Agentation />
    </>
  );
}

export default App;
