import { useEffect, useRef, useState, useCallback } from "react";
import { getWorkerOutput, getWorkerOutputStreamUrl } from "../api/client";
import type { OutputLine } from "../types";

interface WorkerOutputPanelProps {
  workerId: string;
  isOpen: boolean;
  onClose: () => void;
}

export function WorkerOutputPanel({ workerId, isOpen, onClose }: WorkerOutputPanelProps) {
  const [lines, setLines] = useState<OutputLine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const outputRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const lastLineRef = useRef<number>(0);

  // Load initial output
  const loadInitialOutput = useCallback(async () => {
    try {
      setLoading(true);
      const response = await getWorkerOutput(workerId, 500);
      setLines(response.lines);
      if (response.lines.length > 0) {
        lastLineRef.current = response.lines[response.lines.length - 1].line_number;
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load output");
    } finally {
      setLoading(false);
    }
  }, [workerId]);

  // Connect to SSE stream for real-time updates
  const connectStream = useCallback(() => {
    if (!isLive || eventSourceRef.current) return;

    const url = getWorkerOutputStreamUrl(workerId);
    const eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      try {
        const line: OutputLine = JSON.parse(event.data);
        setLines((prev) => {
          // Avoid duplicates
          if (line.line_number <= lastLineRef.current) {
            return prev;
          }
          lastLineRef.current = line.line_number;
          return [...prev, line];
        });
      } catch {
        // Ignore parse errors
      }
    };

    eventSource.onerror = () => {
      // Connection error - will auto-reconnect
      eventSource.close();
      eventSourceRef.current = null;
      // Reconnect after delay
      setTimeout(() => {
        if (isLive && isOpen) {
          connectStream();
        }
      }, 2000);
    };

    eventSourceRef.current = eventSource;
  }, [workerId, isLive, isOpen]);

  // Disconnect from stream
  const disconnectStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  // Initial load
  useEffect(() => {
    if (isOpen) {
      loadInitialOutput();
    }
  }, [isOpen, loadInitialOutput]);

  // Connect/disconnect based on live mode
  useEffect(() => {
    if (isOpen && isLive) {
      connectStream();
    } else {
      disconnectStream();
    }

    return () => {
      disconnectStream();
    };
  }, [isOpen, isLive, connectStream, disconnectStream]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [lines, autoScroll]);

  // Handle scroll to detect manual scrolling
  const handleScroll = () => {
    if (!outputRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = outputRef.current;
    // If user scrolled up, disable auto-scroll
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    setAutoScroll(isAtBottom);
  };

  if (!isOpen) return null;

  return (
    <div className="worker-output-panel">
      <div className="worker-output-header">
        <h3>Worker Output</h3>
        <div className="worker-output-controls">
          <label className="live-toggle">
            <input
              type="checkbox"
              checked={isLive}
              onChange={(e) => setIsLive(e.target.checked)}
            />
            Live
            <span className={`status-indicator ${isLive ? "connected" : ""}`} />
          </label>
          <label className="auto-scroll-toggle">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            Auto-scroll
          </label>
          <span className="line-count">{lines.length} lines</span>
          <button onClick={() => loadInitialOutput()} title="Refresh">
            Refresh
          </button>
          <button onClick={onClose} className="close-btn" title="Close">
            x
          </button>
        </div>
      </div>
      <div className="worker-output-content" ref={outputRef} onScroll={handleScroll}>
        {loading && lines.length === 0 && (
          <div className="output-loading">Loading output...</div>
        )}
        {error && <div className="output-error">{error}</div>}
        {!loading && lines.length === 0 && !error && (
          <div className="output-empty">No output yet. Worker output will appear here when the worker runs.</div>
        )}
        {lines.map((line) => (
          <div key={line.line_number} className="output-line">
            <span className="line-number">{line.line_number}</span>
            <span className="line-content">{line.line}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
