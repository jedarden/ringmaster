import { useEffect, useState, useCallback } from "react";

export interface ToastMessage {
  id: string;
  message: string;
  type: "success" | "error" | "info";
  duration?: number;
}

interface ToastProps {
  messages: ToastMessage[];
  onDismiss: (id: string) => void;
}

/**
 * Toast notification component that displays temporary messages.
 */
export function Toast({ messages, onDismiss }: ToastProps) {
  if (messages.length === 0) return null;

  return (
    <div className="toast-container">
      {messages.map((msg) => (
        <ToastItem key={msg.id} message={msg} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

interface ToastItemProps {
  message: ToastMessage;
  onDismiss: (id: string) => void;
}

function ToastItem({ message, onDismiss }: ToastItemProps) {
  const [isExiting, setIsExiting] = useState(false);
  const duration = message.duration ?? 3000;

  const handleDismiss = useCallback(() => {
    setIsExiting(true);
    setTimeout(() => onDismiss(message.id), 200);
  }, [message.id, onDismiss]);

  useEffect(() => {
    const timer = setTimeout(handleDismiss, duration);
    return () => clearTimeout(timer);
  }, [duration, handleDismiss]);

  return (
    <div
      className={`toast-item toast-${message.type} ${isExiting ? "toast-exiting" : ""}`}
      onClick={handleDismiss}
    >
      <span className="toast-icon">
        {message.type === "success" && "\u2713"}
        {message.type === "error" && "\u2717"}
        {message.type === "info" && "\u2139"}
      </span>
      <span className="toast-message">{message.message}</span>
    </div>
  );
}

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
