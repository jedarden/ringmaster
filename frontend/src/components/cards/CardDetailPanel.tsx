import { useState, useMemo } from 'react';
import { X, Pencil, Save, XCircle } from 'lucide-react';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { Input } from '../ui/Input';
import { Textarea } from '../ui/Textarea';
import { Select } from '../ui/Select';
import { StateIndicator } from '../kanban/StateIndicator';
import { LoopControls } from '../loops/LoopControls';
import { LoopStatus } from '../loops/LoopStatus';
import { formatCost, formatRelativeTime } from '../../lib/utils';
import { useUpdateCard } from '../../hooks/useCards';
import type { Card } from '../../types';

interface CardDetailPanelProps {
  card: Card;
  onClose: () => void;
}

// Inner component that resets state when card.id changes via key prop
function CardDetailPanelInner({ card, onClose }: CardDetailPanelProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedTitle, setEditedTitle] = useState(card.title);
  const [editedDescription, setEditedDescription] = useState(card.description || '');
  const [editedTaskPrompt, setEditedTaskPrompt] = useState(card.taskPrompt);
  const labelsString = useMemo(() => card.labels.join(', '), [card.labels]);
  const [editedLabels, setEditedLabels] = useState(labelsString);
  const [editedPriority, setEditedPriority] = useState(card.priority);

  const updateCard = useUpdateCard();

  const handleSave = async () => {
    const labels = editedLabels
      .split(',')
      .map((l) => l.trim())
      .filter((l) => l.length > 0);

    try {
      await updateCard.mutateAsync({
        id: card.id,
        updates: {
          title: editedTitle,
          description: editedDescription || undefined,
          taskPrompt: editedTaskPrompt,
          labels,
          priority: editedPriority,
        },
      });
      setIsEditing(false);
    } catch (err) {
      console.error('Failed to update card:', err);
    }
  };

  const handleCancel = () => {
    setEditedTitle(card.title);
    setEditedDescription(card.description || '');
    setEditedTaskPrompt(card.taskPrompt);
    setEditedLabels(card.labels.join(', '));
    setEditedPriority(card.priority);
    setIsEditing(false);
  };

  return (
    <div className="fixed inset-y-0 right-0 w-[480px] bg-gray-800 border-l border-gray-700 shadow-xl z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-start justify-between p-4 border-b border-gray-700">
        <div className="flex-1 pr-4">
          {isEditing ? (
            <Input
              value={editedTitle}
              onChange={(e) => setEditedTitle(e.target.value)}
              className="text-lg font-semibold"
              placeholder="Card title"
            />
          ) : (
            <h2 className="text-lg font-semibold">{card.title}</h2>
          )}
          <div className="flex items-center gap-2 mt-1">
            <StateIndicator state={card.state} size="sm" />
            <span className="text-gray-500 text-xs">
              #{card.id.slice(0, 8)}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {isEditing ? (
            <>
              <Button
                variant="ghost"
                size="icon"
                onClick={handleCancel}
                title="Cancel"
              >
                <XCircle className="h-4 w-4 text-gray-400" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={handleSave}
                disabled={updateCard.isPending}
                title="Save"
              >
                <Save className="h-4 w-4 text-green-400" />
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setIsEditing(true)}
              title="Edit card"
            >
              <Pencil className="h-4 w-4 text-gray-400" />
            </Button>
          )}
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* Loop Controls */}
        <section>
          <h3 className="text-sm font-medium text-gray-400 mb-2">Loop Control</h3>
          <LoopControls cardId={card.id} />
          <div className="mt-4">
            <LoopStatus cardId={card.id} />
          </div>
        </section>

        {/* Description */}
        <section>
          <h3 className="text-sm font-medium text-gray-400 mb-2">Description</h3>
          {isEditing ? (
            <Input
              value={editedDescription}
              onChange={(e) => setEditedDescription(e.target.value)}
              placeholder="Brief description of this task"
            />
          ) : (
            <p className="text-sm text-gray-300">
              {card.description || <span className="text-gray-500 italic">No description</span>}
            </p>
          )}
        </section>

        {/* Task Prompt - Main context for AI */}
        <section>
          <h3 className="text-sm font-medium text-gray-400 mb-2">
            Task Prompt
            <span className="ml-2 text-xs text-purple-400">(fed to AI as context)</span>
          </h3>
          {isEditing ? (
            <Textarea
              value={editedTaskPrompt}
              onChange={(e) => setEditedTaskPrompt(e.target.value)}
              placeholder="Describe what you want the AI to accomplish..."
              rows={8}
              className="font-mono text-sm"
            />
          ) : (
            <div className="text-sm text-gray-300 bg-gray-700/50 rounded-lg p-3 whitespace-pre-wrap font-mono">
              {card.taskPrompt}
            </div>
          )}
        </section>

        {/* Labels */}
        <section>
          <h3 className="text-sm font-medium text-gray-400 mb-2">Labels</h3>
          {isEditing ? (
            <Input
              value={editedLabels}
              onChange={(e) => setEditedLabels(e.target.value)}
              placeholder="Comma-separated labels (e.g., bug, frontend, urgent)"
            />
          ) : card.labels.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {card.labels.map((label) => (
                <Badge key={label} variant="secondary" size="sm">
                  {label}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500 italic">No labels</p>
          )}
        </section>

        {/* Priority */}
        <section>
          <h3 className="text-sm font-medium text-gray-400 mb-2">Priority</h3>
          {isEditing ? (
            <Select
              value={editedPriority}
              onChange={(e) => setEditedPriority(Number(e.target.value))}
            >
              <option value={0}>None</option>
              <option value={1}>P1 - Critical</option>
              <option value={2}>P2 - High</option>
              <option value={3}>P3 - Medium</option>
              <option value={4}>P4 - Low</option>
            </Select>
          ) : (
            <span className="text-sm text-gray-300">
              {card.priority > 0 ? `P${card.priority}` : 'None'}
            </span>
          )}
        </section>

        {/* Metadata (read-only) */}
        <section>
          <h3 className="text-sm font-medium text-gray-400 mb-2">Details</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">Total Cost</span>
              <span>{formatCost(card.totalCostUsd)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Loop Iterations</span>
              <span>{card.loopIteration}</span>
            </div>
            {card.branchName && (
              <div className="flex justify-between">
                <span className="text-gray-400">Branch</span>
                <span className="font-mono text-xs">{card.branchName}</span>
              </div>
            )}
            {card.pullRequestUrl && (
              <div className="flex justify-between">
                <span className="text-gray-400">Pull Request</span>
                <a
                  href={card.pullRequestUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-purple-400 hover:underline"
                >
                  View PR
                </a>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-gray-400">Created</span>
              <span>{formatRelativeTime(card.createdAt)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Updated</span>
              <span>{formatRelativeTime(card.updatedAt)}</span>
            </div>
          </div>
        </section>
      </div>

      {/* Edit mode footer */}
      {isEditing && (
        <div className="p-4 border-t border-gray-700 bg-gray-800/50">
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={handleCancel}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={updateCard.isPending}>
              {updateCard.isPending ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// Wrapper component that uses key prop to reset state when card changes
export function CardDetailPanel({ card, onClose }: CardDetailPanelProps) {
  return <CardDetailPanelInner key={card.id} card={card} onClose={onClose} />;
}
