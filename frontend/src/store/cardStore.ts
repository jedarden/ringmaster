import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import type { Card, CardState } from '../types';

interface CardFilters {
  states: CardState[];
  labels: string[];
  search: string;
  projectId: string | null;
}

interface CardStore {
  // State
  cards: Map<string, Card>;
  selectedCardId: string | null;
  filters: CardFilters;
  isLoading: boolean;

  // Actions
  setCards: (cards: Card[]) => void;
  addCard: (card: Card) => void;
  updateCard: (card: Card) => void;
  removeCard: (cardId: string) => void;
  setSelectedCard: (cardId: string | null) => void;
  setFilters: (filters: Partial<CardFilters>) => void;
  setLoading: (loading: boolean) => void;

  // Selectors
  getCardsByState: (state: CardState) => Card[];
  getFilteredCards: () => Card[];
  getCard: (id: string) => Card | undefined;
}

export const useCardStore = create<CardStore>()(
  devtools(
    (set, get) => ({
      cards: new Map(),
      selectedCardId: null,
      filters: {
        states: [],
        labels: [],
        search: '',
        projectId: null,
      },
      isLoading: false,

      setCards: (cards) =>
        set({
          cards: new Map(cards.map((c) => [c.id, c])),
        }),

      addCard: (card) =>
        set((state) => {
          const newCards = new Map(state.cards);
          newCards.set(card.id, card);
          return { cards: newCards };
        }),

      updateCard: (card) =>
        set((state) => {
          const newCards = new Map(state.cards);
          newCards.set(card.id, card);
          return { cards: newCards };
        }),

      removeCard: (cardId) =>
        set((state) => {
          const newCards = new Map(state.cards);
          newCards.delete(cardId);
          return { cards: newCards };
        }),

      setSelectedCard: (cardId) => set({ selectedCardId: cardId }),

      setFilters: (filters) =>
        set((state) => ({
          filters: { ...state.filters, ...filters },
        })),

      setLoading: (isLoading) => set({ isLoading }),

      getCardsByState: (state) => {
        const { cards, filters } = get();
        return Array.from(cards.values()).filter((card) => {
          if (card.state !== state) return false;
          if (filters.projectId && card.projectId !== filters.projectId)
            return false;
          return true;
        });
      },

      getFilteredCards: () => {
        const { cards, filters } = get();
        return Array.from(cards.values()).filter((card) => {
          if (filters.states.length && !filters.states.includes(card.state)) {
            return false;
          }
          if (filters.projectId && card.projectId !== filters.projectId) {
            return false;
          }
          if (
            filters.labels.length &&
            !filters.labels.some((l) => card.labels.includes(l))
          ) {
            return false;
          }
          if (filters.search) {
            const search = filters.search.toLowerCase();
            if (
              !card.title.toLowerCase().includes(search) &&
              !card.description?.toLowerCase().includes(search)
            ) {
              return false;
            }
          }
          return true;
        });
      },

      getCard: (id) => get().cards.get(id),
    }),
    { name: 'card-store' }
  )
);
