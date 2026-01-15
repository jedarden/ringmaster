import { useState, useEffect } from 'react'
import './index.css'

// Card states based on the state machine
const STATES = [
  { id: 'draft', name: 'Draft', color: 'bg-gray-600' },
  { id: 'planning', name: 'Planning', color: 'bg-blue-600' },
  { id: 'coding', name: 'Coding', color: 'bg-purple-600' },
  { id: 'code_review', name: 'Review', color: 'bg-yellow-600' },
  { id: 'testing', name: 'Testing', color: 'bg-orange-600' },
  { id: 'building', name: 'Building', color: 'bg-cyan-600' },
  { id: 'deploying', name: 'Deploying', color: 'bg-indigo-600' },
  { id: 'verifying', name: 'Verifying', color: 'bg-teal-600' },
  { id: 'completed', name: 'Completed', color: 'bg-green-600' },
  { id: 'error_fixing', name: 'Error Fixing', color: 'bg-red-600' },
]

interface Card {
  id: string
  title: string
  description?: string
  state: string
  loopIteration: number
  totalCostUsd: number
  labels: string[]
  priority: number
}

interface Project {
  id: string
  name: string
  description?: string
  cardCount: number
  activeLoops: number
  totalCostUsd: number
}

function App() {
  const [cards, setCards] = useState<Card[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProject, setSelectedProject] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchProjects()
    fetchCards()
  }, [])

  async function fetchProjects() {
    try {
      const res = await fetch('/api/projects')
      if (res.ok) {
        const data = await res.json()
        setProjects(data.data || [])
      }
    } catch (err) {
      console.error('Failed to fetch projects:', err)
    }
  }

  async function fetchCards() {
    try {
      const res = await fetch('/api/cards')
      if (res.ok) {
        const data = await res.json()
        setCards(data.data || [])
      }
      setLoading(false)
    } catch (err) {
      setError('Failed to connect to server')
      setLoading(false)
    }
  }

  const getCardsForState = (stateId: string) =>
    cards.filter((c) => c.state === stateId)

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="text-white text-xl">Loading Ringmaster...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-2xl font-bold text-purple-400">Ringmaster</h1>
            <span className="text-gray-400 text-sm">SDLC Orchestration</span>
          </div>
          <div className="flex items-center gap-4">
            <select
              className="bg-gray-700 text-white px-3 py-1.5 rounded-md border border-gray-600"
              value={selectedProject || ''}
              onChange={(e) => setSelectedProject(e.target.value || null)}
            >
              <option value="">All Projects</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <button className="bg-purple-600 hover:bg-purple-700 px-4 py-1.5 rounded-md text-sm font-medium">
              + New Card
            </button>
          </div>
        </div>
      </header>

      {/* Kanban Board */}
      <main className="p-6 overflow-x-auto">
        {error ? (
          <div className="bg-red-900/50 text-red-300 p-4 rounded-lg">
            {error}. Make sure the server is running on port 8080.
          </div>
        ) : (
          <div className="flex gap-4" style={{ minWidth: 'max-content' }}>
            {STATES.map((state) => (
              <div
                key={state.id}
                className="bg-gray-800 rounded-lg w-72 flex-shrink-0"
              >
                {/* Column Header */}
                <div
                  className={`${state.color} px-4 py-2 rounded-t-lg flex items-center justify-between`}
                >
                  <span className="font-medium">{state.name}</span>
                  <span className="bg-white/20 px-2 py-0.5 rounded text-sm">
                    {getCardsForState(state.id).length}
                  </span>
                </div>

                {/* Cards */}
                <div className="p-2 space-y-2 min-h-[200px]">
                  {getCardsForState(state.id).map((card) => (
                    <div
                      key={card.id}
                      className="bg-gray-700 rounded-lg p-3 hover:bg-gray-650 cursor-pointer border border-gray-600"
                    >
                      <h3 className="font-medium text-sm">{card.title}</h3>
                      {card.description && (
                        <p className="text-gray-400 text-xs mt-1 line-clamp-2">
                          {card.description}
                        </p>
                      )}
                      <div className="flex items-center gap-2 mt-2">
                        {card.loopIteration > 0 && (
                          <span className="bg-purple-900/50 text-purple-300 px-1.5 py-0.5 rounded text-xs">
                            Loop #{card.loopIteration}
                          </span>
                        )}
                        {card.totalCostUsd > 0 && (
                          <span className="text-gray-400 text-xs">
                            ${card.totalCostUsd.toFixed(2)}
                          </span>
                        )}
                      </div>
                      {card.labels.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {card.labels.map((label) => (
                            <span
                              key={label}
                              className="bg-gray-600 px-1.5 py-0.5 rounded text-xs"
                            >
                              {label}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}

                  {getCardsForState(state.id).length === 0 && (
                    <div className="text-gray-500 text-sm text-center py-8">
                      No cards
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Stats Bar */}
      <footer className="fixed bottom-0 left-0 right-0 bg-gray-800 border-t border-gray-700 px-6 py-3">
        <div className="flex items-center gap-8 text-sm">
          <div>
            <span className="text-gray-400">Total Cards:</span>{' '}
            <span className="font-medium">{cards.length}</span>
          </div>
          <div>
            <span className="text-gray-400">Active Loops:</span>{' '}
            <span className="font-medium text-purple-400">
              {cards.filter((c) => c.state === 'coding').length}
            </span>
          </div>
          <div>
            <span className="text-gray-400">Projects:</span>{' '}
            <span className="font-medium">{projects.length}</span>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default App
