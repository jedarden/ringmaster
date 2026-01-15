import { useState } from 'react';
import {
  DndContext,
  DragOverlay,
  closestCenter,
  type DragStartEvent,
  type DragEndEvent,
} from '@dnd-kit/core';
import { KanbanColumn } from './KanbanColumn';
import { DraggableCard } from './DraggableCard';
import { KANBAN_COLUMNS } from './StateIndicator';
import { useCardStore } from '../../store/cardStore';
import { useTransitionCard, getTransitionTrigger } from '../../hooks/useCards';
import type { Card, CardState } from '../../types';

interface KanbanBoardProps {
  onCardClick?: (card: Card) => void;
}

export function KanbanBoard({ onCardClick }: KanbanBoardProps) {
  const [activeCard, setActiveCard] = useState<Card | null>(null);
  const getCardsByState = useCardStore((s) => s.getCardsByState);
  const transitionCard = useTransitionCard();

  const handleDragStart = (event: DragStartEvent) => {
    const card = event.active.data.current?.card as Card | undefined;
    setActiveCard(card || null);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveCard(null);

    const { active, over } = event;
    if (!over) return;

    const card = active.data.current?.card as Card | undefined;
    if (!card) return;

    const newState = over.id as CardState;
    if (card.state === newState) return;

    // Get the trigger for this transition
    const trigger = getTransitionTrigger(card.state, newState);
    if (trigger) {
      transitionCard.mutate({
        cardId: card.id,
        trigger,
      });
    }
  };

  const handleDragCancel = () => {
    setActiveCard(null);
  };

  return (
    <DndContext
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragCancel={handleDragCancel}
    >
      <div className="flex gap-4 overflow-x-auto p-4" style={{ minWidth: 'max-content' }}>
        {KANBAN_COLUMNS.map(({ state, title }) => (
          <KanbanColumn
            key={state}
            id={state}
            title={title}
            cards={getCardsByState(state)}
            onCardClick={onCardClick}
          />
        ))}
      </div>

      <DragOverlay>
        {activeCard && <DraggableCard card={activeCard} isDragging />}
      </DragOverlay>
    </DndContext>
  );
}
