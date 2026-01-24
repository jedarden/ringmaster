import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '../../test/test-utils'
import { KanbanColumn } from './KanbanColumn'
import type { Card, CardState } from '../../types'

// Mock dnd-kit hooks
vi.mock('@dnd-kit/core', () => ({
  useDroppable: () => ({
    setNodeRef: vi.fn(),
    isOver: false,
  }),
}))

vi.mock('@dnd-kit/sortable', () => ({
  SortableContext: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  verticalListSortingStrategy: {},
  useSortable: () => ({
    attributes: {},
    listeners: {},
    setNodeRef: vi.fn(),
    transform: null,
    transition: null,
  }),
}))

// Helper to create mock card data
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

describe('KanbanColumn', () => {
  it('renders column title', () => {
    render(
      <KanbanColumn
        id="draft"
        title="Draft"
        cards={[]}
      />
    )

    expect(screen.getByText('Draft')).toBeInTheDocument()
  })

  it('displays card count', () => {
    const cards = [
      createMockCard({ id: '1', title: 'Card 1' }),
      createMockCard({ id: '2', title: 'Card 2' }),
      createMockCard({ id: '3', title: 'Card 3' }),
    ]

    render(
      <KanbanColumn
        id="draft"
        title="Draft"
        cards={cards}
      />
    )

    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('renders empty state when no cards', () => {
    render(
      <KanbanColumn
        id="draft"
        title="Draft"
        cards={[]}
      />
    )

    expect(screen.getByText('No cards')).toBeInTheDocument()
  })

  it('renders all cards in the column', () => {
    const cards = [
      createMockCard({ id: '1', title: 'First Card' }),
      createMockCard({ id: '2', title: 'Second Card' }),
    ]

    render(
      <KanbanColumn
        id="draft"
        title="Draft"
        cards={cards}
      />
    )

    expect(screen.getByText('First Card')).toBeInTheDocument()
    expect(screen.getByText('Second Card')).toBeInTheDocument()
  })

  it('calls onCardClick when a card is clicked', () => {
    const handleClick = vi.fn()
    const cards = [createMockCard({ id: '1', title: 'Clickable Card' })]

    render(
      <KanbanColumn
        id="draft"
        title="Draft"
        cards={cards}
        onCardClick={handleClick}
      />
    )

    // Click on the card
    screen.getByText('Clickable Card').closest('div')?.click()
    expect(handleClick).toHaveBeenCalledWith(cards[0])
  })

  it('renders different states with appropriate styling', () => {
    const states: CardState[] = ['draft', 'planning', 'coding', 'completed']

    for (const state of states) {
      const { unmount } = render(
        <KanbanColumn
          id={state}
          title={state.charAt(0).toUpperCase() + state.slice(1)}
          cards={[]}
        />
      )

      // Column should be rendered
      expect(screen.getByText('0')).toBeInTheDocument()
      unmount()
    }
  })
})
