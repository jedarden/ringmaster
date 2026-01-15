import { useLoopStore } from '../../store/loopStore';
import { Progress } from '../ui/Progress';
import { Badge } from '../ui/Badge';
import { formatNumber, formatDuration, formatCost } from '../../lib/utils';

interface LoopStatusProps {
  cardId: string;
}

export function LoopStatus({ cardId }: LoopStatusProps) {
  const loopState = useLoopStore((s) => s.getLoopState(cardId));

  if (!loopState) {
    return (
      <div className="p-4 text-center text-gray-500">No active loop</div>
    );
  }

  const maxIterations = loopState.config.maxIterations;
  const maxCost = loopState.config.maxCostUsd;

  return (
    <div className="space-y-4">
      {/* Metrics */}
      <div className="grid grid-cols-3 gap-4">
        <MetricCard
          label="Iteration"
          value={`${loopState.iteration} / ${maxIterations}`}
          progress={(loopState.iteration / maxIterations) * 100}
        />
        <MetricCard
          label="Cost"
          value={formatCost(loopState.totalCostUsd)}
          progress={(loopState.totalCostUsd / maxCost) * 100}
          variant={loopState.totalCostUsd > maxCost * 0.8 ? 'warning' : 'default'}
        />
        <MetricCard
          label="Tokens"
          value={formatNumber(loopState.totalTokens)}
        />
      </div>

      {/* Status */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-400">Status</span>
        <StatusBadge status={loopState.status} />
      </div>

      {/* Elapsed Time */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-400">Elapsed Time</span>
        <span>{formatDuration(loopState.elapsedSeconds)}</span>
      </div>

      {/* Last Checkpoint */}
      {loopState.lastCheckpoint && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-400">Last Checkpoint</span>
          <span>Iteration {loopState.lastCheckpoint}</span>
        </div>
      )}

      {/* Consecutive Errors */}
      {loopState.consecutiveErrors > 0 && (
        <div className="flex items-center justify-between text-sm text-red-400">
          <span>Consecutive Errors</span>
          <span>
            {loopState.consecutiveErrors} / {loopState.config.maxConsecutiveErrors}
          </span>
        </div>
      )}
    </div>
  );
}

interface MetricCardProps {
  label: string;
  value: string;
  progress?: number;
  variant?: 'default' | 'warning';
}

function MetricCard({ label, value, progress, variant = 'default' }: MetricCardProps) {
  return (
    <div className="bg-gray-700/50 rounded-lg p-3">
      <div className="text-xs text-gray-400 mb-1">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
      {progress !== undefined && (
        <Progress
          value={progress}
          size="sm"
          variant={variant}
          className="mt-2"
        />
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, 'success' | 'warning' | 'destructive' | 'secondary'> = {
    running: 'success',
    paused: 'warning',
    completed: 'success',
    stopped: 'secondary',
    failed: 'destructive',
  };

  return (
    <Badge variant={variants[status] || 'secondary'}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </Badge>
  );
}
