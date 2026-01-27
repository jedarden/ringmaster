import { useEffect, useCallback, useState, useRef } from "react";

/**
 * Keyboard shortcut definition
 */
export interface Shortcut {
  keys: string; // e.g., "g m", "Cmd+k", "j", "Escape"
  action: () => void;
  description: string;
  scope?: "global" | "list" | "modal"; // Where shortcut is active
  enabled?: boolean;
}

/**
 * Parse keyboard event into a normalized key string
 */
function parseKeyEvent(e: KeyboardEvent): string {
  const parts: string[] = [];

  if (e.metaKey || e.ctrlKey) parts.push("Cmd");
  if (e.shiftKey) parts.push("Shift");
  if (e.altKey) parts.push("Alt");

  // Map special keys
  const keyMap: Record<string, string> = {
    " ": "Space",
    "ArrowUp": "Up",
    "ArrowDown": "Down",
    "ArrowLeft": "Left",
    "ArrowRight": "Right",
  };

  const key = keyMap[e.key] || e.key;

  // Don't add modifier keys as the key itself
  if (!["Control", "Meta", "Shift", "Alt"].includes(e.key)) {
    parts.push(key);
  }

  return parts.join("+");
}

/**
 * Normalize shortcut definition to match parsed events
 * e.g., "Cmd+K" -> "Cmd+K", "g m" stays as is for sequence handling
 */
function normalizeShortcut(shortcut: string): string {
  return shortcut
    .split("+")
    .map(part => part.trim())
    .map(part => {
      // Capitalize single letters
      if (part.length === 1 && /[a-z]/.test(part)) {
        return part.toLowerCase();
      }
      return part;
    })
    .join("+");
}

export interface UseKeyboardShortcutsOptions {
  shortcuts: Shortcut[];
  enabled?: boolean;
  sequenceTimeout?: number; // Time to wait for sequence completion (ms)
}

export interface UseKeyboardShortcutsReturn {
  pendingSequence: string | null;
  activeShortcuts: Shortcut[];
}

/**
 * Hook for handling keyboard shortcuts including sequences (like "g m")
 */
export function useKeyboardShortcuts(
  options: UseKeyboardShortcutsOptions
): UseKeyboardShortcutsReturn {
  const { shortcuts, enabled = true, sequenceTimeout = 500 } = options;

  const [pendingSequence, setPendingSequence] = useState<string | null>(null);
  const sequenceTimeoutRef = useRef<number | null>(null);
  const shortcutsRef = useRef(shortcuts);

  // Keep ref updated with latest shortcuts
  useEffect(() => {
    shortcutsRef.current = shortcuts;
  }, [shortcuts]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!enabled) return;

    // Don't handle shortcuts when typing in inputs
    const target = e.target as HTMLElement;
    if (
      target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.isContentEditable
    ) {
      // Allow Escape in inputs
      if (e.key !== "Escape") return;
    }

    const key = parseKeyEvent(e);
    const lowerKey = key.toLowerCase();

    // Clear sequence timeout
    if (sequenceTimeoutRef.current) {
      clearTimeout(sequenceTimeoutRef.current);
      sequenceTimeoutRef.current = null;
    }

    // Build sequence
    const currentSequence = pendingSequence ? `${pendingSequence} ${lowerKey}` : lowerKey;

    // Check for exact matches
    const enabledShortcuts = shortcutsRef.current.filter(s => s.enabled !== false);

    // First check if current sequence exactly matches any shortcut
    const exactMatch = enabledShortcuts.find(
      s => normalizeShortcut(s.keys).toLowerCase() === currentSequence
    );

    if (exactMatch) {
      e.preventDefault();
      setPendingSequence(null);
      exactMatch.action();
      return;
    }

    // Check if sequence is a prefix of any shortcut
    const isPrefix = enabledShortcuts.some(s => {
      const normalized = normalizeShortcut(s.keys).toLowerCase();
      return normalized.startsWith(currentSequence + " ");
    });

    if (isPrefix) {
      e.preventDefault();
      setPendingSequence(currentSequence);

      // Set timeout to clear pending sequence
      sequenceTimeoutRef.current = window.setTimeout(() => {
        setPendingSequence(null);
      }, sequenceTimeout);
      return;
    }

    // Check for single-key match (non-sequence shortcuts)
    const singleMatch = enabledShortcuts.find(
      s => normalizeShortcut(s.keys).toLowerCase() === lowerKey && !s.keys.includes(" ")
    );

    if (singleMatch) {
      e.preventDefault();
      setPendingSequence(null);
      singleMatch.action();
      return;
    }

    // No match, clear pending sequence
    setPendingSequence(null);
  }, [enabled, pendingSequence, sequenceTimeout]);

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (sequenceTimeoutRef.current) {
        clearTimeout(sequenceTimeoutRef.current);
      }
    };
  }, [handleKeyDown]);

  return {
    pendingSequence,
    activeShortcuts: shortcuts.filter(s => s.enabled !== false),
  };
}

/**
 * Hook for navigating lists with j/k keys
 */
export interface UseListNavigationOptions<T> {
  items: T[];
  enabled?: boolean;
  onSelect?: (item: T, index: number) => void;
  onOpen?: (item: T, index: number) => void;
}

export interface UseListNavigationReturn {
  selectedIndex: number;
  setSelectedIndex: (index: number) => void;
}

export function useListNavigation<T>(
  options: UseListNavigationOptions<T>
): UseListNavigationReturn {
  const { items, enabled = true, onSelect, onOpen } = options;
  const [selectedIndex, setSelectedIndex] = useState(-1);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!enabled || items.length === 0) return;

    // Don't handle when typing in inputs
    const target = e.target as HTMLElement;
    if (
      target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.isContentEditable
    ) {
      return;
    }

    switch (e.key) {
      case "j":
        e.preventDefault();
        setSelectedIndex(prev => {
          const next = prev < items.length - 1 ? prev + 1 : prev;
          onSelect?.(items[next], next);
          return next;
        });
        break;

      case "k":
        e.preventDefault();
        setSelectedIndex(prev => {
          const next = prev > 0 ? prev - 1 : 0;
          onSelect?.(items[next], next);
          return next;
        });
        break;

      case "Enter":
        if (selectedIndex >= 0 && selectedIndex < items.length) {
          e.preventDefault();
          onOpen?.(items[selectedIndex], selectedIndex);
        }
        break;
    }
  }, [enabled, items, selectedIndex, onSelect, onOpen]);

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // Reset selection when items change
  useEffect(() => {
    if (selectedIndex >= items.length) {
      setSelectedIndex(items.length > 0 ? 0 : -1);
    }
  }, [items.length, selectedIndex]);

  return { selectedIndex, setSelectedIndex };
}

/**
 * Default keyboard shortcuts for the application
 */
export function useDefaultShortcuts(options: {
  onGoToMailbox?: () => void;
  onGoToAgents?: () => void;
  onGoToQueue?: () => void;
  onGoToMetrics?: () => void;
  onGoToLogs?: () => void;
  onUndo?: () => void;
  onRedo?: () => void;
  onOpenCommandPalette?: () => void;
  onSearch?: () => void;
  onShowHelp?: () => void;
  onEscape?: () => void;
}) {
  const shortcuts: Shortcut[] = [
    // Navigation shortcuts (g prefix)
    {
      keys: "g m",
      action: options.onGoToMailbox || (() => {}),
      description: "Go to mailbox (projects)",
      scope: "global",
      enabled: !!options.onGoToMailbox,
    },
    {
      keys: "g a",
      action: options.onGoToAgents || (() => {}),
      description: "Go to agents (workers)",
      scope: "global",
      enabled: !!options.onGoToAgents,
    },
    {
      keys: "g q",
      action: options.onGoToQueue || (() => {}),
      description: "Go to queue",
      scope: "global",
      enabled: !!options.onGoToQueue,
    },
    {
      keys: "g d",
      action: options.onGoToMetrics || (() => {}),
      description: "Go to dashboard (metrics)",
      scope: "global",
      enabled: !!options.onGoToMetrics,
    },
    {
      keys: "g l",
      action: options.onGoToLogs || (() => {}),
      description: "Go to logs",
      scope: "global",
      enabled: !!options.onGoToLogs,
    },

    // Undo/Redo
    {
      keys: "Cmd+z",
      action: options.onUndo || (() => {}),
      description: "Undo last action",
      scope: "global",
      enabled: !!options.onUndo,
    },
    {
      keys: "Cmd+Shift+z",
      action: options.onRedo || (() => {}),
      description: "Redo",
      scope: "global",
      enabled: !!options.onRedo,
    },

    // Command palette & search
    {
      keys: "Cmd+k",
      action: options.onOpenCommandPalette || (() => {}),
      description: "Open command palette",
      scope: "global",
      enabled: !!options.onOpenCommandPalette,
    },
    {
      keys: "/",
      action: options.onSearch || (() => {}),
      description: "Search",
      scope: "global",
      enabled: !!options.onSearch,
    },

    // Help
    {
      keys: "?",
      action: options.onShowHelp || (() => {}),
      description: "Show keyboard shortcuts",
      scope: "global",
      enabled: !!options.onShowHelp,
    },

    // Escape
    {
      keys: "Escape",
      action: options.onEscape || (() => {}),
      description: "Close modal / go back",
      scope: "global",
      enabled: !!options.onEscape,
    },
  ];

  return useKeyboardShortcuts({ shortcuts });
}
