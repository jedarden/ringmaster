import { useState, useMemo } from 'react';
import { KanbanBoard } from '../components/kanban/KanbanBoard';
import { CardDetailPanel } from '../components/cards/CardDetailPanel';
import { NewCardDialog } from '../components/cards/NewCardDialog';
import { useCards } from '../hooks/useCards';
import { useAllLoops } from '../hooks/useLoops';
import { useUIStore } from '../store/uiStore';
import { useCardStore } from '../store/cardStore';
import { Spinner } from '../components/ui/Spinner';
import type { Card } from '../types';

export function KanbanPage() {
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const { selectedProjectId } = useUIStore();
  const { isLoading: cardsLoading, error: cardsError } = useCards(selectedProjectId);
  const { isLoading: loopsLoading } = useAllLoops();
  const cards = useCardStore((s) => s.cards);

  // Derive selected card from ID - automatically updates when card changes in store
  const selectedCard = useMemo(() => {
    return selectedCardId ? cards.get(selectedCardId) ?? null : null;
  }, [cards, selectedCardId]);

  const handleCardClick = (card: Card) => {
    setSelectedCardId(card.id);
  };

  const handleCloseDetail = () => {
    setSelectedCardId(null);
  };

  if (cardsLoading || loopsLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="h-full">
      {/* Error state */}
      {cardsError && (
        <div className="bg-red-900/50 text-red-300 p-4 m-4 rounded-lg">
          Failed to load cards. Make sure the server is running on port 8080.
        </div>
      )}

      {/* Kanban Board */}
      <div className="pb-4 overflow-x-auto">
        <KanbanBoard onCardClick={handleCardClick} />
      </div>

      {/* Card Detail Panel */}
      {selectedCard && (
        <CardDetailPanel card={selectedCard} onClose={handleCloseDetail} />
      )}

      {/* New Card Dialog */}
      <NewCardDialog />
    </div>
  );
}
