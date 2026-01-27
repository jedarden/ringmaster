import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { useEffect, useState, useCallback } from "react";
import { healthCheck } from "../api/client";
import { useWebSocket } from "../hooks/useWebSocket";
import { useDefaultShortcuts } from "../hooks/useKeyboardShortcuts";
import { useUndo } from "../hooks/useUndo";
import { CommandPalette } from "./CommandPalette";
import { ShortcutsHelp } from "./ShortcutsHelp";
import { Toast } from "./Toast";
import { useToast } from "../hooks/useToast";
import { ActionHistoryPanel } from "./ActionHistoryPanel";

export function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [apiStatus, setApiStatus] = useState<"connected" | "disconnected" | "checking">("checking");
  const { connected: wsConnected, lastEvent } = useWebSocket();
  const toast = useToast();

  // Modal states
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [showShortcutsHelp, setShowShortcutsHelp] = useState(false);
  const [showActionHistory, setShowActionHistory] = useState(false);

  // Undo/Redo
  const undoManager = useUndo({
    onUndoSuccess: (response) => {
      toast.success(response.message);
    },
    onRedoSuccess: (response) => {
      toast.success(response.message);
    },
    onError: (error) => {
      toast.error(`Undo/Redo failed: ${error.message}`);
    },
  });

  // Refresh undo state when undo/redo events come in via WebSocket
  useEffect(() => {
    if (lastEvent?.type === "undo.performed" || lastEvent?.type === "redo.performed") {
      undoManager.refresh();
    }
  }, [lastEvent, undoManager]);

  // Health check
  useEffect(() => {
    const checkHealth = async () => {
      try {
        await healthCheck();
        setApiStatus("connected");
      } catch {
        setApiStatus("disconnected");
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  // Handle escape to close modals or go back
  const handleEscape = useCallback(() => {
    if (showCommandPalette) {
      setShowCommandPalette(false);
    } else if (showShortcutsHelp) {
      setShowShortcutsHelp(false);
    } else if (showActionHistory) {
      setShowActionHistory(false);
    } else if (location.pathname !== "/") {
      // Go back if not on home page
      navigate(-1);
    }
  }, [showCommandPalette, showShortcutsHelp, showActionHistory, location.pathname, navigate]);

  // Toggle help modal
  const toggleShortcutsHelp = useCallback(() => {
    setShowShortcutsHelp(prev => !prev);
  }, []);

  // Set up keyboard shortcuts
  const { pendingSequence } = useDefaultShortcuts({
    onGoToMailbox: () => navigate("/"),
    onGoToAgents: () => navigate("/workers"),
    onGoToQueue: () => navigate("/queue"),
    onGoToMetrics: () => navigate("/metrics"),
    onGoToLogs: () => navigate("/logs"),
    onOpenCommandPalette: () => setShowCommandPalette(true),
    onSearch: () => setShowCommandPalette(true), // "/" also opens command palette
    onShowHelp: toggleShortcutsHelp,
    onEscape: handleEscape,
    onUndo: undoManager.undo,
    onRedo: undoManager.redo,
  });

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <h1 className="app-title">Ringmaster</h1>
          <nav className="main-nav">
            <NavLink to="/" end className={({ isActive }) => isActive ? "active" : ""}>
              Projects
            </NavLink>
            <NavLink to="/workers" className={({ isActive }) => isActive ? "active" : ""}>
              Workers
            </NavLink>
            <NavLink to="/queue" className={({ isActive }) => isActive ? "active" : ""}>
              Queue
            </NavLink>
            <NavLink to="/metrics" className={({ isActive }) => isActive ? "active" : ""}>
              Metrics
            </NavLink>
            <NavLink to="/logs" className={({ isActive }) => isActive ? "active" : ""}>
              Logs
            </NavLink>
          </nav>
        </div>
        <div className="header-right">
          <button
            className="history-btn"
            onClick={() => setShowActionHistory(true)}
            title="Action History"
            style={{
              padding: "0.25rem 0.5rem",
              fontSize: "0.8rem",
              background: "transparent",
              border: "1px solid var(--color-border)",
              borderRadius: "4px",
              cursor: "pointer",
              marginRight: "0.5rem",
            }}
          >
            History
          </button>
          <button
            className="help-btn"
            onClick={toggleShortcutsHelp}
            title="Keyboard shortcuts (?)"
            style={{
              padding: "0.25rem 0.5rem",
              fontSize: "0.8rem",
              background: "transparent",
              border: "1px solid var(--color-primary)",
              borderRadius: "4px",
              cursor: "pointer",
            }}
          >
            ?
          </button>
          <span className={`ws-status status-${wsConnected ? "connected" : "disconnected"}`}>
            WS: {wsConnected ? "live" : "offline"}
          </span>
          <span className={`api-status status-${apiStatus}`}>
            API: {apiStatus}
          </span>
        </div>
      </header>
      <main className="app-main">
        <Outlet />
      </main>

      {/* Command Palette */}
      <CommandPalette
        isOpen={showCommandPalette}
        onClose={() => setShowCommandPalette(false)}
      />

      {/* Shortcuts Help Modal */}
      <ShortcutsHelp
        isOpen={showShortcutsHelp}
        onClose={() => setShowShortcutsHelp(false)}
      />

      {/* Action History Panel */}
      <ActionHistoryPanel
        isOpen={showActionHistory}
        onClose={() => setShowActionHistory(false)}
        onActionUndone={(action) => {
          toast.success(`Undone: ${action.description}`);
        }}
      />

      {/* Pending Shortcut Indicator */}
      {pendingSequence && (
        <div className="shortcut-indicator">
          {pendingSequence}...
        </div>
      )}

      {/* Toast Notifications */}
      <Toast messages={toast.messages} onDismiss={toast.dismissToast} />
    </div>
  );
}
