import { NavLink, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { healthCheck } from "../api/client";
import { useWebSocket } from "../hooks/useWebSocket";

export function Layout() {
  const [apiStatus, setApiStatus] = useState<"connected" | "disconnected" | "checking">("checking");
  const { connected: wsConnected } = useWebSocket();

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
    </div>
  );
}
