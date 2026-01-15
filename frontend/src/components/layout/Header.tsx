import { Plus, Activity } from 'lucide-react';
import { Button } from '../ui/Button';
import { Select } from '../ui/Select';
import { useUIStore } from '../../store/uiStore';
import { useLoopStore } from '../../store/loopStore';
import { useProjects } from '../../hooks/useProjects';
import { formatCost } from '../../lib/utils';

export function Header() {
  const { selectedProjectId, setSelectedProject, setShowNewCardDialog } = useUIStore();
  const { data: projects } = useProjects();
  const activeLoopCount = useLoopStore((s) => s.getActiveLoopCount());
  const totalCost = useLoopStore((s) => s.getTotalCost());

  return (
    <header className="bg-gray-800 border-b border-gray-700 px-6 py-4">
      <div className="flex items-center justify-between">
        {/* Left side - Logo and project selector */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Activity className="h-6 w-6 text-purple-400" />
            <h1 className="text-2xl font-bold text-purple-400">Ringmaster</h1>
          </div>
          <span className="text-gray-500 text-sm">SDLC Orchestration</span>

          <Select
            className="w-48 ml-4"
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
        </div>

        {/* Right side - Stats and actions */}
        <div className="flex items-center gap-6">
          {/* Active loops indicator */}
          {activeLoopCount > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-purple-900/30 rounded-lg">
              <div className="h-2 w-2 rounded-full bg-purple-400 animate-pulse" />
              <span className="text-purple-300 text-sm">
                {activeLoopCount} active loop{activeLoopCount !== 1 ? 's' : ''}
              </span>
              {totalCost > 0 && (
                <span className="text-gray-400 text-sm">
                  ({formatCost(totalCost)})
                </span>
              )}
            </div>
          )}

          <Button onClick={() => setShowNewCardDialog(true)}>
            <Plus className="h-4 w-4 mr-1" />
            New Card
          </Button>
        </div>
      </div>
    </header>
  );
}
