import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import type { LoopState, LoopStatus } from '../types';

interface LoopStore {
  // State
  activeLoops: Map<string, LoopState>;

  // Actions
  setLoopState: (cardId: string, state: LoopState | null) => void;
  updateLoopIteration: (
    cardId: string,
    iteration: number,
    cost: number,
    tokens: number
  ) => void;
  updateLoopStatus: (cardId: string, status: LoopStatus) => void;
  clearAllLoops: () => void;
  setAllLoops: (loops: Array<{ cardId: string; state: Partial<LoopState> }>) => void;

  // Selectors
  getLoopState: (cardId: string) => LoopState | undefined;
  getActiveLoopCount: () => number;
  getRunningLoops: () => LoopState[];
  getTotalCost: () => number;
}

export const useLoopStore = create<LoopStore>()(
  devtools(
    (set, get) => ({
      activeLoops: new Map(),

      setLoopState: (cardId, state) =>
        set((s) => {
          const newLoops = new Map(s.activeLoops);
          if (state) {
            newLoops.set(cardId, state);
          } else {
            newLoops.delete(cardId);
          }
          return { activeLoops: newLoops };
        }),

      updateLoopIteration: (cardId, iteration, cost, tokens) =>
        set((s) => {
          const loop = s.activeLoops.get(cardId);
          if (loop) {
            const newLoops = new Map(s.activeLoops);
            newLoops.set(cardId, {
              ...loop,
              iteration,
              totalCostUsd: cost,
              totalTokens: tokens,
            });
            return { activeLoops: newLoops };
          }
          return s;
        }),

      updateLoopStatus: (cardId, status) =>
        set((s) => {
          const loop = s.activeLoops.get(cardId);
          if (loop) {
            const newLoops = new Map(s.activeLoops);
            newLoops.set(cardId, { ...loop, status });
            return { activeLoops: newLoops };
          }
          return s;
        }),

      clearAllLoops: () => set({ activeLoops: new Map() }),

      setAllLoops: (loops) =>
        set(() => {
          const newLoops = new Map<string, LoopState>();
          loops.forEach(({ cardId, state }) => {
            newLoops.set(cardId, state as LoopState);
          });
          return { activeLoops: newLoops };
        }),

      getLoopState: (cardId) => get().activeLoops.get(cardId),

      getActiveLoopCount: () => {
        return Array.from(get().activeLoops.values()).filter(
          (l) => l.status === 'running' || l.status === 'paused'
        ).length;
      },

      getRunningLoops: () => {
        return Array.from(get().activeLoops.values()).filter(
          (l) => l.status === 'running'
        );
      },

      getTotalCost: () => {
        return Array.from(get().activeLoops.values()).reduce(
          (sum, l) => sum + l.totalCostUsd,
          0
        );
      },
    }),
    { name: 'loop-store' }
  )
);
