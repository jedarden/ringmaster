import { useState, useCallback, useEffect, useRef } from "react";
import { performUndo, performRedo, getUndoHistory } from "../api/client";
import type { UndoResponse, HistoryResponse } from "../types";

export interface UseUndoOptions {
  projectId?: string;
  onUndoSuccess?: (response: UndoResponse) => void;
  onRedoSuccess?: (response: UndoResponse) => void;
  onError?: (error: Error) => void;
}

export interface UseUndoReturn {
  canUndo: boolean;
  canRedo: boolean;
  isLoading: boolean;
  lastAction: UndoResponse | null;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  refresh: () => Promise<void>;
}

/**
 * Hook for managing undo/redo functionality with the backend API.
 * Automatically refreshes state when UNDO_PERFORMED or REDO_PERFORMED events are received.
 */
export function useUndo(options: UseUndoOptions = {}): UseUndoReturn {
  const { projectId, onUndoSuccess, onRedoSuccess, onError } = options;

  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [lastAction, setLastAction] = useState<UndoResponse | null>(null);

  // Use ref to track mounted state
  const mountedRef = useRef(true);

  // Refresh undo/redo availability from the server
  const refresh = useCallback(async () => {
    try {
      const history: HistoryResponse = await getUndoHistory({
        project_id: projectId,
        limit: 1,
      });
      if (mountedRef.current) {
        setCanUndo(history.can_undo);
        setCanRedo(history.can_redo);
      }
    } catch {
      // Silently ignore errors on refresh
    }
  }, [projectId]);

  // Initial load
  useEffect(() => {
    mountedRef.current = true;
    refresh();
    return () => {
      mountedRef.current = false;
    };
  }, [refresh]);

  // Perform undo
  const undo = useCallback(async () => {
    if (isLoading) return;

    setIsLoading(true);
    try {
      const response = await performUndo(projectId);
      if (mountedRef.current) {
        setLastAction(response);
        if (response.success) {
          onUndoSuccess?.(response);
        }
        // Refresh availability after action
        await refresh();
      }
    } catch (error) {
      if (mountedRef.current) {
        onError?.(error instanceof Error ? error : new Error(String(error)));
      }
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [projectId, isLoading, onUndoSuccess, onError, refresh]);

  // Perform redo
  const redo = useCallback(async () => {
    if (isLoading) return;

    setIsLoading(true);
    try {
      const response = await performRedo(projectId);
      if (mountedRef.current) {
        setLastAction(response);
        if (response.success) {
          onRedoSuccess?.(response);
        }
        // Refresh availability after action
        await refresh();
      }
    } catch (error) {
      if (mountedRef.current) {
        onError?.(error instanceof Error ? error : new Error(String(error)));
      }
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [projectId, isLoading, onRedoSuccess, onError, refresh]);

  return {
    canUndo,
    canRedo,
    isLoading,
    lastAction,
    undo,
    redo,
    refresh,
  };
}
