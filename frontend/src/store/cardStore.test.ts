import { describe, it, expect, beforeEach } from 'vitest'
import { useCardStore } from './cardStore'
import type { Card, CardState } from '../types'

// Helper to create mock card data with all required fields
function createMockCard(overrides: Partial<Card> & { id: string; title: string }): Card {
  return {
    projectId: 'project-1',
    description: '',
    taskPrompt: 'Test task prompt',
    state: 'draft',
    loopIteration: 0,
    errorCount: 0,
    totalCostUsd: 0,
    totalTokens: 0,
    labels: [],
    priority: 0,
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-01T00:00:00Z',
    ...overrides,
  }
}

// Mock card data for testing
const mockCards: Card[] = [
  createMockCard({
    id: '1',
    title: 'Test Card 1',
    description: 'Test description 1',
    state: 'draft',
    labels: ['frontend'],
    projectId: 'project-1',
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-01T00:00:00Z',
  }),
  createMockCard({
    id: '2',
    title: 'Test Card 2',
    description: 'Test description 2',
    state: 'planning',
    labels: ['backend', 'api'],
    projectId: 'project-1',
    createdAt: '2024-01-02T00:00:00Z',
    updatedAt: '2024-01-02T00:00:00Z',
  }),
  createMockCard({
    id: '3',
    title: 'Another Card',
    description: 'Different description',
    state: 'draft',
    labels: ['testing'],
    projectId: 'project-2',
    createdAt: '2024-01-03T00:00:00Z',
    updatedAt: '2024-01-03T00:00:00Z',
  }),
]

describe('cardStore', () => {
  beforeEach(() => {
    // Reset the store before each test
    useCardStore.getState().setCards([])
    useCardStore.getState().setSelectedCard(null)
    useCardStore.getState().setFilters({
      states: [],
      labels: [],
      search: '',
      projectId: null,
    })
  })

  describe('Basic CRUD operations', () => {
    it('should set cards correctly', () => {
      const store = useCardStore.getState()
      store.setCards(mockCards)

      // Must get fresh state after mutations
      const currentState = useCardStore.getState()
      expect(currentState.cards.size).toBe(3)
      expect(currentState.getCard('1')).toEqual(mockCards[0])
      expect(currentState.getCard('2')).toEqual(mockCards[1])
      expect(currentState.getCard('3')).toEqual(mockCards[2])
    })

    it('should add a new card', () => {
      const store = useCardStore.getState()
      const newCard = createMockCard({
        id: '4',
        title: 'New Card',
        description: 'New description',
        state: 'draft',
        labels: [],
        projectId: 'project-1',
        createdAt: '2024-01-04T00:00:00Z',
        updatedAt: '2024-01-04T00:00:00Z',
      })

      store.addCard(newCard)

      // Must get fresh state after mutations
      const currentState = useCardStore.getState()
      expect(currentState.cards.size).toBe(1)
      expect(currentState.getCard('4')).toEqual(newCard)
    })

    it('should update an existing card', () => {
      const store = useCardStore.getState()
      store.setCards([mockCards[0]])

      const updatedCard = { ...mockCards[0], title: 'Updated Title' }
      store.updateCard(updatedCard)

      expect(store.getCard('1')).toEqual(updatedCard)
      expect(store.getCard('1')?.title).toBe('Updated Title')
    })

    it('should remove a card', () => {
      const store = useCardStore.getState()
      store.setCards(mockCards)

      // Get fresh state and remove a card
      let currentState = useCardStore.getState()
      currentState.removeCard('2')

      // Must get fresh state after mutations
      currentState = useCardStore.getState()
      expect(currentState.cards.size).toBe(2)
      expect(currentState.getCard('2')).toBeUndefined()
      expect(currentState.getCard('1')).toBeDefined()
      expect(currentState.getCard('3')).toBeDefined()
    })
  })

  describe('Selection management', () => {
    it('should set and get selected card', () => {
      let currentState = useCardStore.getState()

      expect(currentState.selectedCardId).toBeNull()

      currentState.setSelectedCard('1')
      // Must get fresh state after mutations
      currentState = useCardStore.getState()
      expect(currentState.selectedCardId).toBe('1')

      currentState.setSelectedCard(null)
      // Must get fresh state after mutations
      currentState = useCardStore.getState()
      expect(currentState.selectedCardId).toBeNull()
    })
  })

  describe('State-based filtering', () => {
    beforeEach(() => {
      const store = useCardStore.getState()
      store.setCards(mockCards)
    })

    it('should get cards by state', () => {
      const store = useCardStore.getState()

      const draftCards = store.getCardsByState('draft')
      expect(draftCards).toHaveLength(2)
      expect(draftCards[0].id).toBe('1')
      expect(draftCards[1].id).toBe('3')

      const planningCards = store.getCardsByState('planning')
      expect(planningCards).toHaveLength(1)
      expect(planningCards[0].id).toBe('2')
    })

    it('should filter cards by project when getting cards by state', () => {
      const store = useCardStore.getState()
      store.setFilters({ projectId: 'project-1' })

      // Get fresh state after filter mutation
      const currentState = useCardStore.getState()
      const draftCards = currentState.getCardsByState('draft')
      expect(draftCards).toHaveLength(1)
      expect(draftCards[0].id).toBe('1')
    })
  })

  describe('Advanced filtering', () => {
    beforeEach(() => {
      const store = useCardStore.getState()
      store.setCards(mockCards)
    })

    it('should filter by multiple states', () => {
      const store = useCardStore.getState()
      store.setFilters({ states: ['draft', 'planning'] })

      // Get fresh state after filter mutation
      const currentState = useCardStore.getState()
      const filtered = currentState.getFilteredCards()
      expect(filtered).toHaveLength(3)
    })

    it('should filter by project ID', () => {
      const store = useCardStore.getState()
      store.setFilters({ projectId: 'project-1' })

      // Get fresh state after filter mutation
      const currentState = useCardStore.getState()
      const filtered = currentState.getFilteredCards()
      expect(filtered).toHaveLength(2)
      expect(filtered.map(c => c.id).sort()).toEqual(['1', '2'])
    })

    it('should filter by labels', () => {
      const store = useCardStore.getState()
      store.setFilters({ labels: ['backend'] })

      // Get fresh state after filter mutation
      const currentState = useCardStore.getState()
      const filtered = currentState.getFilteredCards()
      expect(filtered).toHaveLength(1)
      expect(filtered[0].id).toBe('2')
    })

    it('should filter by search text', () => {
      const store = useCardStore.getState()
      store.setFilters({ search: 'Another' })

      // Get fresh state after filter mutation
      const currentState = useCardStore.getState()
      const filtered = currentState.getFilteredCards()
      expect(filtered).toHaveLength(1)
      expect(filtered[0].id).toBe('3')
    })

    it('should filter by search in description', () => {
      const store = useCardStore.getState()
      store.setFilters({ search: 'Different' })

      // Get fresh state after filter mutation
      const currentState = useCardStore.getState()
      const filtered = currentState.getFilteredCards()
      expect(filtered).toHaveLength(1)
      expect(filtered[0].id).toBe('3')
    })

    it('should combine multiple filters', () => {
      const store = useCardStore.getState()
      store.setFilters({
        projectId: 'project-1',
        states: ['draft'],
        labels: ['frontend'],
      })

      // Get fresh state after filter mutation
      const currentState = useCardStore.getState()
      const filtered = currentState.getFilteredCards()
      expect(filtered).toHaveLength(1)
      expect(filtered[0].id).toBe('1')
    })

    it('should return no results for impossible filter combinations', () => {
      const store = useCardStore.getState()
      store.setFilters({
        projectId: 'project-1',
        labels: ['nonexistent'],
      })

      // Get fresh state after filter mutation
      const currentState = useCardStore.getState()
      const filtered = currentState.getFilteredCards()
      expect(filtered).toHaveLength(0)
    })
  })

  describe('Loading state', () => {
    it('should manage loading state', () => {
      let currentState = useCardStore.getState()

      expect(currentState.isLoading).toBe(false)

      currentState.setLoading(true)
      // Must get fresh state after mutations
      currentState = useCardStore.getState()
      expect(currentState.isLoading).toBe(true)

      currentState.setLoading(false)
      // Must get fresh state after mutations
      currentState = useCardStore.getState()
      expect(currentState.isLoading).toBe(false)
    })
  })
})