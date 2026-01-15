import { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Header } from './components/layout/Header';
import { StatsBar } from './components/layout/StatsBar';
import { KanbanBoard } from './components/kanban/KanbanBoard';
import { NewCardDialog } from './components/cards/NewCardDialog';
import { CardDetailPanel } from './components/cards/CardDetailPanel';
import { Spinner } from './components/ui/Spinner';
import { useCards } from './hooks/useCards';
import { useAllLoops } from './hooks/useLoops';
import { useWebSocket } from './hooks/useWebSocket';
import { useUIStore } from './store/uiStore';
import { useCardStore } from './store/cardStore';
import type { Card } from './types';
import './index.css';

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function AppContent() {
  const [selectedCard, setSelectedCard] = useState<Card | null>(null);
  const { selectedProjectId } = useUIStore();
  const { isLoading: cardsLoading, error: cardsError } = useCards(selectedProjectId);
  const { isLoading: loopsLoading } = useAllLoops();
  const { isConnected } = useWebSocket();
  const cards = useCardStore((s) => s.cards);

  // Update selected card when it changes in the store
  useEffect(() => {
    if (selectedCard) {
      const updatedCard = cards.get(selectedCard.id);
      if (updatedCard) {
        setSelectedCard(updatedCard);
      }
    }
  }, [cards, selectedCard]);

  const handleCardClick = (card: Card) => {
    setSelectedCard(card);
  };

  const handleCloseDetail = () => {
    setSelectedCard(null);
  };

  if (cardsLoading || loopsLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="flex flex-col items-center gap-4">
          <Spinner size="lg" />
          <div className="text-white text-lg">Loading Ringmaster...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <Header />

      {/* Connection status */}
      {!isConnected && (
        <div className="bg-yellow-900/50 text-yellow-300 px-4 py-2 text-sm text-center">
          Connecting to server...
        </div>
      )}

      {/* Error state */}
      {cardsError && (
        <div className="bg-red-900/50 text-red-300 p-4 m-4 rounded-lg">
          Failed to load cards. Make sure the server is running on port 8080.
        </div>
      )}

      {/* Main content - Kanban Board */}
      <main className="pb-16 overflow-x-auto">
        <KanbanBoard onCardClick={handleCardClick} />
      </main>

      {/* Stats Bar */}
      <StatsBar />

      {/* Card Detail Panel */}
      {selectedCard && (
        <CardDetailPanel card={selectedCard} onClose={handleCloseDetail} />
      )}

      {/* New Card Dialog */}
      <NewCardDialog />
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
}

export default App;
