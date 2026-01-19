import { useEffect, useRef, useCallback, useState } from 'react';
import { useCardStore } from '../store/cardStore';
import { useLoopStore } from '../store/loopStore';
import type { Card, LoopState } from '../types';

const WS_URL = import.meta.env.VITE_WS_URL || `ws://${window.location.host}/api/ws`;
const RECONNECT_INTERVAL = 3000;
const HEARTBEAT_INTERVAL = 30000;

interface WebSocketMessage {
  type: string;
  cardId?: string;
  data?: unknown;
  timestamp?: string;
}

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const heartbeatIntervalRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const connectRef = useRef<() => void>(() => {});
  const [isConnected, setIsConnected] = useState(false);

  const updateCard = useCardStore((s) => s.updateCard);
  const addCard = useCardStore((s) => s.addCard);
  const setLoopState = useLoopStore((s) => s.setLoopState);
  const updateLoopIteration = useLoopStore((s) => s.updateLoopIteration);
  const updateLoopStatus = useLoopStore((s) => s.updateLoopStatus);

  const handleMessage = useCallback(
    (message: WebSocketMessage) => {
      switch (message.type) {
        case 'card_created':
          addCard(message.data as Card);
          break;

        case 'card_updated':
          updateCard(message.data as Card);
          break;

        case 'state_changed':
          if (message.data && typeof message.data === 'object') {
            const data = message.data as { card: Card };
            updateCard(data.card);
          }
          break;

        case 'loop_started':
          if (message.cardId && message.data) {
            setLoopState(message.cardId, message.data as LoopState);
          }
          break;

        case 'loop_iteration':
          if (message.cardId && message.data) {
            const data = message.data as {
              iteration: number;
              costUsd: number;
              tokensUsed: number;
            };
            updateLoopIteration(
              message.cardId,
              data.iteration,
              data.costUsd,
              data.tokensUsed
            );
          }
          break;

        case 'loop_paused':
          if (message.cardId) {
            updateLoopStatus(message.cardId, 'paused');
          }
          break;

        case 'loop_resumed':
          if (message.cardId) {
            updateLoopStatus(message.cardId, 'running');
          }
          break;

        case 'loop_completed':
        case 'loop_stopped':
        case 'loop_failed':
          if (message.cardId) {
            setLoopState(message.cardId, null);
          }
          break;

        case 'error_detected':
          // Could show a toast notification here
          console.warn('Error detected:', message.data);
          break;

        case 'pong':
          // Heartbeat response, no action needed
          break;

        default:
          console.log('Unknown WebSocket message:', message.type);
      }
    },
    [addCard, updateCard, setLoopState, updateLoopIteration, updateLoopStatus]
  );

  // Use ref to break circular dependency in useCallback
  useEffect(() => {
    const scheduleReconnect = () => {
      reconnectTimeoutRef.current = setTimeout(() => {
        connectRef.current();
      }, RECONNECT_INTERVAL);
    };

    connectRef.current = () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        return;
      }

      try {
        const ws = new WebSocket(WS_URL);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('WebSocket connected');
          setIsConnected(true);

          // Start heartbeat
          heartbeatIntervalRef.current = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'ping' }));
            }
          }, HEARTBEAT_INTERVAL);
        };

        ws.onclose = () => {
          console.log('WebSocket disconnected');
          setIsConnected(false);

          // Clear heartbeat
          if (heartbeatIntervalRef.current) {
            clearInterval(heartbeatIntervalRef.current);
          }

          // Reconnect after delay
          scheduleReconnect();
        };

        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
        };

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data) as WebSocketMessage;
            handleMessage(message);
          } catch (e) {
            console.error('Failed to parse WebSocket message:', e);
          }
        };
      } catch (e) {
        console.error('Failed to create WebSocket:', e);
        scheduleReconnect();
      }
    };

    // Initial connection
    connectRef.current();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (heartbeatIntervalRef.current) {
        clearInterval(heartbeatIntervalRef.current);
      }
      wsRef.current?.close();
    };
  }, [handleMessage]);

  const subscribe = useCallback((cardIds: string[], projectIds: string[] = []) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'subscribe',
          cardIds,
          projectIds,
        })
      );
    }
  }, []);

  const unsubscribe = useCallback((cardIds: string[], projectIds: string[] = []) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'unsubscribe',
          cardIds,
          projectIds,
        })
      );
    }
  }, []);

  return { isConnected, subscribe, unsubscribe };
}
