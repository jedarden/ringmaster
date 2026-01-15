import { X } from 'lucide-react';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { StateIndicator } from '../kanban/StateIndicator';
import { LoopControls } from '../loops/LoopControls';
import { LoopStatus } from '../loops/LoopStatus';
import { formatCost, formatRelativeTime } from '../../lib/utils';
import type { Card } from '../../types';

interface CardDetailPanelProps {
  card: Card;
  onClose: () => void;
}

export function CardDetailPanel({ card, onClose }: CardDetailPanelProps) {
  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-gray-800 border-l border-gray-700 shadow-xl z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-start justify-between p-4 border-b border-gray-700">
        <div className="flex-1 pr-4">
          <h2 className="text-lg font-semibold">{card.title}</h2>
          <div className="flex items-center gap-2 mt-1">
            <StateIndicator state={card.state} size="sm" />
            <span className="text-gray-500 text-xs">
              #{card.id.slice(0, 8)}
            </span>
          </div>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
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
        {card.description && (
          <section>
            <h3 className="text-sm font-medium text-gray-400 mb-2">Description</h3>
            <p className="text-sm text-gray-300">{card.description}</p>
          </section>
        )}

        {/* Task Prompt */}
        <section>
          <h3 className="text-sm font-medium text-gray-400 mb-2">Task Prompt</h3>
          <div className="text-sm text-gray-300 bg-gray-700/50 rounded-lg p-3 whitespace-pre-wrap">
            {card.taskPrompt}
          </div>
        </section>

        {/* Labels */}
        {card.labels.length > 0 && (
          <section>
            <h3 className="text-sm font-medium text-gray-400 mb-2">Labels</h3>
            <div className="flex flex-wrap gap-1">
              {card.labels.map((label) => (
                <Badge key={label} variant="secondary" size="sm">
                  {label}
                </Badge>
              ))}
            </div>
          </section>
        )}

        {/* Metadata */}
        <section>
          <h3 className="text-sm font-medium text-gray-400 mb-2">Details</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">Priority</span>
              <span>{card.priority > 0 ? `P${card.priority}` : 'None'}</span>
            </div>
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
    </div>
  );
}
