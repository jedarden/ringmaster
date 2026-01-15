# Frontend Architecture

## Overview

The Ringmaster frontend is a React + TypeScript single-page application built with Vite. It provides a Kanban-style interface for managing SDLC cards, with real-time updates via WebSocket, loop monitoring, and integration status displays.

## Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.2+ | UI framework |
| TypeScript | 5.3+ | Type safety |
| Vite | 5.0+ | Build tool |
| Tailwind CSS | 3.4+ | Styling |
| Zustand | 4.4+ | State management |
| TanStack Query | 5.0+ | Server state/caching |
| React Router | 6.20+ | Routing |
| dnd-kit | 6.0+ | Drag and drop |
| Recharts | 2.10+ | Charts |
| Lucide React | 0.300+ | Icons |

## Component Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND COMPONENT TREE                                     │
└──────────────────────────────────────────────────────────────────────────────────────┘

App
├── Providers
│   ├── QueryClientProvider (TanStack Query)
│   ├── RouterProvider (React Router)
│   └── WebSocketProvider (custom)
│
├── Layout
│   ├── Header
│   │   ├── Logo
│   │   ├── ProjectSelector
│   │   ├── GlobalSearch
│   │   └── UserMenu
│   │
│   ├── Sidebar
│   │   ├── Navigation
│   │   │   ├── NavItem (Dashboard)
│   │   │   ├── NavItem (Kanban)
│   │   │   ├── NavItem (Projects)
│   │   │   └── NavItem (Settings)
│   │   ├── ActiveLoops
│   │   │   └── LoopIndicator[]
│   │   └── QuickActions
│   │
│   └── MainContent
│       └── <Outlet /> (React Router)
│
├── Pages
│   ├── DashboardPage
│   │   ├── StatsCards
│   │   │   ├── StatCard (Total Cards)
│   │   │   ├── StatCard (Active Loops)
│   │   │   ├── StatCard (Today's Cost)
│   │   │   └── StatCard (Success Rate)
│   │   ├── CardsByStateChart
│   │   ├── CostTrendChart
│   │   ├── ActiveLoopsPanel
│   │   │   └── LoopCard[]
│   │   └── RecentActivity
│   │       └── ActivityItem[]
│   │
│   ├── KanbanPage
│   │   ├── KanbanToolbar
│   │   │   ├── ViewToggle (Board/List)
│   │   │   ├── FilterDropdown
│   │   │   ├── SortDropdown
│   │   │   └── NewCardButton
│   │   ├── KanbanBoard (DndContext)
│   │   │   └── KanbanColumn[]
│   │   │       ├── ColumnHeader
│   │   │       │   ├── ColumnTitle
│   │   │       │   └── CardCount
│   │   │       └── DroppableArea
│   │   │           └── DraggableCard[]
│   │   │               ├── CardHeader
│   │   │               │   ├── CardTitle
│   │   │               │   └── PriorityBadge
│   │   │               ├── CardLabels
│   │   │               ├── LoopProgress (if active)
│   │   │               └── CardFooter
│   │   │                   ├── DueDate
│   │   │                   └── QuickActions
│   │   └── CardDrawer (Sheet)
│   │       └── CardDetailPanel
│   │
│   ├── CardDetailPage
│   │   ├── CardHeader
│   │   │   ├── BackButton
│   │   │   ├── TitleEditor (inline)
│   │   │   ├── StateIndicator
│   │   │   └── ActionButtons
│   │   │       ├── StartLoop
│   │   │       ├── PauseLoop
│   │   │       └── Archive
│   │   ├── CardTabs
│   │   │   ├── Tab: Overview
│   │   │   │   ├── DescriptionEditor
│   │   │   │   ├── AcceptanceCriteria
│   │   │   │   │   └── CriteriaItem[]
│   │   │   │   ├── DependenciesList
│   │   │   │   └── MetadataPanel
│   │   │   │       ├── Labels
│   │   │   │       ├── Priority
│   │   │   │       └── Deadline
│   │   │   │
│   │   │   ├── Tab: Loop
│   │   │   │   ├── LoopStatus
│   │   │   │   │   ├── IterationCounter
│   │   │   │   │   ├── CostMeter
│   │   │   │   │   └── TimeMeter
│   │   │   │   ├── LoopControls
│   │   │   │   │   ├── StartButton
│   │   │   │   │   ├── PauseButton
│   │   │   │   │   └── StopButton
│   │   │   │   ├── LoopConfig (expandable)
│   │   │   │   └── IterationTimeline
│   │   │   │       └── IterationItem[]
│   │   │   │
│   │   │   ├── Tab: Attempts
│   │   │   │   ├── AttemptList
│   │   │   │   │   └── AttemptItem[]
│   │   │   │   └── AttemptDetail (expandable)
│   │   │   │       ├── OutputViewer
│   │   │   │       ├── DiffViewer
│   │   │   │       └── MetricsDisplay
│   │   │   │
│   │   │   ├── Tab: Errors
│   │   │   │   ├── ErrorList
│   │   │   │   │   └── ErrorItem[]
│   │   │   │   └── ErrorDetail (expandable)
│   │   │   │       ├── ErrorMessage
│   │   │   │       ├── StackTrace
│   │   │   │       └── ContextViewer
│   │   │   │
│   │   │   ├── Tab: Deploy
│   │   │   │   ├── BuildStatus
│   │   │   │   │   ├── WorkflowRun
│   │   │   │   │   └── BuildLogs
│   │   │   │   ├── DeployStatus
│   │   │   │   │   ├── ArgoCDStatus
│   │   │   │   │   └── K8sStatus
│   │   │   │   └── DeployHistory
│   │   │   │       └── DeploymentItem[]
│   │   │   │
│   │   │   └── Tab: Logs
│   │   │       └── LogViewer
│   │   │           ├── LogFilters
│   │   │           └── LogStream
│   │   │
│   │   └── CardTimeline (right sidebar)
│   │       └── TimelineEvent[]
│   │
│   ├── ProjectsPage
│   │   ├── ProjectList
│   │   │   └── ProjectCard[]
│   │   └── NewProjectDialog
│   │
│   └── SettingsPage
│       ├── GeneralSettings
│       ├── IntegrationSettings
│       │   ├── GitHubConfig
│       │   ├── ArgoCDConfig
│       │   └── ClaudeAPIConfig
│       └── LoopDefaults
│
└── Shared Components
    ├── UI (primitives)
    │   ├── Button
    │   ├── Input
    │   ├── Select
    │   ├── Textarea
    │   ├── Badge
    │   ├── Card
    │   ├── Dialog
    │   ├── Sheet (slide-over)
    │   ├── Tabs
    │   ├── Tooltip
    │   ├── Dropdown
    │   ├── Progress
    │   └── Spinner
    │
    ├── Domain Components
    │   ├── StateIndicator
    │   ├── LoopProgress
    │   ├── CostDisplay
    │   ├── DiffViewer
    │   ├── LogViewer
    │   ├── MarkdownEditor
    │   └── CodeEditor
    │
    └── Hooks
        ├── useWebSocket
        ├── useCards
        ├── useLoop
        ├── useAttempts
        └── useIntegrations
```

## State Management (Zustand)

```typescript
// File: src/store/index.ts

// Re-export all stores
export { useCardStore } from './cardStore';
export { useLoopStore } from './loopStore';
export { useUIStore } from './uiStore';
export { useWebSocketStore } from './webSocketStore';

// File: src/store/cardStore.ts

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

export interface Card {
  id: string;
  projectId: string;
  title: string;
  description?: string;
  state: CardState;
  loopIteration: number;
  totalCostUsd: number;
  labels: string[];
  priority: number;
  createdAt: string;
  updatedAt: string;
}

export type CardState =
  | 'draft' | 'planning' | 'coding' | 'code_review' | 'testing'
  | 'build_queue' | 'building' | 'build_success' | 'build_failed'
  | 'deploy_queue' | 'deploying' | 'verifying'
  | 'completed' | 'error_fixing' | 'archived' | 'failed';

interface CardStore {
  // State
  cards: Map<string, Card>;
  selectedCardId: string | null;
  filters: {
    states: CardState[];
    labels: string[];
    search: string;
  };

  // Actions
  setCards: (cards: Card[]) => void;
  addCard: (card: Card) => void;
  updateCard: (card: Card) => void;
  removeCard: (cardId: string) => void;
  setSelectedCard: (cardId: string | null) => void;
  setFilters: (filters: Partial<CardStore['filters']>) => void;

  // Selectors
  getCardsByState: (state: CardState) => Card[];
  getFilteredCards: () => Card[];
}

export const useCardStore = create<CardStore>()(
  devtools(
    (set, get) => ({
      cards: new Map(),
      selectedCardId: null,
      filters: { states: [], labels: [], search: '' },

      setCards: (cards) => set({
        cards: new Map(cards.map(c => [c.id, c]))
      }),

      addCard: (card) => set((state) => {
        const newCards = new Map(state.cards);
        newCards.set(card.id, card);
        return { cards: newCards };
      }),

      updateCard: (card) => set((state) => {
        const newCards = new Map(state.cards);
        newCards.set(card.id, card);
        return { cards: newCards };
      }),

      removeCard: (cardId) => set((state) => {
        const newCards = new Map(state.cards);
        newCards.delete(cardId);
        return { cards: newCards };
      }),

      setSelectedCard: (cardId) => set({ selectedCardId: cardId }),

      setFilters: (filters) => set((state) => ({
        filters: { ...state.filters, ...filters }
      })),

      getCardsByState: (state) => {
        return Array.from(get().cards.values())
          .filter(card => card.state === state);
      },

      getFilteredCards: () => {
        const { cards, filters } = get();
        return Array.from(cards.values()).filter(card => {
          if (filters.states.length && !filters.states.includes(card.state)) {
            return false;
          }
          if (filters.labels.length && !filters.labels.some(l => card.labels.includes(l))) {
            return false;
          }
          if (filters.search) {
            const search = filters.search.toLowerCase();
            if (!card.title.toLowerCase().includes(search) &&
                !card.description?.toLowerCase().includes(search)) {
              return false;
            }
          }
          return true;
        });
      },
    }),
    { name: 'card-store' }
  )
);

// File: src/store/loopStore.ts

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

export interface LoopState {
  cardId: string;
  iteration: number;
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'stopped';
  totalCostUsd: number;
  totalTokens: number;
  consecutiveErrors: number;
  startTime: string;
  elapsedSeconds: number;
}

interface LoopStore {
  activeLoops: Map<string, LoopState>;

  setLoopState: (cardId: string, state: LoopState | null) => void;
  updateLoopIteration: (cardId: string, iteration: number, cost: number, tokens: number) => void;
  getActiveLoopCount: () => number;
  getTotalCost: () => number;
}

export const useLoopStore = create<LoopStore>()(
  devtools(
    (set, get) => ({
      activeLoops: new Map(),

      setLoopState: (cardId, state) => set((s) => {
        const newLoops = new Map(s.activeLoops);
        if (state) {
          newLoops.set(cardId, state);
        } else {
          newLoops.delete(cardId);
        }
        return { activeLoops: newLoops };
      }),

      updateLoopIteration: (cardId, iteration, cost, tokens) => set((s) => {
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

      getActiveLoopCount: () => {
        return Array.from(get().activeLoops.values())
          .filter(l => l.status === 'running').length;
      },

      getTotalCost: () => {
        return Array.from(get().activeLoops.values())
          .reduce((sum, l) => sum + l.totalCostUsd, 0);
      },
    }),
    { name: 'loop-store' }
  )
);

// File: src/store/uiStore.ts

import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

interface UIStore {
  sidebarCollapsed: boolean;
  kanbanView: 'board' | 'list';
  theme: 'light' | 'dark' | 'system';
  selectedProjectId: string | null;

  toggleSidebar: () => void;
  setKanbanView: (view: 'board' | 'list') => void;
  setTheme: (theme: 'light' | 'dark' | 'system') => void;
  setSelectedProject: (projectId: string | null) => void;
}

export const useUIStore = create<UIStore>()(
  devtools(
    persist(
      (set) => ({
        sidebarCollapsed: false,
        kanbanView: 'board',
        theme: 'system',
        selectedProjectId: null,

        toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
        setKanbanView: (view) => set({ kanbanView: view }),
        setTheme: (theme) => set({ theme }),
        setSelectedProject: (projectId) => set({ selectedProjectId: projectId }),
      }),
      { name: 'ringmaster-ui' }
    ),
    { name: 'ui-store' }
  )
);
```

## WebSocket Integration

```typescript
// File: src/hooks/useWebSocket.ts

import { useEffect, useRef, useCallback } from 'react';
import { useWebSocketStore } from '../store/webSocketStore';
import { useCardStore } from '../store/cardStore';
import { useLoopStore } from '../store/loopStore';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8080/api/ws';
const RECONNECT_INTERVAL = 3000;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();

  const {
    setConnected,
    subscribedCards,
    subscribedProjects,
    addSubscription,
    removeSubscription,
  } = useWebSocketStore();

  const { updateCard } = useCardStore();
  const { setLoopState, updateLoopIteration } = useLoopStore();

  const connect = useCallback(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected');
      setConnected(true);

      // Resubscribe to existing subscriptions
      if (subscribedCards.size > 0 || subscribedProjects.size > 0) {
        ws.send(JSON.stringify({
          type: 'subscribe',
          cardIds: Array.from(subscribedCards),
          projectIds: Array.from(subscribedProjects),
        }));
      }
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setConnected(false);

      // Reconnect after delay
      reconnectTimeoutRef.current = setTimeout(connect, RECONNECT_INTERVAL);
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      handleMessage(message);
    };
  }, [subscribedCards, subscribedProjects, setConnected]);

  const handleMessage = useCallback((message: WebSocketMessage) => {
    switch (message.type) {
      case 'card_updated':
        updateCard(message.data);
        break;

      case 'state_changed':
        // Card state changed, fetch updated card
        updateCard({ ...message.data.card });
        break;

      case 'loop_iteration':
        updateLoopIteration(
          message.cardId,
          message.data.iteration,
          message.data.costUsd,
          message.data.tokensUsed
        );
        break;

      case 'loop_started':
        setLoopState(message.cardId, {
          cardId: message.cardId,
          iteration: 0,
          status: 'running',
          totalCostUsd: 0,
          totalTokens: 0,
          consecutiveErrors: 0,
          startTime: new Date().toISOString(),
          elapsedSeconds: 0,
        });
        break;

      case 'loop_completed':
        setLoopState(message.cardId, null);
        break;

      case 'error_detected':
        // Show toast notification
        break;

      case 'pong':
        // Heartbeat response
        break;

      default:
        console.log('Unknown message type:', message.type);
    }
  }, [updateCard, setLoopState, updateLoopIteration]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close();
    };
  }, [connect]);

  const subscribe = useCallback((cardIds: string[], projectIds: string[] = []) => {
    cardIds.forEach(id => addSubscription('card', id));
    projectIds.forEach(id => addSubscription('project', id));

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'subscribe',
        cardIds,
        projectIds,
      }));
    }
  }, [addSubscription]);

  const unsubscribe = useCallback((cardIds: string[], projectIds: string[] = []) => {
    cardIds.forEach(id => removeSubscription('card', id));
    projectIds.forEach(id => removeSubscription('project', id));

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'unsubscribe',
        cardIds,
        projectIds,
      }));
    }
  }, [removeSubscription]);

  return { subscribe, unsubscribe };
}

interface WebSocketMessage {
  type: string;
  cardId?: string;
  data?: any;
  timestamp?: string;
}
```

## Key Components

### Kanban Board

```tsx
// File: src/components/kanban/KanbanBoard.tsx

import { DndContext, DragEndEvent, DragOverlay, closestCenter } from '@dnd-kit/core';
import { useState } from 'react';
import { useCardStore } from '../../store/cardStore';
import { KanbanColumn } from './KanbanColumn';
import { DraggableCard } from './DraggableCard';
import { useTransitionCard } from '../../hooks/useCards';

const COLUMNS: { state: CardState; title: string }[] = [
  { state: 'draft', title: 'Draft' },
  { state: 'planning', title: 'Planning' },
  { state: 'coding', title: 'Coding' },
  { state: 'code_review', title: 'Code Review' },
  { state: 'testing', title: 'Testing' },
  { state: 'build_queue', title: 'Build Queue' },
  { state: 'deploying', title: 'Deploying' },
  { state: 'completed', title: 'Completed' },
];

export function KanbanBoard() {
  const [activeCard, setActiveCard] = useState<Card | null>(null);
  const { getCardsByState } = useCardStore();
  const transitionCard = useTransitionCard();

  const handleDragStart = (event: DragStartEvent) => {
    const card = event.active.data.current?.card;
    setActiveCard(card);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveCard(null);

    const { active, over } = event;
    if (!over) return;

    const cardId = active.id as string;
    const newState = over.id as CardState;

    // Determine trigger based on state transition
    const trigger = getTransitionTrigger(active.data.current?.card.state, newState);
    if (trigger) {
      transitionCard.mutate({ cardId, trigger });
    }
  };

  return (
    <DndContext
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-4 overflow-x-auto p-4">
        {COLUMNS.map(({ state, title }) => (
          <KanbanColumn
            key={state}
            id={state}
            title={title}
            cards={getCardsByState(state)}
          />
        ))}
      </div>

      <DragOverlay>
        {activeCard && <DraggableCard card={activeCard} isDragging />}
      </DragOverlay>
    </DndContext>
  );
}

// File: src/components/kanban/KanbanColumn.tsx

import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { DraggableCard } from './DraggableCard';

interface KanbanColumnProps {
  id: string;
  title: string;
  cards: Card[];
}

export function KanbanColumn({ id, title, cards }: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id });

  return (
    <div
      ref={setNodeRef}
      className={`
        flex flex-col w-72 min-w-72 bg-gray-100 rounded-lg
        ${isOver ? 'ring-2 ring-blue-500' : ''}
      `}
    >
      <div className="flex items-center justify-between p-3 border-b">
        <h3 className="font-medium text-gray-700">{title}</h3>
        <span className="px-2 py-1 text-xs bg-gray-200 rounded-full">
          {cards.length}
        </span>
      </div>

      <div className="flex-1 p-2 space-y-2 overflow-y-auto">
        <SortableContext items={cards.map(c => c.id)} strategy={verticalListSortingStrategy}>
          {cards.map(card => (
            <DraggableCard key={card.id} card={card} />
          ))}
        </SortableContext>
      </div>
    </div>
  );
}

// File: src/components/kanban/DraggableCard.tsx

import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useNavigate } from 'react-router-dom';
import { Badge } from '../ui/Badge';
import { LoopProgress } from '../LoopProgress';
import { useLoopStore } from '../../store/loopStore';

interface DraggableCardProps {
  card: Card;
  isDragging?: boolean;
}

export function DraggableCard({ card, isDragging }: DraggableCardProps) {
  const navigate = useNavigate();
  const { activeLoops } = useLoopStore();
  const loopState = activeLoops.get(card.id);

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({
    id: card.id,
    data: { card },
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={() => navigate(`/cards/${card.id}`)}
      className={`
        p-3 bg-white rounded-lg shadow-sm border cursor-pointer
        hover:shadow-md transition-shadow
        ${isDragging ? 'opacity-50 shadow-lg' : ''}
      `}
    >
      <div className="flex items-start justify-between mb-2">
        <h4 className="font-medium text-sm text-gray-900 line-clamp-2">
          {card.title}
        </h4>
        {card.priority > 0 && (
          <Badge variant="warning" size="sm">P{card.priority}</Badge>
        )}
      </div>

      {card.labels.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {card.labels.slice(0, 3).map(label => (
            <Badge key={label} variant="secondary" size="xs">{label}</Badge>
          ))}
        </div>
      )}

      {loopState && loopState.status === 'running' && (
        <LoopProgress
          iteration={loopState.iteration}
          maxIterations={100}
          cost={loopState.totalCostUsd}
        />
      )}

      <div className="flex items-center justify-between mt-2 text-xs text-gray-500">
        <span>#{card.id.slice(0, 8)}</span>
        {card.totalCostUsd > 0 && (
          <span>${card.totalCostUsd.toFixed(2)}</span>
        )}
      </div>
    </div>
  );
}
```

### Loop Controls

```tsx
// File: src/components/loops/LoopControls.tsx

import { Play, Pause, Square, Settings } from 'lucide-react';
import { Button } from '../ui/Button';
import { useStartLoop, usePauseLoop, useStopLoop, useLoopState } from '../../hooks/useLoops';

interface LoopControlsProps {
  cardId: string;
}

export function LoopControls({ cardId }: LoopControlsProps) {
  const { data: loopState } = useLoopState(cardId);
  const startLoop = useStartLoop();
  const pauseLoop = usePauseLoop();
  const stopLoop = useStopLoop();

  const isRunning = loopState?.status === 'running';
  const isPaused = loopState?.status === 'paused';
  const isActive = isRunning || isPaused;

  return (
    <div className="flex items-center gap-2">
      {!isActive ? (
        <Button
          onClick={() => startLoop.mutate({ cardId })}
          disabled={startLoop.isPending}
          variant="primary"
        >
          <Play className="w-4 h-4 mr-1" />
          Start Loop
        </Button>
      ) : (
        <>
          {isRunning ? (
            <Button
              onClick={() => pauseLoop.mutate(cardId)}
              disabled={pauseLoop.isPending}
              variant="secondary"
            >
              <Pause className="w-4 h-4 mr-1" />
              Pause
            </Button>
          ) : (
            <Button
              onClick={() => startLoop.mutate({ cardId })}
              disabled={startLoop.isPending}
              variant="primary"
            >
              <Play className="w-4 h-4 mr-1" />
              Resume
            </Button>
          )}

          <Button
            onClick={() => stopLoop.mutate(cardId)}
            disabled={stopLoop.isPending}
            variant="destructive"
          >
            <Square className="w-4 h-4 mr-1" />
            Stop
          </Button>
        </>
      )}

      <Button variant="ghost" size="icon">
        <Settings className="w-4 h-4" />
      </Button>
    </div>
  );
}

// File: src/components/loops/LoopStatus.tsx

export function LoopStatus({ cardId }: { cardId: string }) {
  const { data: loopState } = useLoopState(cardId);

  if (!loopState) {
    return (
      <div className="p-4 text-center text-gray-500">
        No active loop
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <MetricCard
          label="Iteration"
          value={`${loopState.iteration} / 100`}
          progress={(loopState.iteration / 100) * 100}
        />
        <MetricCard
          label="Cost"
          value={`$${loopState.totalCostUsd.toFixed(2)}`}
          progress={(loopState.totalCostUsd / 300) * 100}
          variant={loopState.totalCostUsd > 200 ? 'warning' : 'default'}
        />
        <MetricCard
          label="Tokens"
          value={formatNumber(loopState.totalTokens)}
        />
      </div>

      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-500">Status</span>
        <StatusBadge status={loopState.status} />
      </div>

      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-500">Elapsed Time</span>
        <span>{formatDuration(loopState.elapsedSeconds)}</span>
      </div>

      {loopState.consecutiveErrors > 0 && (
        <div className="flex items-center justify-between text-sm text-red-600">
          <span>Consecutive Errors</span>
          <span>{loopState.consecutiveErrors} / 5</span>
        </div>
      )}
    </div>
  );
}
```

## API Integration (TanStack Query)

```typescript
// File: src/hooks/useCards.ts

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';

export function useCards(projectId?: string) {
  return useQuery({
    queryKey: ['cards', { projectId }],
    queryFn: () => api.getCards({ projectId }),
    staleTime: 30_000,
  });
}

export function useCard(cardId: string) {
  return useQuery({
    queryKey: ['cards', cardId],
    queryFn: () => api.getCard(cardId),
    enabled: !!cardId,
  });
}

export function useCreateCard() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.createCard,
    onSuccess: (newCard) => {
      queryClient.invalidateQueries({ queryKey: ['cards'] });
      queryClient.setQueryData(['cards', newCard.id], newCard);
    },
  });
}

export function useTransitionCard() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ cardId, trigger, data }: TransitionParams) =>
      api.transitionCard(cardId, trigger, data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['cards'] });
      queryClient.setQueryData(['cards', result.card.id], result.card);
    },
  });
}

// File: src/hooks/useLoops.ts

export function useLoopState(cardId: string) {
  return useQuery({
    queryKey: ['loops', cardId],
    queryFn: () => api.getLoopState(cardId),
    enabled: !!cardId,
    refetchInterval: 5000,  // Refresh every 5 seconds when active
  });
}

export function useStartLoop() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ cardId, config }: StartLoopParams) =>
      api.startLoop(cardId, config),
    onSuccess: (result, { cardId }) => {
      queryClient.setQueryData(['loops', cardId], result.state);
    },
  });
}

export function usePauseLoop() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.pauseLoop,
    onSuccess: (result, cardId) => {
      queryClient.setQueryData(['loops', cardId], result);
    },
  });
}

export function useStopLoop() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.stopLoop,
    onSuccess: (_, cardId) => {
      queryClient.setQueryData(['loops', cardId], null);
      queryClient.invalidateQueries({ queryKey: ['cards', cardId] });
    },
  });
}

// File: src/api/client.ts

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080/api';

class ApiClient {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const response = await fetch(`${BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new ApiError(error);
    }

    const { data } = await response.json();
    return data;
  }

  // Cards
  getCards = (params?: CardFilters) =>
    this.request<Card[]>(`/cards?${new URLSearchParams(params as any)}`);

  getCard = (id: string) =>
    this.request<CardDetail>(`/cards/${id}`);

  createCard = (card: NewCard) =>
    this.request<Card>('/cards', {
      method: 'POST',
      body: JSON.stringify(card),
    });

  transitionCard = (id: string, trigger: string, data?: any) =>
    this.request<TransitionResult>(`/cards/${id}/transition`, {
      method: 'POST',
      body: JSON.stringify({ trigger, data }),
    });

  // Loops
  getLoopState = (cardId: string) =>
    this.request<LoopState | null>(`/cards/${cardId}/loop`);

  startLoop = (cardId: string, config?: LoopConfig) =>
    this.request<{ state: LoopState }>(`/cards/${cardId}/loop/start`, {
      method: 'POST',
      body: JSON.stringify({ config }),
    });

  pauseLoop = (cardId: string) =>
    this.request<LoopState>(`/cards/${cardId}/loop/pause`, { method: 'POST' });

  stopLoop = (cardId: string) =>
    this.request<void>(`/cards/${cardId}/loop/stop`, { method: 'POST' });
}

export const api = new ApiClient();
```

## File Structure

```
frontend/
├── public/
│   └── favicon.ico
├── src/
│   ├── api/
│   │   └── client.ts
│   ├── components/
│   │   ├── kanban/
│   │   │   ├── KanbanBoard.tsx
│   │   │   ├── KanbanColumn.tsx
│   │   │   ├── DraggableCard.tsx
│   │   │   └── index.ts
│   │   ├── cards/
│   │   │   ├── CardDetail.tsx
│   │   │   ├── CardHeader.tsx
│   │   │   ├── CardTabs.tsx
│   │   │   └── index.ts
│   │   ├── loops/
│   │   │   ├── LoopControls.tsx
│   │   │   ├── LoopStatus.tsx
│   │   │   ├── LoopProgress.tsx
│   │   │   └── index.ts
│   │   ├── layout/
│   │   │   ├── Header.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   ├── Layout.tsx
│   │   │   └── index.ts
│   │   └── ui/
│   │       ├── Button.tsx
│   │       ├── Badge.tsx
│   │       ├── Card.tsx
│   │       ├── Dialog.tsx
│   │       ├── Input.tsx
│   │       ├── Select.tsx
│   │       ├── Tabs.tsx
│   │       └── index.ts
│   ├── hooks/
│   │   ├── useCards.ts
│   │   ├── useLoops.ts
│   │   ├── useWebSocket.ts
│   │   └── useIntegrations.ts
│   ├── pages/
│   │   ├── Dashboard.tsx
│   │   ├── Kanban.tsx
│   │   ├── CardDetail.tsx
│   │   ├── Projects.tsx
│   │   └── Settings.tsx
│   ├── store/
│   │   ├── cardStore.ts
│   │   ├── loopStore.ts
│   │   ├── uiStore.ts
│   │   ├── webSocketStore.ts
│   │   └── index.ts
│   ├── types/
│   │   ├── card.ts
│   │   ├── loop.ts
│   │   ├── api.ts
│   │   └── index.ts
│   ├── lib/
│   │   └── utils.ts
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── index.html
├── package.json
├── tailwind.config.js
├── tsconfig.json
├── vite.config.ts
└── postcss.config.js
```
