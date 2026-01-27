interface ShortcutsHelpProps {
  isOpen: boolean;
  onClose: () => void;
}

interface ShortcutGroup {
  title: string;
  shortcuts: { keys: string; description: string }[];
}

const shortcutGroups: ShortcutGroup[] = [
  {
    title: "Navigation",
    shortcuts: [
      { keys: "g m", description: "Go to mailbox (projects)" },
      { keys: "g a", description: "Go to agents (workers)" },
      { keys: "g q", description: "Go to queue" },
      { keys: "g d", description: "Go to dashboard (metrics)" },
      { keys: "g l", description: "Go to logs" },
    ],
  },
  {
    title: "Lists",
    shortcuts: [
      { keys: "j", description: "Move down in list" },
      { keys: "k", description: "Move up in list" },
      { keys: "Enter", description: "Open selected item" },
    ],
  },
  {
    title: "Actions",
    shortcuts: [
      { keys: "Cmd+K", description: "Open command palette" },
      { keys: "/", description: "Focus search" },
      { keys: "Escape", description: "Close modal / go back" },
    ],
  },
  {
    title: "Editing",
    shortcuts: [
      { keys: "Cmd+Z", description: "Undo last action" },
      { keys: "Cmd+Shift+Z", description: "Redo" },
    ],
  },
  {
    title: "Help",
    shortcuts: [
      { keys: "?", description: "Show this help" },
    ],
  },
];

export function ShortcutsHelp({ isOpen, onClose }: ShortcutsHelpProps) {
  if (!isOpen) return null;

  return (
    <div className="shortcuts-help-overlay" onClick={onClose}>
      <div
        className="shortcuts-help"
        onClick={e => e.stopPropagation()}
      >
        <div className="shortcuts-help-header">
          <h2>Keyboard Shortcuts</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="shortcuts-help-body">
          {shortcutGroups.map(group => (
            <div key={group.title} className="shortcut-group">
              <h3>{group.title}</h3>
              <table>
                <tbody>
                  {group.shortcuts.map(shortcut => (
                    <tr key={shortcut.keys}>
                      <td className="shortcut-keys">
                        {shortcut.keys.split("+").map((key, i) => (
                          <span key={i}>
                            {i > 0 && <span className="key-separator">+</span>}
                            <kbd>{key}</kbd>
                          </span>
                        ))}
                      </td>
                      <td className="shortcut-description">
                        {shortcut.description}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
        <div className="shortcuts-help-footer">
          Press <kbd>?</kbd> to toggle this help or <kbd>Escape</kbd> to close
        </div>
      </div>
    </div>
  );
}
