import { describe, it, expect, beforeEach } from 'vitest'
import { useLoopStore } from './loopStore'
import type { LoopState, LoopStatus } from '../types'

// Mock loop data for testing
const mockLoopState: LoopState = {
  cardId: 'card-1',
  status: 'running',
  iteration: 5,
  totalCostUsd: 2.50,
  totalTokens: 15000,
  startedAt: '2024-01-01T10:00:00Z',
  lastActive: '2024-01-01T10:30:00Z',
}

const mockLoopState2: LoopState = {
  cardId: 'card-2',
  status: 'paused',
  iteration: 2,
  totalCostUsd: 1.25,
  totalTokens: 7500,
  startedAt: '2024-01-01T09:00:00Z',
  lastActive: '2024-01-01T09:15:00Z',
}

const mockLoopState3: LoopState = {
  cardId: 'card-3',
  status: 'completed',
  iteration: 10,
  totalCostUsd: 5.75,
  totalTokens: 30000,
  startedAt: '2024-01-01T08:00:00Z',
  lastActive: '2024-01-01T08:45:00Z',
}

describe('loopStore', () => {
  beforeEach(() => {
    // Reset the store before each test
    useLoopStore.getState().clearAllLoops()
  })

  describe('Basic loop management', () => {
    it('should set and get loop state', () => {
      const store = useLoopStore.getState()

      expect(store.getLoopState('card-1')).toBeUndefined()

      store.setLoopState('card-1', mockLoopState)

      const retrievedState = store.getLoopState('card-1')
      expect(retrievedState).toEqual(mockLoopState)
    })

    it('should remove loop state when set to null', () => {
      const store = useLoopStore.getState()
      store.setLoopState('card-1', mockLoopState)

      expect(store.getLoopState('card-1')).toBeDefined()

      store.setLoopState('card-1', null)

      expect(store.getLoopState('card-1')).toBeUndefined()
    })

    it('should manage multiple loop states', () => {
      const store = useLoopStore.getState()
      store.setLoopState('card-1', mockLoopState)
      store.setLoopState('card-2', mockLoopState2)

      // Must get fresh state after mutations
      const currentState = useLoopStore.getState()
      expect(currentState.getLoopState('card-1')).toEqual(mockLoopState)
      expect(currentState.getLoopState('card-2')).toEqual(mockLoopState2)
      expect(currentState.activeLoops.size).toBe(2)
    })
  })

  describe('Loop iteration updates', () => {
    it('should update loop iteration data', () => {
      const store = useLoopStore.getState()
      store.setLoopState('card-1', mockLoopState)

      store.updateLoopIteration('card-1', 7, 3.50, 18000)

      const updatedState = store.getLoopState('card-1')
      expect(updatedState).toEqual({
        ...mockLoopState,
        iteration: 7,
        totalCostUsd: 3.50,
        totalTokens: 18000,
      })
    })

    it('should not update non-existent loop iteration', () => {
      const store = useLoopStore.getState()

      store.updateLoopIteration('nonexistent', 7, 3.50, 18000)

      // Must get fresh state after mutations
      const currentState = useLoopStore.getState()
      expect(currentState.getLoopState('nonexistent')).toBeUndefined()
      expect(currentState.activeLoops.size).toBe(0)
    })
  })

  describe('Loop status updates', () => {
    it('should update loop status', () => {
      const store = useLoopStore.getState()
      store.setLoopState('card-1', mockLoopState)

      store.updateLoopStatus('card-1', 'paused')

      const updatedState = store.getLoopState('card-1')
      expect(updatedState?.status).toBe('paused')
    })

    it('should not update non-existent loop status', () => {
      const store = useLoopStore.getState()

      store.updateLoopStatus('nonexistent', 'paused')

      expect(store.getLoopState('nonexistent')).toBeUndefined()
    })
  })

  describe('Bulk operations', () => {
    it('should set all loops from array', () => {
      const store = useLoopStore.getState()
      const loopData = [
        { cardId: 'card-1', state: mockLoopState },
        { cardId: 'card-2', state: mockLoopState2 },
      ]

      store.setAllLoops(loopData)

      // Must get fresh state after mutations
      const currentState = useLoopStore.getState()
      expect(currentState.activeLoops.size).toBe(2)
      expect(currentState.getLoopState('card-1')).toEqual(mockLoopState)
      expect(currentState.getLoopState('card-2')).toEqual(mockLoopState2)
    })

    it('should clear all loops', () => {
      const store = useLoopStore.getState()
      store.setLoopState('card-1', mockLoopState)
      store.setLoopState('card-2', mockLoopState2)

      // Must get fresh state after mutations
      let currentState = useLoopStore.getState()
      expect(currentState.activeLoops.size).toBe(2)

      currentState.clearAllLoops()

      // Get fresh state again after clearAllLoops
      currentState = useLoopStore.getState()
      expect(currentState.activeLoops.size).toBe(0)
      expect(currentState.getLoopState('card-1')).toBeUndefined()
      expect(currentState.getLoopState('card-2')).toBeUndefined()
    })
  })

  describe('Analytics and selectors', () => {
    beforeEach(() => {
      const store = useLoopStore.getState()
      store.setLoopState('card-1', mockLoopState) // running
      store.setLoopState('card-2', mockLoopState2) // paused
      store.setLoopState('card-3', mockLoopState3) // completed
    })

    it('should get active loop count (running + paused)', () => {
      const store = useLoopStore.getState()
      const activeCount = store.getActiveLoopCount()

      expect(activeCount).toBe(2) // running + paused, not completed
    })

    it('should get only running loops', () => {
      const store = useLoopStore.getState()
      const runningLoops = store.getRunningLoops()

      expect(runningLoops).toHaveLength(1)
      expect(runningLoops[0]).toEqual(mockLoopState)
    })

    it('should calculate total cost', () => {
      const store = useLoopStore.getState()
      const totalCost = store.getTotalCost()

      // 2.50 + 1.25 + 5.75 = 9.50
      expect(totalCost).toBe(9.50)
    })

    it('should handle empty loops for analytics', () => {
      const store = useLoopStore.getState()
      store.clearAllLoops()

      // Must get fresh state after mutations
      const currentState = useLoopStore.getState()
      expect(currentState.getActiveLoopCount()).toBe(0)
      expect(currentState.getRunningLoops()).toHaveLength(0)
      expect(currentState.getTotalCost()).toBe(0)
    })
  })

  describe('Edge cases', () => {
    it('should handle updating iteration for removed loop', () => {
      const store = useLoopStore.getState()
      store.setLoopState('card-1', mockLoopState)
      store.setLoopState('card-1', null) // Remove it

      store.updateLoopIteration('card-1', 10, 5.00, 25000)

      // Must get fresh state after mutations
      const currentState = useLoopStore.getState()
      expect(currentState.getLoopState('card-1')).toBeUndefined()
    })

    it('should handle updating status for removed loop', () => {
      const store = useLoopStore.getState()
      store.setLoopState('card-1', mockLoopState)
      store.setLoopState('card-1', null) // Remove it

      store.updateLoopStatus('card-1', 'completed')

      // Must get fresh state after mutations
      const currentState = useLoopStore.getState()
      expect(currentState.getLoopState('card-1')).toBeUndefined()
    })
  })
})