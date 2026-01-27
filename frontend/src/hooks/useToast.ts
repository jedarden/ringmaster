import { useState, useCallback } from "react";
import type { ToastMessage } from "../components/Toast";

/**
 * Hook for managing toast notifications.
 */
export function useToast() {
  const [messages, setMessages] = useState<ToastMessage[]>([]);

  const addToast = useCallback(
    (message: string, type: ToastMessage["type"] = "info", duration?: number) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      setMessages((prev) => [...prev, { id, message, type, duration }]);
      return id;
    },
    []
  );

  const dismissToast = useCallback((id: string) => {
    setMessages((prev) => prev.filter((msg) => msg.id !== id));
  }, []);

  const success = useCallback(
    (message: string, duration?: number) => addToast(message, "success", duration),
    [addToast]
  );

  const error = useCallback(
    (message: string, duration?: number) => addToast(message, "error", duration),
    [addToast]
  );

  const info = useCallback(
    (message: string, duration?: number) => addToast(message, "info", duration),
    [addToast]
  );

  return {
    messages,
    addToast,
    dismissToast,
    success,
    error,
    info,
  };
}
