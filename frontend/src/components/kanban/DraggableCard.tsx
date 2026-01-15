import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Badge } from '../ui/Badge';
import { LoopProgress } from '../loops/LoopProgress';
import { useLoopStore } from '../../store/loopStore';
import { formatCost, truncate } from '../../lib/utils';
import type { Card } from '../../types';
import { cn } from '../../lib/utils';

interface DraggableCardProps {
  card: Card;
  isDragging?: boolean;
  onClick?: () => void;
}

export function DraggableCard({ card, isDragging, onClick }: DraggableCardProps) {
  const loopState = useLoopStore((s) => s.getLoopState(card.id));

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({
    id: card.id,
    data: { card },
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const isLoopRunning = loopState?.status === 'running';

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={onClick}
      className={cn(
        'bg-gray-700 rounded-lg p-3 cursor-pointer border border-gray-600',
        'hover:bg-gray-650 hover:border-gray-500 transition-colors',
        {
          'opacity-50 shadow-lg rotate-2': isDragging,
          'ring-2 ring-purple-500 ring-opacity-50': isLoopRunning,
        }
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <h3 className="font-medium text-sm line-clamp-2">
          {card.title}
        </h3>
        {card.priority > 0 && (
          <Badge variant="warning" size="xs">
            P{card.priority}
          </Badge>
        )}
      </div>

      {/* Description */}
      {card.description && (
        <p className="text-gray-400 text-xs mt-1 line-clamp-2">
          {truncate(card.description, 80)}
        </p>
      )}

      {/* Loop Progress */}
      {loopState && isLoopRunning && (
        <div className="mt-2">
          <LoopProgress
            iteration={loopState.iteration}
            maxIterations={loopState.config.maxIterations}
            cost={loopState.totalCostUsd}
            maxCost={loopState.config.maxCostUsd}
          />
        </div>
      )}

      {/* Labels */}
      {card.labels.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {card.labels.slice(0, 3).map((label) => (
            <Badge key={label} variant="secondary" size="xs">
              {label}
            </Badge>
          ))}
          {card.labels.length > 3 && (
            <Badge variant="outline" size="xs">
              +{card.labels.length - 3}
            </Badge>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between mt-2 text-xs text-gray-500">
        <span>#{card.id.slice(0, 8)}</span>
        <div className="flex items-center gap-2">
          {card.loopIteration > 0 && !isLoopRunning && (
            <span className="text-purple-400">Loop #{card.loopIteration}</span>
          )}
          {card.totalCostUsd > 0 && (
            <span>{formatCost(card.totalCostUsd)}</span>
          )}
        </div>
      </div>
    </div>
  );
}
