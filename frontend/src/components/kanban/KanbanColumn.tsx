import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { DraggableCard } from './DraggableCard';
import { STATE_CONFIG } from './StateIndicator';
import { cn } from '../../lib/utils';
import type { Card, CardState } from '../../types';

interface KanbanColumnProps {
  id: CardState;
  title: string;
  cards: Card[];
  onCardClick?: (card: Card) => void;
}

export function KanbanColumn({ id, title, cards, onCardClick }: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id });
  const config = STATE_CONFIG[id];

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'flex flex-col w-72 min-w-72 bg-gray-800 rounded-lg',
        {
          'ring-2 ring-purple-500': isOver,
        }
      )}
    >
      {/* Column Header */}
      <div
        className={cn(
          'px-4 py-2 rounded-t-lg flex items-center justify-between',
          config.bgColor
        )}
      >
        <span className="font-medium">{title}</span>
        <span className="bg-white/20 px-2 py-0.5 rounded text-sm">
          {cards.length}
        </span>
      </div>

      {/* Cards */}
      <div className="p-2 space-y-2 min-h-[200px] flex-1 overflow-y-auto">
        <SortableContext
          items={cards.map((c) => c.id)}
          strategy={verticalListSortingStrategy}
        >
          {cards.map((card) => (
            <DraggableCard
              key={card.id}
              card={card}
              onClick={() => onCardClick?.(card)}
            />
          ))}
        </SortableContext>

        {cards.length === 0 && (
          <div className="text-gray-500 text-sm text-center py-8">
            No cards
          </div>
        )}
      </div>
    </div>
  );
}
