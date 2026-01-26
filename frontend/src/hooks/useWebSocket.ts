import { useEffect, useRef, useCallback, useState } from "react";

export type EventType =
  | "task.created"
  | "task.updated"
  | "task.deleted"
  | "task.started"
  | "task.completed"
  | "task.failed"
  | "worker.created"
  | "worker.updated"
  | "worker.deleted"
  | "worker.connected"
  | "worker.disconnected"
  | "project.created"
  | "project.updated"
  | "project.deleted"
  | "queue.updated"
  | "decision.created"
  | "decision.resolved"
  | "question.created"
  | "question.answered"
  | "scheduler.started"
  | "scheduler.stopped";

export interface WebSocketEvent {
  id: string;
  type: EventType;
  timestamp: string;
  data: Record<string, unknown>;
  project_id: string | null;
}

export type EventHandler = (event: WebSocketEvent) => void;

interface UseWebSocketOptions {
  projectId?: string;
  onEvent?: EventHandler;
  autoReconnect?: boolean;
  reconnectInterval?: number;
}

interface UseWebSocketReturn {
  connected: boolean;
  lastEvent: WebSocketEvent | null;
  send: (message: object) => void;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    projectId,
    onEvent,
    autoReconnect = true,
    reconnectInterval = 3000,
  } = options;

  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<WebSocketEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    // Build WebSocket URL
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const params = projectId ? `?project_id=${projectId}` : "";
    const wsUrl = `${protocol}//${host}/ws${params}`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WebSocketEvent;
        setLastEvent(data);
        onEvent?.(data);
      } catch {
        // Ignore non-JSON messages (like pong responses)
      }
    };

    ws.onerror = () => {
      // Error handling is done in onclose
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;

      if (autoReconnect) {
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect();
        }, reconnectInterval);
      }
    };

    wsRef.current = ws;
  }, [projectId, onEvent, autoReconnect, reconnectInterval]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const send = useCallback((message: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  return { connected, lastEvent, send };
}

// Hook for subscribing to specific event types
export function useEventSubscription(
  eventTypes: EventType[],
  handler: EventHandler,
  projectId?: string
): { connected: boolean } {
  const { connected } = useWebSocket({
    projectId,
    onEvent: (event) => {
      if (eventTypes.includes(event.type)) {
        handler(event);
      }
    },
  });

  return { connected };
}
