import { useState, useEffect, useRef, useCallback } from "react";
import { listMessages, createMessage, getMessageCount, uploadFile } from "../api/client";
import { useWebSocket, type WebSocketEvent } from "../hooks/useWebSocket";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import type { ChatMessage, MessageCreate, FileUploadResponse } from "../types";

interface ChatPanelProps {
  projectId: string;
  taskId?: string | null;
}

interface PendingAttachment {
  file: File;
  uploadResponse: FileUploadResponse | null;
  uploading: boolean;
  error: string | null;
}

export function ChatPanel({ projectId, taskId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [newMessage, setNewMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messageCount, setMessageCount] = useState(0);
  const [pendingAttachment, setPendingAttachment] = useState<PendingAttachment | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
          media_type: (data.media_type as string) || null,
          media_path: (data.media_path as string) || null,
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

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file size (10MB limit)
    if (file.size > 10 * 1024 * 1024) {
      setError("File too large. Maximum size is 10MB.");
      return;
    }

    setPendingAttachment({
      file,
      uploadResponse: null,
      uploading: true,
      error: null,
    });

    try {
      const response = await uploadFile(projectId, file);
      setPendingAttachment((prev) =>
        prev ? { ...prev, uploadResponse: response, uploading: false } : null
      );
    } catch (err) {
      setPendingAttachment((prev) =>
        prev
          ? { ...prev, uploading: false, error: err instanceof Error ? err.message : "Upload failed" }
          : null
      );
    }

    // Clear the file input
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleRemoveAttachment = () => {
    setPendingAttachment(null);
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const hasContent = newMessage.trim();
    const hasAttachment = pendingAttachment?.uploadResponse;

    if ((!hasContent && !hasAttachment) || sending) return;

    try {
      setSending(true);
      const uploadResponse = pendingAttachment?.uploadResponse;
      const messageData: MessageCreate = {
        project_id: projectId,
        task_id: taskId ?? null,
        role: "user",
        content: newMessage.trim() || (uploadResponse ? `[Attached: ${pendingAttachment.file.name}]` : ""),
        media_type: uploadResponse ? uploadResponse.media_type : undefined,
        media_path: uploadResponse ? uploadResponse.path : undefined,
      };
      await createMessage(projectId, messageData);
      setNewMessage("");
      setPendingAttachment(null);
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

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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

  const getMediaIcon = (mediaType: string) => {
    switch (mediaType) {
      case "image":
        return "\uD83D\uDDBC\uFE0F"; // framed picture
      case "document":
        return "\uD83D\uDCC4"; // document
      case "code":
        return "\uD83D\uDCDD"; // memo
      case "archive":
        return "\uD83D\uDCE6"; // package
      default:
        return "\uD83D\uDCC1"; // folder
    }
  };

  const handleVoiceToggle = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  const handleAttachClick = () => {
    fileInputRef.current?.click();
  };

  // Display value: show interim transcript while listening, otherwise the composed message
  const displayValue = isListening && transcript ? newMessage + (newMessage ? " " : "") + transcript : newMessage;

  const canSend = (displayValue.trim() || pendingAttachment?.uploadResponse) && !sending;

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
                {msg.media_type && msg.media_path && (
                  <div className="message-attachment">
                    <span className="attachment-icon">{getMediaIcon(msg.media_type)}</span>
                    <span className="attachment-info">
                      <span className="attachment-type">{msg.media_type}</span>
                      <span className="attachment-name">{msg.media_path.split("/").pop()}</span>
                    </span>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {pendingAttachment && (
        <div className="chat-attachment-preview">
          {pendingAttachment.uploading ? (
            <span className="attachment-uploading">Uploading {pendingAttachment.file.name}...</span>
          ) : pendingAttachment.error ? (
            <span className="attachment-error">
              Failed to upload: {pendingAttachment.error}
              <button
                type="button"
                onClick={handleRemoveAttachment}
                className="attachment-remove"
                aria-label="Remove attachment"
              >
                x
              </button>
            </span>
          ) : pendingAttachment.uploadResponse ? (
            <span className="attachment-ready">
              <span className="attachment-icon">{getMediaIcon(pendingAttachment.uploadResponse.media_type)}</span>
              <span className="attachment-details">
                <span className="attachment-filename">{pendingAttachment.file.name}</span>
                <span className="attachment-size">{formatFileSize(pendingAttachment.uploadResponse.size)}</span>
              </span>
              <button
                type="button"
                onClick={handleRemoveAttachment}
                className="attachment-remove"
                aria-label="Remove attachment"
              >
                x
              </button>
            </span>
          ) : null}
        </div>
      )}

      <form onSubmit={handleSend} className="chat-input-form">
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileSelect}
          style={{ display: "none" }}
          accept="image/*,.pdf,.txt,.md,.py,.js,.ts,.tsx,.json,.html,.css,.zip,.gz"
        />
        <button
          type="button"
          onClick={handleAttachClick}
          disabled={sending || pendingAttachment?.uploading}
          className="chat-attach-btn"
          title="Attach file"
          aria-label="Attach file"
        >
          {"\uD83D\uDCCE"}
        </button>
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
        <button type="submit" disabled={!canSend} className="chat-send-btn">
          {sending ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}
