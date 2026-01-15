import { useState } from 'react';
import { useProjects } from '../hooks/useProjects';
import { useUIStore } from '../store/uiStore';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Textarea } from '../components/ui/Textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/Dialog';
import { Spinner } from '../components/ui/Spinner';
import { FolderGit, Plus, ExternalLink, Settings, Trash2 } from 'lucide-react';
import type { Project } from '../types';

interface ProjectFormData {
  name: string;
  repositoryUrl: string;
  repositoryPath: string;
  description: string;
  techStack: string;
  codingConventions: string;
}

function NewProjectDialog({ open, onClose, onSubmit }: {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: ProjectFormData) => void;
}) {
  const [formData, setFormData] = useState<ProjectFormData>({
    name: '',
    repositoryUrl: '',
    repositoryPath: '',
    description: '',
    techStack: '',
    codingConventions: '',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(formData);
    setFormData({
      name: '',
      repositoryUrl: '',
      repositoryPath: '',
      description: '',
      techStack: '',
      codingConventions: '',
    });
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Create New Project</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Project Name *</label>
            <Input
              value={formData.name}
              onChange={(e) => setFormData(d => ({ ...d, name: e.target.value }))}
              placeholder="My Project"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Repository URL *</label>
            <Input
              value={formData.repositoryUrl}
              onChange={(e) => setFormData(d => ({ ...d, repositoryUrl: e.target.value }))}
              placeholder="https://github.com/org/repo"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Local Repository Path</label>
            <Input
              value={formData.repositoryPath}
              onChange={(e) => setFormData(d => ({ ...d, repositoryPath: e.target.value }))}
              placeholder="/path/to/repo"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Description</label>
            <Textarea
              value={formData.description}
              onChange={(e) => setFormData(d => ({ ...d, description: e.target.value }))}
              placeholder="What does this project do?"
              rows={3}
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Tech Stack</label>
            <Input
              value={formData.techStack}
              onChange={(e) => setFormData(d => ({ ...d, techStack: e.target.value }))}
              placeholder="React, TypeScript, Node.js"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Coding Conventions</label>
            <Textarea
              value={formData.codingConventions}
              onChange={(e) => setFormData(d => ({ ...d, codingConventions: e.target.value }))}
              placeholder="ESLint, Prettier, no any types..."
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit">Create Project</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

interface ProjectCardProps {
  project: Project;
  isSelected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

function ProjectCard({ project, isSelected, onSelect, onDelete }: ProjectCardProps) {
  return (
    <div
      className={`
        bg-gray-800 rounded-lg border p-6 cursor-pointer transition-all
        ${isSelected ? 'border-blue-500 ring-2 ring-blue-500/50' : 'border-gray-700 hover:border-gray-600'}
      `}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <FolderGit className="w-8 h-8 text-blue-400" />
          <div>
            <h3 className="font-semibold text-lg">{project.name}</h3>
            <p className="text-sm text-gray-400">{project.repositoryUrl}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={project.repositoryUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-gray-700"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="p-2 text-gray-400 hover:text-red-400 rounded-lg hover:bg-gray-700"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {project.description && (
        <p className="mt-4 text-gray-300 text-sm">{project.description}</p>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {project.techStack?.map((tech) => (
          <span
            key={tech}
            className="px-2 py-1 text-xs bg-gray-700 rounded-full text-gray-300"
          >
            {tech}
          </span>
        ))}
      </div>

      {isSelected && (
        <div className="mt-4 pt-4 border-t border-gray-700">
          <p className="text-xs text-blue-400 flex items-center gap-1">
            <Settings className="w-3 h-3" />
            Currently selected project
          </p>
        </div>
      )}
    </div>
  );
}

export function ProjectsPage() {
  const [isNewProjectOpen, setIsNewProjectOpen] = useState(false);
  const { projects, isLoading, createProject, deleteProject } = useProjects();
  const { selectedProjectId, setSelectedProjectId } = useUIStore();

  const handleCreateProject = async (data: ProjectFormData) => {
    await createProject({
      name: data.name,
      repositoryUrl: data.repositoryUrl,
      repositoryPath: data.repositoryPath || undefined,
      description: data.description || undefined,
      techStack: data.techStack ? data.techStack.split(',').map(s => s.trim()) : undefined,
      codingConventions: data.codingConventions || undefined,
    });
    setIsNewProjectOpen(false);
  };

  const handleDeleteProject = async (projectId: string) => {
    if (confirm('Are you sure you want to delete this project? This will not delete any cards.')) {
      await deleteProject(projectId);
      if (selectedProjectId === projectId) {
        setSelectedProjectId(null);
      }
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Projects</h1>
        <Button onClick={() => setIsNewProjectOpen(true)}>
          <Plus className="w-4 h-4 mr-2" />
          New Project
        </Button>
      </div>

      {projects.length === 0 ? (
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-12 text-center">
          <FolderGit className="w-16 h-16 mx-auto text-gray-600 mb-4" />
          <h3 className="text-lg font-semibold mb-2">No projects yet</h3>
          <p className="text-gray-400 mb-4">
            Create your first project to start organizing your coding tasks.
          </p>
          <Button onClick={() => setIsNewProjectOpen(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Create Project
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* All Projects Option */}
          <div
            className={`
              bg-gray-800 rounded-lg border p-6 cursor-pointer transition-all
              ${selectedProjectId === null ? 'border-blue-500 ring-2 ring-blue-500/50' : 'border-gray-700 hover:border-gray-600'}
            `}
            onClick={() => setSelectedProjectId(null)}
          >
            <div className="flex items-center gap-3">
              <FolderGit className="w-8 h-8 text-gray-400" />
              <div>
                <h3 className="font-semibold text-lg">All Projects</h3>
                <p className="text-sm text-gray-400">View cards from all projects</p>
              </div>
            </div>
          </div>

          {/* Project Cards */}
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              isSelected={selectedProjectId === project.id}
              onSelect={() => setSelectedProjectId(project.id)}
              onDelete={() => handleDeleteProject(project.id)}
            />
          ))}
        </div>
      )}

      <NewProjectDialog
        open={isNewProjectOpen}
        onClose={() => setIsNewProjectOpen(false)}
        onSubmit={handleCreateProject}
      />
    </div>
  );
}
