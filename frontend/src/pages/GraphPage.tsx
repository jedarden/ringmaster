import { useParams, useNavigate } from "react-router-dom";
import { DependencyGraph } from "../components/DependencyGraph";

export function GraphPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  if (!projectId) {
    return (
      <div className="p-6">
        <div className="text-red-500">No project selected. Please select a project first.</div>
      </div>
    );
  }

  const handleNodeClick = (nodeId: string) => {
    // Navigate to task detail or show task info
    navigate(`/projects/${projectId}?task=${nodeId}`);
  };

  return (
    <div className="h-full flex flex-col">
      <div className="p-4 border-b bg-white">
        <h1 className="text-2xl font-bold">Dependency Graph</h1>
        <p className="text-gray-500 text-sm mt-1">
          Visualize task dependencies and relationships. Click a node to view task details.
        </p>
      </div>
      <div className="flex-1" style={{ minHeight: 0 }}>
        <DependencyGraph projectId={projectId} onNodeClick={handleNodeClick} />
      </div>
    </div>
  );
}
