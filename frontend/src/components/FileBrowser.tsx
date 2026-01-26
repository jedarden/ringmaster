import { useEffect, useState, useCallback } from "react";
import { listDirectory, getFileContent } from "../api/client";
import type { FileEntry, FileContent, DirectoryListing } from "../types";

interface FileBrowserProps {
  projectId: string;
}

function formatFileSize(bytes: number | null): string {
  if (bytes === null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(entry: FileEntry): string {
  if (entry.is_dir) return "\ud83d\udcc1";

  const ext = entry.name.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "py":
      return "\ud83d\udc0d";
    case "js":
    case "ts":
    case "jsx":
    case "tsx":
      return "\ud83d\udfe8";
    case "json":
      return "\ud83d\udccb";
    case "md":
    case "txt":
      return "\ud83d\udcdd";
    case "css":
    case "scss":
    case "sass":
      return "\ud83c\udfa8";
    case "html":
      return "\ud83c\udf10";
    case "yaml":
    case "yml":
    case "toml":
      return "\u2699\ufe0f";
    case "sh":
    case "bash":
      return "\ud83d\udcbb";
    default:
      return "\ud83d\udcc4";
  }
}

export function FileBrowser({ projectId }: FileBrowserProps) {
  const [currentPath, setCurrentPath] = useState("");
  const [listing, setListing] = useState<DirectoryListing | null>(null);
  const [selectedFile, setSelectedFile] = useState<FileContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingFile, setLoadingFile] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  const loadDirectory = useCallback(async (path: string) => {
    try {
      setLoading(true);
      setError(null);
      const data = await listDirectory(projectId, path);
      setListing(data);
      setCurrentPath(path);
    } catch (err) {
      if (err instanceof Error && err.message.includes("400")) {
        setError("No working directory configured for this project");
      } else {
        setError(err instanceof Error ? err.message : "Failed to load directory");
      }
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const loadFile = useCallback(async (path: string) => {
    try {
      setLoadingFile(true);
      setFileError(null);
      const content = await getFileContent(projectId, path);
      setSelectedFile(content);
    } catch (err) {
      setFileError(err instanceof Error ? err.message : "Failed to load file");
    } finally {
      setLoadingFile(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadDirectory("");
  }, [loadDirectory]);

  const handleEntryClick = (entry: FileEntry) => {
    if (entry.is_dir) {
      loadDirectory(entry.path);
      setSelectedFile(null);
    } else {
      loadFile(entry.path);
    }
  };

  const handleNavigateUp = () => {
    if (listing?.parent_path !== null && listing?.parent_path !== undefined) {
      loadDirectory(listing.parent_path);
      setSelectedFile(null);
    }
  };

  const handleBreadcrumbClick = (path: string) => {
    loadDirectory(path);
    setSelectedFile(null);
  };

  const renderBreadcrumbs = () => {
    const parts = currentPath ? currentPath.split("/") : [];
    const breadcrumbs: { name: string; path: string }[] = [
      { name: "root", path: "" },
    ];

    let accumulated = "";
    for (const part of parts) {
      accumulated = accumulated ? `${accumulated}/${part}` : part;
      breadcrumbs.push({ name: part, path: accumulated });
    }

    return (
      <div className="file-breadcrumbs">
        {breadcrumbs.map((bc, idx) => (
          <span key={bc.path}>
            {idx > 0 && <span className="breadcrumb-sep">/</span>}
            <button
              className={`breadcrumb-btn ${idx === breadcrumbs.length - 1 ? "active" : ""}`}
              onClick={() => handleBreadcrumbClick(bc.path)}
              disabled={idx === breadcrumbs.length - 1}
            >
              {bc.name}
            </button>
          </span>
        ))}
      </div>
    );
  };

  if (loading && !listing) {
    return <div className="file-browser-loading">Loading...</div>;
  }

  if (error) {
    return (
      <div className="file-browser file-browser-error">
        <div className="file-browser-header">
          <h3>Files</h3>
        </div>
        <div className="file-browser-error-message">{error}</div>
      </div>
    );
  }

  return (
    <div className="file-browser">
      <div className="file-browser-header">
        <h3>Files</h3>
        {renderBreadcrumbs()}
      </div>

      <div className="file-browser-content">
        <div className="file-list">
          {listing?.parent_path !== null && listing?.parent_path !== undefined && (
            <div className="file-entry file-entry-parent" onClick={handleNavigateUp}>
              <span className="file-icon">\ud83d\udcc2</span>
              <span className="file-name">..</span>
            </div>
          )}
          {listing?.entries.map((entry) => (
            <div
              key={entry.path}
              className={`file-entry ${entry.is_dir ? "file-entry-dir" : "file-entry-file"} ${
                selectedFile?.path === entry.path ? "selected" : ""
              }`}
              onClick={() => handleEntryClick(entry)}
            >
              <span className="file-icon">{getFileIcon(entry)}</span>
              <span className="file-name">{entry.name}</span>
              {!entry.is_dir && entry.size !== null && (
                <span className="file-size">{formatFileSize(entry.size)}</span>
              )}
            </div>
          ))}
          {listing?.entries.length === 0 && (
            <div className="file-empty">No files in this directory</div>
          )}
        </div>

        {selectedFile && (
          <div className="file-preview">
            <div className="file-preview-header">
              <span className="file-preview-name">{selectedFile.path.split("/").pop()}</span>
              <span className="file-preview-meta">
                {formatFileSize(selectedFile.size)}
                {selectedFile.mime_type && ` \u2022 ${selectedFile.mime_type}`}
              </span>
            </div>
            {loadingFile ? (
              <div className="file-preview-loading">Loading...</div>
            ) : fileError ? (
              <div className="file-preview-error">{fileError}</div>
            ) : selectedFile.is_binary ? (
              <div className="file-preview-binary">
                Binary file - preview not available
              </div>
            ) : (
              <pre className="file-preview-content">
                <code>{selectedFile.content}</code>
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
