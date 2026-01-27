import { useState, useEffect, useRef, useCallback } from "react";
import { listMessages, createMessage, getMessageCount } from "../api/client";
import { useWebSocket, type WebSocketEvent } from "../hooks/useWebSocket";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import type { ChatMessage, MessageCreate } from "../types";

interface ChatPanelProps {
  projectId: string;
  taskId?: string | null;
}

export function ChatPanel({ projectId, taskId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [newMessage, setNewMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messageCount, setMessageCount] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Speech recognition for voice input
  const {
    isSupported: speechSupported,
    isListening,
    transcript,
    error: speechError,
    startListening,
    stopListening,
  } = useSpeechRecognition({
    onTranscript: (text, isFinal) => {
      if (isFinal) {
        // Final transcript: append to existing message
        setNewMessage((prev) => (prev ? prev + " " + text : text));
      }
    },
    onError: (err) => {
      setError(err);
    },
  });

  // Handle incoming WebSocket events
  const handleWebSocketEvent = useCallback((event: WebSocketEvent) => {
    if (event.type === "message.created") {
      const data = event.data;
      // Only add if it matches our task filter (or no filter)
      const eventTaskId = data.task_id as string | null;
      if (taskId === undefined || taskId === null || eventTaskId === taskId) {
        const newMsg: ChatMessage = {
          id: data.message_id as number,
          project_id: projectId,
          task_id: eventTaskId,
          role: data.role as "user" | "assistant" | "system",
          content: data.content as string,
          media_type: null,
          media_path: null,
          token_count: null,
          created_at: (data.created_at as string) || new Date().toISOString(),
        };
        // Check if message already exists (avoid duplicates from our own sends)
        setMessages((prev) => {
          if (prev.some((m) => m.id === newMsg.id)) {
            return prev;
          }
          return [...prev, newMsg];
        });
        setMessageCount((prev) => prev + 1);
      }
    }
  }, [projectId, taskId]);

  // Subscribe to WebSocket events for this project
  useWebSocket({
    projectId,
    onEvent: handleWebSocketEvent,
  });

  const loadMessages = useCallback(async () => {
    try {
      setLoading(true);
      const [messagesData, countData] = await Promise.all([
        listMessages(projectId, { task_id: taskId ?? undefined, limit: 100 }),
        getMessageCount(projectId, taskId ?? undefined),
      ]);
      setMessages(messagesData);
      setMessageCount(countData.count);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messages");
    } finally {
      setLoading(false);
    }
  }, [projectId, taskId]);

  useEffect(() => {
    loadMessages();
  }, [loadMessages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMessage.trim() || sending) return;

    try {
      setSending(true);
      const messageData: MessageCreate = {
        project_id: projectId,
        task_id: taskId ?? null,
        role: "user",
        content: newMessage.trim(),
      };
      await createMessage(projectId, messageData);
      setNewMessage("");
      // Note: The new message will appear via WebSocket event
      // No need to reload all messages
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
    } finally {
      setSending(false);
    }
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  const getRoleIcon = (role: string) => {
    switch (role) {
      case "user":
        return "U";
      case "assistant":
        return "A";
      case "system":
        return "S";
      default:
        return "?";
    }
  };

  const handleVoiceToggle = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  // Display value: show interim transcript while listening, otherwise the composed message
  const displayValue = isListening && transcript ? newMessage + (newMessage ? " " : "") + transcript : newMessage;

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h3>Chat</h3>
        <span className="message-count">{messageCount} messages</span>
      </div>

      {(error || speechError) && <div className="chat-error">{error || speechError}</div>}

      <div className="chat-messages">
        {loading ? (
          <div className="chat-loading">Loading messages...</div>
        ) : messages.length === 0 ? (
          <div className="chat-empty">No messages yet. Start a conversation!</div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`chat-message chat-message-${msg.role}`}
            >
              <div className="message-avatar">
                <span className={`avatar avatar-${msg.role}`}>
                  {getRoleIcon(msg.role)}
                </span>
              </div>
              <div className="message-content">
                <div className="message-header">
                  <span className="message-role">{msg.role}</span>
                  <span className="message-time">{formatTime(msg.created_at)}</span>
                </div>
                <div className="message-text">{msg.content}</div>
                {msg.media_type && (
                  <div className="message-media">
                    <span className="media-badge">{msg.media_type}</span>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSend} className="chat-input-form">
        <input
          ref={inputRef}
          type="text"
          value={displayValue}
          onChange={(e) => setNewMessage(e.target.value)}
          placeholder={isListening ? "Listening..." : "Type a message..."}
          disabled={sending || isListening}
          className={`chat-input ${isListening ? "chat-input-listening" : ""}`}
        />
        {speechSupported && (
          <button
            type="button"
            onClick={handleVoiceToggle}
            disabled={sending}
            className={`chat-voice-btn ${isListening ? "chat-voice-btn-active" : ""}`}
            title={isListening ? "Stop listening" : "Voice input"}
            aria-label={isListening ? "Stop listening" : "Start voice input"}
          >
            {isListening ? "..." : "\uD83C\uDFA4"}
          </button>
        )}
        <button type="submit" disabled={sending || !displayValue.trim()} className="chat-send-btn">
          {sending ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}
