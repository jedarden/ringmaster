import { useEffect, useState, useCallback } from "react";
import { getFileHistory, getFileDiff } from "../api/client";
import type { FileHistoryResponse, CommitInfo, FileDiffResponse } from "../types";
import { FileDiffViewer } from "./FileDiffViewer";

interface GitHistoryModalProps {
  projectId: string;
  filePath: string;
  onClose: () => void;
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

export function GitHistoryModal({ projectId, filePath, onClose }: GitHistoryModalProps) {
  const [history, setHistory] = useState<FileHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCommit, setSelectedCommit] = useState<CommitInfo | null>(null);
  const [diff, setDiff] = useState<FileDiffResponse | null>(null);
  const [loadingDiff, setLoadingDiff] = useState(false);

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

  // Handle Escape key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (selectedCommit) {
          setSelectedCommit(null);
          setDiff(null);
        } else {
          onClose();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, selectedCommit]);

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
                {history.commits.map((commit) => (
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
                    </div>
                    <div className="git-commit-meta">
                      <span className="git-commit-author">{commit.author_name}</span>
                      <span className="git-commit-date">{formatDate(commit.date)}</span>
                      <span className="git-commit-stats">
                        <span className="git-stat-add">+{commit.additions}</span>
                        <span className="git-stat-del">-{commit.deletions}</span>
                      </span>
                    </div>
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
      </div>
    </div>
  );
}
