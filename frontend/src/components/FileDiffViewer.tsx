import type { FileDiffResponse, DiffHunkInfo } from "../types";

interface FileDiffViewerProps {
  diff: FileDiffResponse;
}

interface DiffLineProps {
  line: string;
  lineNumber: number;
}

function DiffLine({ line }: DiffLineProps) {
  let className = "diff-line";
  let lineContent = line;

  if (line.startsWith("+") && !line.startsWith("+++")) {
    className += " diff-line-add";
    lineContent = line.substring(1);
  } else if (line.startsWith("-") && !line.startsWith("---")) {
    className += " diff-line-del";
    lineContent = line.substring(1);
  } else if (line.startsWith(" ")) {
    className += " diff-line-ctx";
    lineContent = line.substring(1);
  } else if (line.startsWith("\\")) {
    // "No newline at end of file" marker
    className += " diff-line-meta";
  }

  return (
    <div className={className}>
      <pre className="diff-line-content">{lineContent || " "}</pre>
    </div>
  );
}

function DiffHunk({ hunk }: { hunk: DiffHunkInfo }) {
  return (
    <div className="diff-hunk">
      <div className="diff-hunk-header">{hunk.header}</div>
      <div className="diff-hunk-lines">
        {hunk.lines.map((line, idx) => (
          <DiffLine key={idx} line={line} lineNumber={idx} />
        ))}
      </div>
    </div>
  );
}

export function FileDiffViewer({ diff }: FileDiffViewerProps) {
  // Handle special cases
  if (diff.is_new) {
    return (
      <div className="diff-viewer">
        <div className="diff-status diff-status-new">New file</div>
        <div className="diff-stats">
          <span className="diff-stat-add">+{diff.additions} lines</span>
        </div>
        <div className="diff-hunks">
          {diff.hunks.map((hunk, idx) => (
            <DiffHunk key={idx} hunk={hunk} />
          ))}
        </div>
      </div>
    );
  }

  if (diff.is_deleted) {
    return (
      <div className="diff-viewer">
        <div className="diff-status diff-status-deleted">Deleted file</div>
        <div className="diff-stats">
          <span className="diff-stat-del">-{diff.deletions} lines</span>
        </div>
        <div className="diff-hunks">
          {diff.hunks.map((hunk, idx) => (
            <DiffHunk key={idx} hunk={hunk} />
          ))}
        </div>
      </div>
    );
  }

  if (diff.is_renamed) {
    return (
      <div className="diff-viewer">
        <div className="diff-status diff-status-renamed">
          Renamed: {diff.old_path} &rarr; {diff.new_path}
        </div>
        <div className="diff-stats">
          <span className="diff-stat-add">+{diff.additions}</span>
          <span className="diff-stat-del">-{diff.deletions}</span>
        </div>
        <div className="diff-hunks">
          {diff.hunks.map((hunk, idx) => (
            <DiffHunk key={idx} hunk={hunk} />
          ))}
        </div>
      </div>
    );
  }

  // Normal diff
  if (diff.hunks.length === 0) {
    return (
      <div className="diff-viewer">
        <div className="diff-empty">No changes in this commit</div>
      </div>
    );
  }

  return (
    <div className="diff-viewer">
      <div className="diff-stats">
        <span className="diff-stat-add">+{diff.additions}</span>
        <span className="diff-stat-del">-{diff.deletions}</span>
      </div>
      <div className="diff-hunks">
        {diff.hunks.map((hunk, idx) => (
          <DiffHunk key={idx} hunk={hunk} />
        ))}
      </div>
    </div>
  );
}
