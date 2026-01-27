import { useEffect, useState, useCallback } from "react";
import { updateProject } from "../api/client";
import type { Project, ProjectUpdate } from "../types";

interface ProjectSettingsModalProps {
  project: Project;
  onClose: () => void;
  onSave?: (project: Project) => void;
}

export function ProjectSettingsModal({ project, onClose, onSave }: ProjectSettingsModalProps) {
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description || "");
  const [repoUrl, setRepoUrl] = useState(project.repo_url || "");
  const [techStack, setTechStack] = useState<string[]>(project.tech_stack || []);
  const [techInput, setTechInput] = useState("");

  // Settings fields
  const [workingDir, setWorkingDir] = useState(
    (project.settings?.working_dir as string) || ""
  );
  const [baseBranch, setBaseBranch] = useState(
    (project.settings?.base_branch as string) || "main"
  );

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const handleAddTech = useCallback(() => {
    const tech = techInput.trim();
    if (tech && !techStack.includes(tech)) {
      setTechStack([...techStack, tech]);
      setTechInput("");
    }
  }, [techInput, techStack]);

  const handleRemoveTech = useCallback((tech: string) => {
    setTechStack(techStack.filter((t) => t !== tech));
  }, [techStack]);

  const handleTechKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleAddTech();
      }
    },
    [handleAddTech]
  );

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);

      const updates: ProjectUpdate = {};

      // Only include changed fields
      if (name !== project.name) {
        updates.name = name;
      }
      if (description !== (project.description || "")) {
        updates.description = description || null;
      }
      if (repoUrl !== (project.repo_url || "")) {
        updates.repo_url = repoUrl || null;
      }
      if (JSON.stringify(techStack) !== JSON.stringify(project.tech_stack)) {
        updates.tech_stack = techStack;
      }

      // Check settings changes
      const settingsChanges: Record<string, string | null> = {};
      const currentWorkingDir = (project.settings?.working_dir as string) || "";
      const currentBaseBranch = (project.settings?.base_branch as string) || "main";

      if (workingDir !== currentWorkingDir) {
        settingsChanges.working_dir = workingDir || null;
      }
      if (baseBranch !== currentBaseBranch) {
        settingsChanges.base_branch = baseBranch || null;
      }

      if (Object.keys(settingsChanges).length > 0) {
        updates.settings = settingsChanges;
      }

      // Only make request if there are changes
      if (Object.keys(updates).length === 0) {
        onClose();
        return;
      }

      const updatedProject = await updateProject(project.id, updates);
      onSave?.(updatedProject);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Project Settings</h2>
          <button className="close-btn" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="modal-body">
          {error && <div className="error-message">{error}</div>}

          <div className="form-section">
            <h3>General</h3>

            <div className="form-group">
              <label htmlFor="name">Project Name</label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Project name"
              />
            </div>

            <div className="form-group">
              <label htmlFor="description">Description</label>
              <textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Project description"
                rows={3}
              />
            </div>

            <div className="form-group">
              <label htmlFor="repo-url">Repository URL</label>
              <input
                id="repo-url"
                type="text"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="/path/to/repo or https://github.com/org/repo"
              />
            </div>

            <div className="form-group">
              <label>Tech Stack</label>
              <div className="tech-input-row">
                <input
                  type="text"
                  value={techInput}
                  onChange={(e) => setTechInput(e.target.value)}
                  onKeyDown={handleTechKeyDown}
                  placeholder="Add technology (press Enter)"
                />
                <button
                  type="button"
                  onClick={handleAddTech}
                  disabled={!techInput.trim()}
                >
                  Add
                </button>
              </div>
              <div className="tech-tags">
                {techStack.map((tech) => (
                  <span key={tech} className="tech-tag">
                    {tech}
                    <button
                      type="button"
                      className="remove-tag"
                      onClick={() => handleRemoveTech(tech)}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="form-section">
            <h3>Advanced Settings</h3>

            <div className="form-group">
              <label htmlFor="working-dir">Working Directory</label>
              <input
                id="working-dir"
                type="text"
                value={workingDir}
                onChange={(e) => setWorkingDir(e.target.value)}
                placeholder="/path/to/working/directory"
              />
              <span className="form-hint">
                Override the project root directory for file operations
              </span>
            </div>

            <div className="form-group">
              <label htmlFor="base-branch">Base Branch</label>
              <input
                id="base-branch"
                type="text"
                value={baseBranch}
                onChange={(e) => setBaseBranch(e.target.value)}
                placeholder="main"
              />
              <span className="form-hint">
                Default git branch for worktrees (e.g., main, master, develop)
              </span>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button className="cancel-btn" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="save-btn" onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
