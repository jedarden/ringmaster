import { useState, useEffect, useCallback } from "react";
import type { Question, QuestionStats, Urgency } from "../types";
import { listQuestions, answerQuestion, getQuestionStats } from "../api/client";

interface QuestionPanelProps {
  projectId: string;
  taskId?: string;
  onQuestionAnswered?: (question: Question) => void;
}

/**
 * Panel for displaying and answering clarification questions.
 * Questions are non-blocking - work can continue with default assumptions.
 */
export function QuestionPanel({
  projectId,
  taskId,
  onQuestionAnswered,
}: QuestionPanelProps) {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [stats, setStats] = useState<QuestionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [answeringId, setAnsweringId] = useState<string | null>(null);
  const [showAnswered, setShowAnswered] = useState(false);

  const fetchQuestions = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [questionsData, statsData] = await Promise.all([
        listQuestions({
          project_id: projectId,
          related_id: taskId,
          pending_only: !showAnswered,
        }),
        getQuestionStats(projectId),
      ]);
      setQuestions(questionsData);
      setStats(statsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load questions");
    } finally {
      setLoading(false);
    }
  }, [projectId, taskId, showAnswered]);

  useEffect(() => {
    fetchQuestions();
  }, [fetchQuestions]);

  const handleAnswer = async (questionId: string, answer: string) => {
    try {
      setAnsweringId(questionId);
      const answered = await answerQuestion(questionId, { answer });
      if (showAnswered) {
        // Update the question in the list
        setQuestions((prev) =>
          prev.map((q) => (q.id === questionId ? answered : q))
        );
      } else {
        // Remove from pending list
        setQuestions((prev) => prev.filter((q) => q.id !== questionId));
      }
      if (stats) {
        setStats({
          ...stats,
          pending: stats.pending - 1,
          answered: stats.answered + 1,
        });
      }
      onQuestionAnswered?.(answered);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to answer question");
    } finally {
      setAnsweringId(null);
    }
  };

  if (loading) {
    return <div className="question-panel loading">Loading questions...</div>;
  }

  if (error) {
    return (
      <div className="question-panel error">
        <span>{error}</span>
        <button onClick={fetchQuestions}>Retry</button>
      </div>
    );
  }

  return (
    <div className="question-panel">
      <div className="question-header">
        <h3>Questions</h3>
        {stats && (
          <span className="question-stats">
            {stats.pending} pending / {stats.total} total
            {stats.by_urgency.high > 0 && (
              <span className="urgency-high"> ({stats.by_urgency.high} high priority)</span>
            )}
          </span>
        )}
      </div>

      <div className="question-filters">
        <label className="filter-checkbox">
          <input
            type="checkbox"
            checked={showAnswered}
            onChange={(e) => setShowAnswered(e.target.checked)}
          />
          Show answered
        </label>
      </div>

      {questions.length === 0 ? (
        <div className="question-empty">
          {showAnswered ? "No questions" : "No pending questions"}
        </div>
      ) : (
        <div className="question-list">
          {questions.map((question) => (
            <QuestionCard
              key={question.id}
              question={question}
              isAnswering={answeringId === question.id}
              onAnswer={(answer) => handleAnswer(question.id, answer)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface QuestionCardProps {
  question: Question;
  isAnswering: boolean;
  onAnswer: (answer: string) => void;
}

function QuestionCard({ question, isAnswering, onAnswer }: QuestionCardProps) {
  const [answer, setAnswer] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (answer.trim() && !isAnswering) {
      onAnswer(answer.trim());
    }
  };

  const handleUseDefault = () => {
    if (question.default_answer && !isAnswering) {
      onAnswer(question.default_answer);
    }
  };

  const timeAgo = formatTimeAgo(question.created_at);
  const isAnswered = question.answer !== null;

  return (
    <div className={`question-card urgency-${question.urgency} ${isAnswered ? "answered" : ""}`}>
      <div className="question-content">
        <UrgencyBadge urgency={question.urgency} />
        <span className="question-text">{question.question}</span>
      </div>

      <div className="question-meta">
        <span className="question-time">{timeAgo}</span>
        <span className="question-task">Task: {question.related_id}</span>
      </div>

      {isAnswered ? (
        <div className="question-answer-display">
          <span className="answer-label">Answer:</span>
          <span className="answer-text">{question.answer}</span>
          {question.answered_at && (
            <span className="answer-time">
              Answered {formatTimeAgo(question.answered_at)}
            </span>
          )}
        </div>
      ) : (
        <div className="question-answer-form">
          {question.default_answer && (
            <div className="default-answer">
              <span className="default-label">Default assumption:</span>
              <span className="default-text">{question.default_answer}</span>
              <button
                type="button"
                className="use-default-btn"
                onClick={handleUseDefault}
                disabled={isAnswering}
              >
                Use Default
              </button>
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Enter your answer..."
              disabled={isAnswering}
              rows={2}
            />
            <button type="submit" disabled={isAnswering || !answer.trim()}>
              {isAnswering ? "Submitting..." : "Answer"}
            </button>
          </form>
        </div>
      )}

      {isAnswering && (
        <div className="question-submitting">
          Submitting answer...
        </div>
      )}
    </div>
  );
}

function UrgencyBadge({ urgency }: { urgency: Urgency }) {
  const labels: Record<Urgency, string> = {
    low: "Low",
    medium: "Medium",
    high: "High",
  };

  return <span className={`urgency-badge urgency-${urgency}`}>{labels[urgency]}</span>;
}

function formatTimeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}
