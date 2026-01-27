import { useEffect, useRef, useState, useCallback } from "react";
import type { GraphData, GraphNode, GraphEdge, TaskStatus, Priority } from "../types";
import { getGraph } from "../api/client";

interface DependencyGraphProps {
  projectId: string;
  onNodeClick?: (nodeId: string) => void;
}

interface SimNode extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

const STATUS_COLORS: Record<TaskStatus, string> = {
  draft: "#9ca3af",
  ready: "#3b82f6",
  assigned: "#8b5cf6",
  in_progress: "#f59e0b",
  blocked: "#ef4444",
  review: "#06b6d4",
  done: "#22c55e",
  failed: "#dc2626",
};

const TYPE_SHAPES = {
  epic: "hexagon",
  task: "rect",
  subtask: "circle",
} as const;

const PRIORITY_SIZES: Record<Priority, number> = {
  P0: 40,
  P1: 35,
  P2: 30,
  P3: 25,
  P4: 20,
};

function getNodeRadius(node: GraphNode): number {
  return PRIORITY_SIZES[node.priority] || 30;
}

export function DependencyGraph({ projectId, onNodeClick }: DependencyGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [simNodes, setSimNodes] = useState<SimNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [includeDone, setIncludeDone] = useState(false);
  const [includeSubtasks, setIncludeSubtasks] = useState(true);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const animationRef = useRef<number | undefined>(undefined);
  const isDragging = useRef(false);
  const dragNode = useRef<string | null>(null);

  // Load graph data
  const loadGraph = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getGraph(projectId, {
        include_done: includeDone,
        include_subtasks: includeSubtasks,
      });
      setGraphData(data);
      setEdges(data.edges);

      // Initialize node positions in a circle
      const centerX = dimensions.width / 2;
      const centerY = dimensions.height / 2;
      const radius = Math.min(dimensions.width, dimensions.height) * 0.35;

      const nodes: SimNode[] = data.nodes.map((node, i) => {
        const angle = (2 * Math.PI * i) / data.nodes.length;
        return {
          ...node,
          x: centerX + radius * Math.cos(angle),
          y: centerY + radius * Math.sin(angle),
          vx: 0,
          vy: 0,
        };
      });
      setSimNodes(nodes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load graph");
    } finally {
      setLoading(false);
    }
  }, [projectId, includeDone, includeSubtasks, dimensions]);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  // Update dimensions on resize
  useEffect(() => {
    const updateDimensions = () => {
      if (svgRef.current) {
        const rect = svgRef.current.parentElement?.getBoundingClientRect();
        if (rect) {
          setDimensions({ width: rect.width, height: rect.height });
        }
      }
    };
    updateDimensions();
    window.addEventListener("resize", updateDimensions);
    return () => window.removeEventListener("resize", updateDimensions);
  }, []);

  // Force-directed simulation
  useEffect(() => {
    if (simNodes.length === 0) return;

    const simulate = () => {
      setSimNodes((prevNodes) => {
        const nodes = prevNodes.map((n) => ({ ...n }));
        const nodeMap = new Map(nodes.map((n) => [n.id, n]));

        // Apply forces
        const centerX = dimensions.width / 2;
        const centerY = dimensions.height / 2;

        // Center force
        for (const node of nodes) {
          if (isDragging.current && dragNode.current === node.id) continue;
          node.vx += (centerX - node.x) * 0.001;
          node.vy += (centerY - node.y) * 0.001;
        }

        // Repulsion between nodes
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i];
            const b = nodes[j];
            if (isDragging.current && (dragNode.current === a.id || dragNode.current === b.id)) continue;

            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const minDist = getNodeRadius(a) + getNodeRadius(b) + 30;

            if (dist < minDist * 3) {
              const force = (minDist * 3 - dist) / dist * 0.1;
              a.vx -= dx * force;
              a.vy -= dy * force;
              b.vx += dx * force;
              b.vy += dy * force;
            }
          }
        }

        // Edge attraction
        for (const edge of edges) {
          const source = nodeMap.get(edge.source);
          const target = nodeMap.get(edge.target);
          if (!source || !target) continue;
          if (isDragging.current && (dragNode.current === source.id || dragNode.current === target.id)) continue;

          const dx = target.x - source.x;
          const dy = target.y - source.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const idealDist = 120;
          const force = (dist - idealDist) / dist * 0.02;

          source.vx += dx * force;
          source.vy += dy * force;
          target.vx -= dx * force;
          target.vy -= dy * force;
        }

        // Apply velocity with damping
        for (const node of nodes) {
          if (isDragging.current && dragNode.current === node.id) {
            node.vx = 0;
            node.vy = 0;
            continue;
          }
          node.vx *= 0.9;
          node.vy *= 0.9;
          node.x += node.vx;
          node.y += node.vy;

          // Boundary constraints
          const r = getNodeRadius(node);
          node.x = Math.max(r, Math.min(dimensions.width - r, node.x));
          node.y = Math.max(r, Math.min(dimensions.height - r, node.y));
        }

        return nodes;
      });

      animationRef.current = requestAnimationFrame(simulate);
    };

    animationRef.current = requestAnimationFrame(simulate);
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [simNodes.length, edges, dimensions]);

  // Mouse handlers for dragging
  const handleMouseDown = (nodeId: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    isDragging.current = true;
    dragNode.current = nodeId;
  };

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isDragging.current || !dragNode.current || !svgRef.current) return;

      const svg = svgRef.current;
      const rect = svg.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      setSimNodes((prev) =>
        prev.map((n) =>
          n.id === dragNode.current ? { ...n, x, y, vx: 0, vy: 0 } : n
        )
      );
    },
    []
  );

  const handleMouseUp = useCallback(() => {
    isDragging.current = false;
    dragNode.current = null;
  }, []);

  const handleNodeClick = (nodeId: string) => {
    setSelectedNode(nodeId);
    onNodeClick?.(nodeId);
  };

  // Render node shape
  const renderNodeShape = (node: SimNode, isSelected: boolean, isHovered: boolean) => {
    const r = getNodeRadius(node);
    const strokeWidth = isSelected ? 4 : isHovered ? 3 : 2;
    const stroke = node.on_critical_path ? "#f97316" : isSelected ? "#1d4ed8" : "#374151";
    const fill = STATUS_COLORS[node.status] || "#9ca3af";
    const shape = TYPE_SHAPES[node.task_type as keyof typeof TYPE_SHAPES] || "rect";

    if (shape === "hexagon") {
      const points = Array.from({ length: 6 }, (_, i) => {
        const angle = (Math.PI / 3) * i - Math.PI / 2;
        return `${node.x + r * Math.cos(angle)},${node.y + r * Math.sin(angle)}`;
      }).join(" ");
      return (
        <polygon
          points={points}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
          style={{ cursor: "pointer", filter: isHovered ? "brightness(1.1)" : undefined }}
        />
      );
    }

    if (shape === "circle") {
      return (
        <circle
          cx={node.x}
          cy={node.y}
          r={r * 0.8}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
          style={{ cursor: "pointer", filter: isHovered ? "brightness(1.1)" : undefined }}
        />
      );
    }

    // Default: rectangle
    return (
      <rect
        x={node.x - r}
        y={node.y - r * 0.7}
        width={r * 2}
        height={r * 1.4}
        rx={4}
        fill={fill}
        stroke={stroke}
        strokeWidth={strokeWidth}
        style={{ cursor: "pointer", filter: isHovered ? "brightness(1.1)" : undefined }}
      />
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        Loading graph...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-red-500">
        <span>{error}</span>
        <button
          onClick={loadGraph}
          className="mt-2 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!graphData || simNodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        No tasks to display
      </div>
    );
  }

  const nodeMap = new Map(simNodes.map((n) => [n.id, n]));

  return (
    <div className="flex flex-col h-full">
      {/* Controls */}
      <div className="flex gap-4 p-3 bg-gray-50 border-b items-center flex-wrap">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeDone}
            onChange={(e) => setIncludeDone(e.target.checked)}
            className="rounded"
          />
          Show completed
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeSubtasks}
            onChange={(e) => setIncludeSubtasks(e.target.checked)}
            className="rounded"
          />
          Show subtasks
        </label>
        <div className="flex-1" />
        <div className="text-sm text-gray-500">
          {graphData.stats.total_nodes} nodes, {graphData.stats.total_edges} edges
        </div>
      </div>

      {/* Legend */}
      <div className="flex gap-4 p-2 bg-white border-b text-xs flex-wrap">
        <div className="flex items-center gap-2">
          <span className="font-medium">Status:</span>
          {Object.entries(STATUS_COLORS).slice(0, 5).map(([status, color]) => (
            <span key={status} className="flex items-center gap-1">
              <span
                className="w-3 h-3 rounded"
                style={{ backgroundColor: color }}
              />
              {status}
            </span>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="font-medium">Shape:</span>
          <span>⬡ Epic</span>
          <span>▭ Task</span>
          <span>● Subtask</span>
        </div>
        <div className="flex items-center gap-1">
          <span
            className="w-3 h-3 rounded border-2"
            style={{ borderColor: "#f97316" }}
          />
          <span>Critical path</span>
        </div>
      </div>

      {/* Graph */}
      <div className="flex-1 relative" style={{ minHeight: 400 }}>
        <svg
          ref={svgRef}
          width="100%"
          height="100%"
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          style={{ display: "block" }}
        >
          <defs>
            <marker
              id="arrowhead"
              markerWidth="10"
              markerHeight="7"
              refX="10"
              refY="3.5"
              orient="auto"
            >
              <polygon points="0 0, 10 3.5, 0 7" fill="#6b7280" />
            </marker>
          </defs>

          {/* Edges */}
          <g>
            {edges.map((edge, i) => {
              const source = nodeMap.get(edge.source);
              const target = nodeMap.get(edge.target);
              if (!source || !target) return null;

              // Calculate edge endpoint to stop at node boundary
              const dx = target.x - source.x;
              const dy = target.y - source.y;
              const dist = Math.sqrt(dx * dx + dy * dy) || 1;
              const sourceR = getNodeRadius(source);
              const targetR = getNodeRadius(target);

              const x1 = source.x + (dx / dist) * sourceR;
              const y1 = source.y + (dy / dist) * sourceR;
              const x2 = target.x - (dx / dist) * (targetR + 10);
              const y2 = target.y - (dy / dist) * (targetR + 10);

              const isHighlighted =
                selectedNode === edge.source || selectedNode === edge.target;

              return (
                <line
                  key={`${edge.source}-${edge.target}-${i}`}
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={isHighlighted ? "#3b82f6" : "#d1d5db"}
                  strokeWidth={isHighlighted ? 2 : 1}
                  markerEnd="url(#arrowhead)"
                />
              );
            })}
          </g>

          {/* Nodes */}
          <g>
            {simNodes.map((node) => {
              const isSelected = selectedNode === node.id;
              const isHovered = hoveredNode === node.id;
              const r = getNodeRadius(node);

              return (
                <g
                  key={node.id}
                  onMouseDown={handleMouseDown(node.id)}
                  onMouseEnter={() => setHoveredNode(node.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                  onClick={() => handleNodeClick(node.id)}
                >
                  {renderNodeShape(node, isSelected, isHovered)}
                  <text
                    x={node.x}
                    y={node.y + r + 14}
                    textAnchor="middle"
                    fontSize={10}
                    fill="#374151"
                    style={{ pointerEvents: "none" }}
                  >
                    {node.title.length > 15
                      ? node.title.slice(0, 15) + "..."
                      : node.title}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>

        {/* Tooltip */}
        {hoveredNode && (
          <div
            className="absolute bg-white border shadow-lg rounded p-3 text-sm pointer-events-none"
            style={{
              left: (nodeMap.get(hoveredNode)?.x ?? 0) + 20,
              top: (nodeMap.get(hoveredNode)?.y ?? 0) - 20,
              maxWidth: 250,
            }}
          >
            {(() => {
              const node = nodeMap.get(hoveredNode);
              if (!node) return null;
              return (
                <>
                  <div className="font-medium">{node.title}</div>
                  <div className="text-gray-500 text-xs mt-1">
                    <span className="capitalize">{node.task_type}</span> •{" "}
                    <span className="capitalize">{node.status}</span> •{" "}
                    {node.priority}
                  </div>
                  {node.on_critical_path && (
                    <div className="text-orange-600 text-xs mt-1">
                      ⚠ On critical path
                    </div>
                  )}
                  {node.pagerank_score > 0 && (
                    <div className="text-gray-400 text-xs">
                      PageRank: {node.pagerank_score.toFixed(3)}
                    </div>
                  )}
                </>
              );
            })()}
          </div>
        )}
      </div>
    </div>
  );
}
