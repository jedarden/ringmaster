import { useEffect, useState, useCallback } from "react";
import { getFileHistory, getFileDiff, revertCommit, revertFileInCommit, revertToCommit } from "../api/client";
import type { FileHistoryResponse, CommitInfo, FileDiffResponse, RevertResponse } from "../types";
import { FileDiffViewer } from "./FileDiffViewer";

interface GitHistoryModalProps {
  projectId: string;
  filePath: string;
  onClose: () => void;
  onRevert?: () => void; // Optional callback when a revert is performed
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));

  if (days === 0) {
    const hours = Math.floor(diff / (1000 * 60 * 60));
    if (hours === 0) {
      const minutes = Math.floor(diff / (1000 * 60));
      return `${minutes} minute${minutes !== 1 ? "s" : ""} ago`;
    }
    return `${hours} hour${hours !== 1 ? "s" : ""} ago`;
  } else if (days < 7) {
    return `${days} day${days !== 1 ? "s" : ""} ago`;
  } else {
    return date.toLocaleDateString();
  }
}

type RevertMode = "commit" | "file" | "to-commit";

interface RevertState {
  mode: RevertMode;
  commit: CommitInfo;
  loading: boolean;
  error: string | null;
  result: RevertResponse | null;
}

export function GitHistoryModal({ projectId, filePath, onClose, onRevert }: GitHistoryModalProps) {
  const [history, setHistory] = useState<FileHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCommit, setSelectedCommit] = useState<CommitInfo | null>(null);
  const [diff, setDiff] = useState<FileDiffResponse | null>(null);
  const [loadingDiff, setLoadingDiff] = useState(false);

  // Revert state
  const [revertState, setRevertState] = useState<RevertState | null>(null);
  const [showRevertOptions, setShowRevertOptions] = useState<CommitInfo | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getFileHistory(projectId, filePath);
      setHistory(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load git history");
    } finally {
      setLoading(false);
    }
  }, [projectId, filePath]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleCommitSelect = async (commit: CommitInfo) => {
    if (selectedCommit?.hash === commit.hash) {
      // Deselect if already selected
      setSelectedCommit(null);
      setDiff(null);
      return;
    }

    setSelectedCommit(commit);
    setLoadingDiff(true);

    try {
      // Get diff for this commit against its parent
      const diffData = await getFileDiff(projectId, filePath, commit.hash);
      setDiff(diffData);
    } catch (err) {
      console.error("Failed to load diff:", err);
      setDiff(null);
    } finally {
      setLoadingDiff(false);
    }
  };

  const handleRevertClick = (e: React.MouseEvent, commit: CommitInfo) => {
    e.stopPropagation();
    setShowRevertOptions(showRevertOptions?.hash === commit.hash ? null : commit);
  };

  const executeRevert = async (mode: RevertMode, commit: CommitInfo) => {
    setShowRevertOptions(null);
    setRevertState({
      mode,
      commit,
      loading: true,
      error: null,
      result: null,
    });

    try {
      let result: RevertResponse;

      switch (mode) {
        case "commit":
          result = await revertCommit(projectId, commit.hash);
          break;
        case "file":
          result = await revertFileInCommit(projectId, commit.hash, filePath);
          break;
        case "to-commit":
          result = await revertToCommit(projectId, commit.hash);
          break;
      }

      setRevertState((prev) => prev ? { ...prev, loading: false, result } : null);

      if (result.success) {
        // Reload history to show new revert commit
        await loadHistory();
        onRevert?.();
      }
    } catch (err) {
      setRevertState((prev) =>
        prev
          ? {
              ...prev,
              loading: false,
              error: err instanceof Error ? err.message : "Revert failed",
            }
          : null
      );
    }
  };

  const closeRevertResult = () => {
    setRevertState(null);
  };

  // Handle Escape key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (revertState) {
          setRevertState(null);
        } else if (showRevertOptions) {
          setShowRevertOptions(null);
        } else if (selectedCommit) {
          setSelectedCommit(null);
          setDiff(null);
        } else {
          onClose();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, selectedCommit, showRevertOptions, revertState]);

  const getRevertModeLabel = (mode: RevertMode): string => {
    switch (mode) {
      case "commit":
        return "Revert Commit";
      case "file":
        return "Revert File";
      case "to-commit":
        return "Revert to Commit";
    }
  };

  return (
    <div className="git-history-overlay" onClick={onClose}>
      <div className="git-history-modal" onClick={(e) => e.stopPropagation()}>
        <div className="git-history-header">
          <h2>Git History</h2>
          <div className="git-history-path">{filePath}</div>
          <button className="git-history-close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="git-history-content">
          {loading ? (
            <div className="git-history-loading">Loading history...</div>
          ) : error ? (
            <div className="git-history-error">{error}</div>
          ) : !history?.is_git_repo ? (
            <div className="git-history-no-git">
              This project is not in a git repository.
            </div>
          ) : history.commits.length === 0 ? (
            <div className="git-history-empty">
              No commits found for this file.
            </div>
          ) : (
            <div className="git-history-layout">
              <div className={`git-history-list ${selectedCommit ? "with-diff" : ""}`}>
                {history.commits.map((commit, index) => (
                  <div
                    key={commit.hash}
                    className={`git-commit-item ${
                      selectedCommit?.hash === commit.hash ? "selected" : ""
                    }`}
                    onClick={() => handleCommitSelect(commit)}
                  >
                    <div className="git-commit-main">
                      <span className="git-commit-hash">{commit.short_hash}</span>
                      <span className="git-commit-message">{commit.message}</span>
                      <button
                        className="git-revert-btn"
                        onClick={(e) => handleRevertClick(e, commit)}
                        title="Revert this commit"
                      >
                        Revert
                      </button>
                    </div>
                    <div className="git-commit-meta">
                      <span className="git-commit-author">{commit.author_name}</span>
                      <span className="git-commit-date">{formatDate(commit.date)}</span>
                      <span className="git-commit-stats">
                        <span className="git-stat-add">+{commit.additions}</span>
                        <span className="git-stat-del">-{commit.deletions}</span>
                      </span>
                    </div>

                    {/* Revert options dropdown */}
                    {showRevertOptions?.hash === commit.hash && (
                      <div
                        className="git-revert-options"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          className="git-revert-option"
                          onClick={() => executeRevert("commit", commit)}
                          title="Create a new commit that undoes the changes from this commit"
                        >
                          <span className="revert-icon">↩</span>
                          Revert this commit
                        </button>
                        <button
                          className="git-revert-option"
                          onClick={() => executeRevert("file", commit)}
                          title="Revert only the changes to this specific file from this commit"
                        >
                          <span className="revert-icon">📄</span>
                          Revert file changes only
                        </button>
                        {index > 0 && (
                          <button
                            className="git-revert-option git-revert-option-danger"
                            onClick={() => executeRevert("to-commit", commit)}
                            title="Revert all commits from HEAD back to this commit"
                          >
                            <span className="revert-icon">⏪</span>
                            Revert to this point
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {selectedCommit && (
                <div className="git-diff-panel">
                  <div className="git-diff-header">
                    <span className="git-diff-title">
                      Changes in {selectedCommit.short_hash}
                    </span>
                    <button
                      className="git-diff-close"
                      onClick={() => {
                        setSelectedCommit(null);
                        setDiff(null);
                      }}
                    >
                      &times;
                    </button>
                  </div>
                  {loadingDiff ? (
                    <div className="git-diff-loading">Loading diff...</div>
                  ) : diff ? (
                    <FileDiffViewer diff={diff} />
                  ) : (
                    <div className="git-diff-error">Failed to load diff</div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Revert result modal */}
        {revertState && (
          <div className="git-revert-modal-overlay" onClick={closeRevertResult}>
            <div className="git-revert-modal" onClick={(e) => e.stopPropagation()}>
              <div className="git-revert-modal-header">
                <h3>{getRevertModeLabel(revertState.mode)}</h3>
                <button className="git-revert-modal-close" onClick={closeRevertResult}>
                  &times;
                </button>
              </div>
              <div className="git-revert-modal-content">
                {revertState.loading ? (
                  <div className="git-revert-loading">
                    <span className="loading-spinner"></span>
                    Reverting {revertState.commit.short_hash}...
                  </div>
                ) : revertState.error ? (
                  <div className="git-revert-error">
                    <span className="error-icon">✗</span>
                    <span>{revertState.error}</span>
                  </div>
                ) : revertState.result ? (
                  <div
                    className={`git-revert-result ${
                      revertState.result.success ? "success" : "failure"
                    }`}
                  >
                    <span className="result-icon">
                      {revertState.result.success ? "✓" : "✗"}
                    </span>
                    <p className="result-message">{revertState.result.message}</p>
                    {revertState.result.new_commit_hash && (
                      <p className="result-commit">
                        New commit: <code>{revertState.result.new_commit_hash.slice(0, 7)}</code>
                      </p>
                    )}
                    {revertState.result.conflicts && revertState.result.conflicts.length > 0 && (
                      <div className="result-conflicts">
                        <p className="conflicts-title">Conflicts in:</p>
                        <ul>
                          {revertState.result.conflicts.map((file, i) => (
                            <li key={i}>{file}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
              <div className="git-revert-modal-footer">
                <button className="btn-close-revert" onClick={closeRevertResult}>
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
