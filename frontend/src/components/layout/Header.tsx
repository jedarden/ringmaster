import { Link, useLocation } from 'react-router-dom';
import { Plus, Activity, LayoutDashboard, Columns3, FolderGit, Settings } from 'lucide-react';
import { Button } from '../ui/Button';
import { Select } from '../ui/Select';
import { useUIStore } from '../../store/uiStore';
import { useLoopStore } from '../../store/loopStore';
import { useProjects } from '../../hooks/useProjects';
import { formatCost } from '../../lib/utils';

interface NavLinkProps {
  to: string;
  icon: React.ReactNode;
  label: string;
}

function NavLink({ to, icon, label }: NavLinkProps) {
  const location = useLocation();
  const isActive = location.pathname === to;

  return (
    <Link
      to={to}
      className={`
        flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors
        ${isActive
          ? 'bg-purple-900/50 text-purple-300'
          : 'text-gray-400 hover:text-white hover:bg-gray-700'}
      `}
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </Link>
  );
}

export function Header() {
  const { selectedProjectId, setSelectedProject, setShowNewCardDialog } = useUIStore();
  const { projects } = useProjects();
  const activeLoopCount = useLoopStore((s) => s.getActiveLoopCount());
  const totalCost = useLoopStore((s) => s.getTotalCost());

  return (
    <header className="bg-gray-800 border-b border-gray-700 px-4 py-3">
      <div className="flex items-center justify-between">
        {/* Left side - Logo and navigation */}
        <div className="flex items-center gap-6">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2">
            <Activity className="h-6 w-6 text-purple-400" />
            <h1 className="text-xl font-bold text-purple-400 hidden md:block">Ringmaster</h1>
          </Link>

          {/* Navigation */}
          <nav className="flex items-center gap-1">
            <NavLink
              to="/dashboard"
              icon={<LayoutDashboard className="h-4 w-4" />}
              label="Dashboard"
            />
            <NavLink
              to="/kanban"
              icon={<Columns3 className="h-4 w-4" />}
              label="Kanban"
            />
            <NavLink
              to="/projects"
              icon={<FolderGit className="h-4 w-4" />}
              label="Projects"
            />
            <NavLink
              to="/settings"
              icon={<Settings className="h-4 w-4" />}
              label="Settings"
            />
          </nav>
        </div>

        {/* Right side - Project selector, stats, and actions */}
        <div className="flex items-center gap-4">
          {/* Project selector */}
          <Select
            className="w-36 md:w-48"
            value={selectedProjectId || ''}
            onChange={(e) => setSelectedProject(e.target.value || null)}
          >
            <option value="">All Projects</option>
            {projects?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>

          {/* Active loops indicator */}
          {activeLoopCount > 0 && (
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5 bg-purple-900/30 rounded-lg">
              <div className="h-2 w-2 rounded-full bg-purple-400 animate-pulse" />
              <span className="text-purple-300 text-sm">
                {activeLoopCount} loop{activeLoopCount !== 1 ? 's' : ''}
              </span>
              {totalCost > 0 && (
                <span className="text-gray-400 text-sm">
                  ({formatCost(totalCost)})
                </span>
              )}
            </div>
          )}

          <Button size="sm" onClick={() => setShowNewCardDialog(true)}>
            <Plus className="h-4 w-4 mr-1" />
            <span className="hidden sm:inline">New Card</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
