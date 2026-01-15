import { Progress } from '../ui/Progress';
import { formatCost } from '../../lib/utils';

interface LoopProgressProps {
  iteration: number;
  maxIterations: number;
  cost: number;
  maxCost?: number;
}

export function LoopProgress({
  iteration,
  maxIterations,
  cost,
}: LoopProgressProps) {
  const iterationPercent = (iteration / maxIterations) * 100;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-purple-400">Loop {iteration}/{maxIterations}</span>
        <span className="text-gray-400">{formatCost(cost)}</span>
      </div>
      <Progress
        value={iterationPercent}
        size="sm"
        variant={iterationPercent > 80 ? 'warning' : 'default'}
      />
    </div>
  );
}
