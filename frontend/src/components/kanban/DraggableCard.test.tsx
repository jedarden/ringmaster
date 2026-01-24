import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '../../test/test-utils'
import { DraggableCard } from './DraggableCard'
import { useLoopStore } from '../../store/loopStore'
import type { Card } from '../../types'

// Mock dnd-kit hooks
vi.mock('@dnd-kit/sortable', () => ({
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

describe('DraggableCard', () => {
  beforeEach(() => {
    // Reset loop store before each test
    useLoopStore.getState().clearAllLoops()
  })

  it('renders card title', () => {
    const card = createMockCard({
      id: '1',
      title: 'Test Card Title',
    })

    render(<DraggableCard card={card} />)

    expect(screen.getByText('Test Card Title')).toBeInTheDocument()
  })

  it('renders card description when provided', () => {
    const card = createMockCard({
      id: '1',
      title: 'Test Card',
      description: 'This is a test description',
    })

    render(<DraggableCard card={card} />)

    expect(screen.getByText('This is a test description')).toBeInTheDocument()
  })

  it('renders priority badge when priority is set', () => {
    const card = createMockCard({
      id: '1',
      title: 'Test Card',
      priority: 1,
    })

    render(<DraggableCard card={card} />)

    expect(screen.getByText('P1')).toBeInTheDocument()
  })

  it('does not render priority badge when priority is 0', () => {
    const card = createMockCard({
      id: '1',
      title: 'Test Card',
      priority: 0,
    })

    render(<DraggableCard card={card} />)

    expect(screen.queryByText(/^P\d$/)).not.toBeInTheDocument()
  })

  it('renders labels when provided', () => {
    const card = createMockCard({
      id: '1',
      title: 'Test Card',
      labels: ['frontend', 'bug'],
    })

    render(<DraggableCard card={card} />)

    expect(screen.getByText('frontend')).toBeInTheDocument()
    expect(screen.getByText('bug')).toBeInTheDocument()
  })

  it('truncates labels when more than 3', () => {
    const card = createMockCard({
      id: '1',
      title: 'Test Card',
      labels: ['one', 'two', 'three', 'four', 'five'],
    })

    render(<DraggableCard card={card} />)

    expect(screen.getByText('one')).toBeInTheDocument()
    expect(screen.getByText('two')).toBeInTheDocument()
    expect(screen.getByText('three')).toBeInTheDocument()
    expect(screen.getByText('+2')).toBeInTheDocument()
    expect(screen.queryByText('four')).not.toBeInTheDocument()
  })

  it('displays card ID in footer', () => {
    const card = createMockCard({
      id: 'abc12345-longer-id',
      title: 'Test Card',
    })

    render(<DraggableCard card={card} />)

    // Card ID is truncated to first 8 chars with # prefix
    expect(screen.getByText('#abc12345')).toBeInTheDocument()
  })

  it('displays loop iteration when card has completed loops', () => {
    const card = createMockCard({
      id: '1',
      title: 'Test Card',
      loopIteration: 5,
    })

    render(<DraggableCard card={card} />)

    expect(screen.getByText('Loop #5')).toBeInTheDocument()
  })

  it('displays total cost when card has cost', () => {
    const card = createMockCard({
      id: '1',
      title: 'Test Card',
      totalCostUsd: 2.50,
    })

    render(<DraggableCard card={card} />)

    expect(screen.getByText('$2.50')).toBeInTheDocument()
  })

  it('calls onClick handler when clicked', () => {
    const card = createMockCard({
      id: '1',
      title: 'Test Card',
    })
    const handleClick = vi.fn()

    render(<DraggableCard card={card} onClick={handleClick} />)

    screen.getByText('Test Card').closest('div')?.click()
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('applies dragging styles when isDragging is true', () => {
    const card = createMockCard({
      id: '1',
      title: 'Test Card',
    })

    const { container } = render(<DraggableCard card={card} isDragging />)

    // Check for opacity class that indicates dragging state
    const cardElement = container.firstChild as HTMLElement
    expect(cardElement.className).toContain('opacity-50')
  })
})
