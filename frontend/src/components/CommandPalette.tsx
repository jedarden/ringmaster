import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import type { Project, Worker } from "../types";
import { listProjects, listWorkers } from "../api/client";

interface Command {
  id: string;
  label: string;
  category: "navigation" | "project" | "worker" | "task" | "action";
  action: () => void;
  shortcut?: string;
}

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [commands, setCommands] = useState<Command[]>([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load dynamic commands (projects, workers, tasks)
  const loadDynamicCommands = useCallback(async () => {
    setLoading(true);
    try {
      const [projects, workers] = await Promise.all([
        listProjects(),
        listWorkers(),
      ]);

      const dynamicCommands: Command[] = [
        // Navigation commands
        {
          id: "nav-projects",
          label: "Go to Projects",
          category: "navigation",
          action: () => navigate("/"),
          shortcut: "g m",
        },
        {
          id: "nav-workers",
          label: "Go to Workers",
          category: "navigation",
          action: () => navigate("/workers"),
          shortcut: "g a",
        },
        {
          id: "nav-queue",
          label: "Go to Queue",
          category: "navigation",
          action: () => navigate("/queue"),
          shortcut: "g q",
        },
        {
          id: "nav-metrics",
          label: "Go to Metrics",
          category: "navigation",
          action: () => navigate("/metrics"),
          shortcut: "g d",
        },
        {
          id: "nav-logs",
          label: "Go to Logs",
          category: "navigation",
          action: () => navigate("/logs"),
          shortcut: "g l",
        },

        // Project commands
        ...projects.map((project: Project) => ({
          id: `project-${project.id}`,
          label: `Open project: ${project.name}`,
          category: "project" as const,
          action: () => navigate(`/projects/${project.id}`),
        })),
        ...projects.map((project: Project) => ({
          id: `graph-${project.id}`,
          label: `View graph: ${project.name}`,
          category: "project" as const,
          action: () => navigate(`/projects/${project.id}/graph`),
        })),

        // Worker commands
        ...workers.map((worker: Worker) => ({
          id: `worker-${worker.id}`,
          label: `View worker: ${worker.name}`,
          category: "worker" as const,
          action: () => navigate(`/workers?highlight=${worker.id}`),
        })),
      ];

      setCommands(dynamicCommands);
    } catch {
      // Use static commands if loading fails
      setCommands([
        {
          id: "nav-projects",
          label: "Go to Projects",
          category: "navigation",
          action: () => navigate("/"),
          shortcut: "g m",
        },
        {
          id: "nav-workers",
          label: "Go to Workers",
          category: "navigation",
          action: () => navigate("/workers"),
          shortcut: "g a",
        },
        {
          id: "nav-queue",
          label: "Go to Queue",
          category: "navigation",
          action: () => navigate("/queue"),
          shortcut: "g q",
        },
        {
          id: "nav-metrics",
          label: "Go to Metrics",
          category: "navigation",
          action: () => navigate("/metrics"),
          shortcut: "g d",
        },
        {
          id: "nav-logs",
          label: "Go to Logs",
          category: "navigation",
          action: () => navigate("/logs"),
          shortcut: "g l",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  // Load commands when opened
  useEffect(() => {
    if (isOpen) {
      loadDynamicCommands();
      setQuery("");
      setSelectedIndex(0);
      // Focus input after a short delay to ensure modal is rendered
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen, loadDynamicCommands]);

  // Filter commands based on query
  const filteredCommands = commands.filter(cmd =>
    cmd.label.toLowerCase().includes(query.toLowerCase())
  );

  // Group commands by category
  const groupedCommands = filteredCommands.reduce((acc, cmd) => {
    if (!acc[cmd.category]) acc[cmd.category] = [];
    acc[cmd.category].push(cmd);
    return acc;
  }, {} as Record<string, Command[]>);

  const categoryOrder: Command["category"][] = [
    "navigation",
    "project",
    "worker",
    "task",
    "action",
  ];

  const orderedGroups = categoryOrder
    .filter(cat => groupedCommands[cat]?.length)
    .map(cat => ({ category: cat, commands: groupedCommands[cat] }));

  // Flatten for keyboard navigation
  const flatCommands = orderedGroups.flatMap(g => g.commands);

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setSelectedIndex(prev =>
          prev < flatCommands.length - 1 ? prev + 1 : prev
        );
        break;
      case "ArrowUp":
        e.preventDefault();
        setSelectedIndex(prev => (prev > 0 ? prev - 1 : 0));
        break;
      case "Enter":
        e.preventDefault();
        if (flatCommands[selectedIndex]) {
          flatCommands[selectedIndex].action();
          onClose();
        }
        break;
      case "Escape":
        e.preventDefault();
        onClose();
        break;
    }
  }, [flatCommands, selectedIndex, onClose]);

  // Reset selection when query changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  if (!isOpen) return null;

  const categoryLabels: Record<Command["category"], string> = {
    navigation: "Navigation",
    project: "Projects",
    worker: "Workers",
    task: "Tasks",
    action: "Actions",
  };

  return (
    <div className="command-palette-overlay" onClick={onClose}>
      <div
        className="command-palette"
        onClick={e => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <div className="command-palette-header">
          <input
            ref={inputRef}
            type="text"
            placeholder="Type a command or search..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="command-palette-input"
          />
        </div>
        <div className="command-palette-body">
          {loading ? (
            <div className="command-palette-loading">Loading...</div>
          ) : flatCommands.length === 0 ? (
            <div className="command-palette-empty">No commands found</div>
          ) : (
            orderedGroups.map(group => (
              <div key={group.category} className="command-group">
                <div className="command-group-label">
                  {categoryLabels[group.category]}
                </div>
                {group.commands.map((cmd) => {
                  // Calculate flat index
                  const flatIdx = flatCommands.findIndex(c => c.id === cmd.id);
                  const isSelected = flatIdx === selectedIndex;

                  return (
                    <div
                      key={cmd.id}
                      className={`command-item ${isSelected ? "selected" : ""}`}
                      onClick={() => {
                        cmd.action();
                        onClose();
                      }}
                      onMouseEnter={() => setSelectedIndex(flatIdx)}
                    >
                      <span className="command-label">{cmd.label}</span>
                      {cmd.shortcut && (
                        <span className="command-shortcut">{cmd.shortcut}</span>
                      )}
                    </div>
                  );
                })}
              </div>
            ))
          )}
        </div>
        <div className="command-palette-footer">
          <span><kbd>↑↓</kbd> navigate</span>
          <span><kbd>↵</kbd> select</span>
          <span><kbd>esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}
