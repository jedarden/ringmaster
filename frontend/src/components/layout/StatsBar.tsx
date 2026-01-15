import { useCardStore } from '../../store/cardStore';
import { useLoopStore } from '../../store/loopStore';
import { useProjects } from '../../hooks/useProjects';
import { formatCost } from '../../lib/utils';

export function StatsBar() {
  const cards = useCardStore((s) => s.cards);
  const activeLoopCount = useLoopStore((s) => s.getActiveLoopCount());
  const { data: projects } = useProjects();

  const totalCards = cards.size;
  const completedCards = Array.from(cards.values()).filter(
    (c) => c.state === 'completed'
  ).length;
  const totalCost = Array.from(cards.values()).reduce(
    (sum, c) => sum + c.totalCostUsd,
    0
  );

  return (
    <footer className="fixed bottom-0 left-0 right-0 bg-gray-800 border-t border-gray-700 px-6 py-3">
      <div className="flex items-center gap-8 text-sm">
        <StatItem label="Total Cards" value={totalCards} />
        <StatItem label="Completed" value={completedCards} className="text-green-400" />
        <StatItem
          label="Active Loops"
          value={activeLoopCount}
          className="text-purple-400"
        />
        <StatItem label="Projects" value={projects?.length ?? 0} />
        <StatItem label="Total Cost" value={formatCost(totalCost)} />
      </div>
    </footer>
  );
}

interface StatItemProps {
  label: string;
  value: string | number;
  className?: string;
}

function StatItem({ label, value, className }: StatItemProps) {
  return (
    <div>
      <span className="text-gray-400">{label}:</span>{' '}
      <span className={`font-medium ${className || ''}`}>{value}</span>
    </div>
  );
}
