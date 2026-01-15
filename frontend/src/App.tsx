import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Header } from './components/layout/Header';
import { StatsBar } from './components/layout/StatsBar';
import { useWebSocket } from './hooks/useWebSocket';
import { DashboardPage, KanbanPage, ProjectsPage, SettingsPage, CardDetailPage } from './pages';
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

function AppLayout() {
  const { isConnected } = useWebSocket();

  return (
    <div className="min-h-screen bg-gray-900 text-white flex flex-col">
      {/* Header */}
      <Header />

      {/* Connection status */}
      {!isConnected && (
        <div className="bg-yellow-900/50 text-yellow-300 px-4 py-2 text-sm text-center">
          Connecting to server...
        </div>
      )}

      {/* Main content */}
      <main className="flex-1 overflow-auto pb-16">
        <Routes>
          <Route path="/" element={<Navigate to="/kanban" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/kanban" element={<KanbanPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/cards/:cardId" element={<CardDetailPage />} />
        </Routes>
      </main>

      {/* Stats Bar */}
      <StatsBar />
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppLayout />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
