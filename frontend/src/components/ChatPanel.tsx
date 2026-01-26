import { useState, useEffect, useRef, useCallback } from "react";
import { listMessages, createMessage, getMessageCount } from "../api/client";
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
      await loadMessages();
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

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h3>Chat</h3>
        <span className="message-count">{messageCount} messages</span>
      </div>

      {error && <div className="chat-error">{error}</div>}

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
          type="text"
          value={newMessage}
          onChange={(e) => setNewMessage(e.target.value)}
          placeholder="Type a message..."
          disabled={sending}
          className="chat-input"
        />
        <button type="submit" disabled={sending || !newMessage.trim()} className="chat-send-btn">
          {sending ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}
