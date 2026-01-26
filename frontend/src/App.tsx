import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { WorkersPage } from "./pages/WorkersPage";
import { QueuePage } from "./pages/QueuePage";
import { MetricsPage } from "./pages/MetricsPage";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<ProjectsPage />} />
          <Route path="projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="workers" element={<WorkersPage />} />
          <Route path="queue" element={<QueuePage />} />
          <Route path="metrics" element={<MetricsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
