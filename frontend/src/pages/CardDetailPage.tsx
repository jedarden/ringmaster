import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, GitBranch, ExternalLink, Clock, DollarSign, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
// import { Progress } from '../components/ui/Progress';
import { StateIndicator } from '../components/kanban/StateIndicator';
import { LoopControls } from '../components/loops/LoopControls';
import { LoopStatus } from '../components/loops/LoopStatus';
import { formatCost, formatRelativeTime, formatDuration, cn } from '../lib/utils';
import { useCard, useAttempts, useErrors } from '../hooks/useCards';
import type { Card, Attempt, CardError } from '../types';

type TabId = 'overview' | 'loop' | 'attempts' | 'errors' | 'deploy' | 'logs';

interface Tab {
  id: TabId;
  label: string;
  count?: number;
}

export function CardDetailPage() {
  const { cardId } = useParams<{ cardId: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabId>('overview');

  const { data: card, isLoading: cardLoading, error: cardError } = useCard(cardId || '');
  const { data: attempts } = useAttempts(cardId || '');
  const { data: errors } = useErrors(cardId || '');

  if (cardLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
      </div>
    );
  }

  if (cardError || !card) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-400">
        <AlertCircle className="w-12 h-12 mb-4" />
        <p>Card not found</p>
        <Button variant="ghost" className="mt-4" onClick={() => navigate('/kanban')}>
          Go back
        </Button>
      </div>
    );
  }

  const tabs: Tab[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'loop', label: 'Loop' },
    { id: 'attempts', label: 'Attempts', count: attempts?.length },
    { id: 'errors', label: 'Errors', count: errors?.filter((e: CardError) => !e.resolved).length },
    { id: 'deploy', label: 'Deploy' },
    { id: 'logs', label: 'Logs' },
  ];

  return (
    <div className="min-h-screen bg-gray-900">
      {/* Header */}
      <div className="border-b border-gray-700 bg-gray-800/50">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-start justify-between">
            <div className="flex items-start gap-4">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => navigate(-1)}
                className="mt-1"
              >
                <ArrowLeft className="w-5 h-5" />
              </Button>
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-semibold">{card.title}</h1>
                  <StateIndicator state={card.state} size="md" />
                </div>
                <div className="flex items-center gap-4 mt-2 text-sm text-gray-400">
                  <span>#{card.id.slice(0, 8)}</span>
                  {card.branchName && (
                    <span className="flex items-center gap-1">
                      <GitBranch className="w-4 h-4" />
                      {card.branchName}
                    </span>
                  )}
                  {card.pullRequestUrl && (
                    <a
                      href={card.pullRequestUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-purple-400 hover:underline"
                    >
                      View PR <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <LoopControls cardId={card.id} />
            </div>
          </div>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="border-b border-gray-700 bg-gray-800/30">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center gap-6">
            <StatItem
              icon={<Clock className="w-4 h-4" />}
              label="Iterations"
              value={card.loopIteration.toString()}
            />
            <StatItem
              icon={<DollarSign className="w-4 h-4" />}
              label="Total Cost"
              value={formatCost(card.totalCostUsd)}
            />
            <StatItem
              icon={<AlertCircle className="w-4 h-4" />}
              label="Errors"
              value={card.errorCount?.toString() || '0'}
              variant={card.errorCount > 0 ? 'warning' : 'default'}
            />
            <StatItem
              icon={<CheckCircle2 className="w-4 h-4" />}
              label="Priority"
              value={card.priority > 0 ? `P${card.priority}` : 'None'}
            />
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-4">
          <nav className="flex gap-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'px-4 py-3 text-sm font-medium border-b-2 transition-colors',
                  activeTab === tab.id
                    ? 'border-purple-500 text-purple-400'
                    : 'border-transparent text-gray-400 hover:text-gray-200'
                )}
              >
                {tab.label}
                {tab.count !== undefined && tab.count > 0 && (
                  <span className="ml-2 px-1.5 py-0.5 text-xs bg-gray-700 rounded-full">
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </nav>
        </div>
      </div>

      {/* Tab Content */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        {activeTab === 'overview' && <OverviewTab card={card} />}
        {activeTab === 'loop' && <LoopTab cardId={card.id} />}
        {activeTab === 'attempts' && <AttemptsTab attempts={attempts || []} />}
        {activeTab === 'errors' && <ErrorsTab errors={errors || []} />}
        {activeTab === 'deploy' && <DeployTab card={card} />}
        {activeTab === 'logs' && <LogsTab cardId={card.id} />}
      </div>
    </div>
  );
}

function StatItem({
  icon,
  label,
  value,
  variant = 'default',
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  variant?: 'default' | 'warning';
}) {
  return (
    <div className="flex items-center gap-2">
      <span className={variant === 'warning' ? 'text-yellow-500' : 'text-gray-500'}>
        {icon}
      </span>
      <span className="text-gray-500">{label}:</span>
      <span className={variant === 'warning' ? 'text-yellow-400' : 'text-white'}>
        {value}
      </span>
    </div>
  );
}

function OverviewTab({ card }: { card: Card }) {
  return (
    <div className="grid grid-cols-3 gap-6">
      <div className="col-span-2 space-y-6">
        {/* Description */}
        <section className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Description</h3>
          <p className="text-gray-200 whitespace-pre-wrap">
            {card.description || 'No description provided.'}
          </p>
        </section>

        {/* Task Prompt */}
        <section className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Task Prompt</h3>
          <div className="bg-gray-900 rounded-lg p-3 font-mono text-sm text-gray-300 whitespace-pre-wrap">
            {card.taskPrompt}
          </div>
        </section>

        {/* Acceptance Criteria */}
        {card.acceptanceCriteria && card.acceptanceCriteria.length > 0 && (
          <section className="bg-gray-800 rounded-lg p-4">
            <h3 className="text-sm font-medium text-gray-400 mb-3">Acceptance Criteria</h3>
            <ul className="space-y-2">
              {card.acceptanceCriteria.map((criterion: { met: boolean; description: string }, idx: number) => (
                <li key={idx} className="flex items-start gap-3">
                  <span className={cn(
                    'flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs',
                    criterion.met
                      ? 'bg-green-900 text-green-400'
                      : 'bg-gray-700 text-gray-400'
                  )}>
                    {criterion.met ? '✓' : idx + 1}
                  </span>
                  <span className={criterion.met ? 'text-gray-400 line-through' : 'text-gray-200'}>
                    {criterion.description}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {/* Sidebar */}
      <div className="space-y-6">
        {/* Labels */}
        {card.labels.length > 0 && (
          <section className="bg-gray-800 rounded-lg p-4">
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
        <section className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-3">Details</h3>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-gray-400">Created</dt>
              <dd>{formatRelativeTime(card.createdAt)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-400">Updated</dt>
              <dd>{formatRelativeTime(card.updatedAt)}</dd>
            </div>
            {card.stateChangedAt && (
              <div className="flex justify-between">
                <dt className="text-gray-400">State Changed</dt>
                <dd>{formatRelativeTime(card.stateChangedAt)}</dd>
              </div>
            )}
            {card.deadline && (
              <div className="flex justify-between">
                <dt className="text-gray-400">Deadline</dt>
                <dd>{formatRelativeTime(card.deadline)}</dd>
              </div>
            )}
          </dl>
        </section>
      </div>
    </div>
  );
}

function LoopTab({ cardId }: { cardId: string }) {
  return (
    <div className="grid grid-cols-2 gap-6">
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-lg font-medium mb-4">Loop Status</h3>
        <LoopStatus cardId={cardId} />
      </div>
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-lg font-medium mb-4">Loop Controls</h3>
        <LoopControls cardId={cardId} />
        <div className="mt-4 p-3 bg-gray-900 rounded text-sm text-gray-400">
          <p className="mb-2">Configuration:</p>
          <ul className="space-y-1">
            <li>• Max iterations: 100</li>
            <li>• Max cost: $300</li>
            <li>• Max runtime: 4 hours</li>
            <li>• Checkpoint interval: 10 iterations</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

function AttemptsTab({ attempts }: { attempts: Attempt[] }) {
  if (attempts.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <Clock className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>No attempts yet</p>
        <p className="text-sm mt-1">Start a loop to generate attempts</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {attempts.map((attempt) => (
        <div
          key={attempt.id}
          className="bg-gray-800 rounded-lg p-4 border border-gray-700"
        >
          <div className="flex items-start justify-between mb-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-lg font-medium">
                  Attempt #{attempt.attemptNumber}
                </span>
                <Badge
                  variant={
                    attempt.status === 'completed'
                      ? 'success'
                      : attempt.status === 'failed'
                      ? 'destructive'
                      : 'secondary'
                  }
                  size="sm"
                >
                  {attempt.status}
                </Badge>
              </div>
              <p className="text-sm text-gray-400 mt-1">
                {formatRelativeTime(attempt.startedAt)}
                {attempt.durationMs && ` • ${formatDuration(attempt.durationMs / 1000)}`}
              </p>
            </div>
            <div className="text-right text-sm">
              <div className="text-gray-400">
                {attempt.tokensUsed?.toLocaleString()} tokens
              </div>
              <div className="text-purple-400">
                {formatCost(attempt.costUsd || 0)}
              </div>
            </div>
          </div>

          {attempt.commitSha && (
            <div className="flex items-center gap-2 text-sm text-gray-400 mb-3">
              <GitBranch className="w-4 h-4" />
              <code className="font-mono">{attempt.commitSha.slice(0, 7)}</code>
              {attempt.diffStats && (
                <span className="text-green-400">
                  +{attempt.diffStats.insertions}
                </span>
              )}
              {attempt.diffStats && (
                <span className="text-red-400">
                  -{attempt.diffStats.deletions}
                </span>
              )}
            </div>
          )}

          {attempt.output && (
            <details className="mt-3">
              <summary className="cursor-pointer text-sm text-purple-400 hover:text-purple-300">
                View output
              </summary>
              <pre className="mt-2 p-3 bg-gray-900 rounded text-xs text-gray-300 overflow-x-auto max-h-64 overflow-y-auto">
                {attempt.output}
              </pre>
            </details>
          )}

          {attempt.errorMessage && (
            <div className="mt-3 p-3 bg-red-900/20 border border-red-800 rounded text-sm text-red-400">
              {attempt.errorMessage}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ErrorsTab({ errors }: { errors: CardError[] }) {
  if (errors.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <CheckCircle2 className="w-12 h-12 mx-auto mb-4 opacity-50 text-green-500" />
        <p>No errors recorded</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {errors.map((error) => (
        <div
          key={error.id}
          className={cn(
            'bg-gray-800 rounded-lg p-4 border',
            error.resolved ? 'border-gray-700 opacity-60' : 'border-red-800'
          )}
        >
          <div className="flex items-start justify-between mb-2">
            <div className="flex items-center gap-2">
              <Badge
                variant={
                  error.category === 'build'
                    ? 'secondary'
                    : error.category === 'test'
                    ? 'warning'
                    : error.category === 'deploy'
                    ? 'destructive'
                    : 'secondary'
                }
                size="sm"
              >
                {error.category}
              </Badge>
              <span className="font-mono text-sm text-gray-400">
                {error.errorType}
              </span>
            </div>
            {error.resolved && (
              <Badge variant="success" size="sm">
                Resolved
              </Badge>
            )}
          </div>

          <p className="text-red-400 font-medium mb-2">{error.message}</p>

          {error.stackTrace && (
            <details>
              <summary className="cursor-pointer text-sm text-gray-400 hover:text-gray-300">
                Stack trace
              </summary>
              <pre className="mt-2 p-3 bg-gray-900 rounded text-xs text-gray-400 overflow-x-auto max-h-48 overflow-y-auto">
                {error.stackTrace}
              </pre>
            </details>
          )}

          <div className="mt-3 text-xs text-gray-500">
            {formatRelativeTime(error.createdAt)}
            {error.resolvedAt && ` • Resolved ${formatRelativeTime(error.resolvedAt)}`}
          </div>
        </div>
      ))}
    </div>
  );
}

function DeployTab({ card }: { card: Card }) {
  return (
    <div className="grid grid-cols-2 gap-6">
      {/* Build Status */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-lg font-medium mb-4">Build Status</h3>
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-gray-400">Status</span>
            <Badge variant="secondary">Not Started</Badge>
          </div>
          {card.deploymentName && (
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Deployment</span>
              <span className="font-mono text-sm">{card.deploymentName}</span>
            </div>
          )}
          {card.deploymentNamespace && (
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Namespace</span>
              <span className="font-mono text-sm">{card.deploymentNamespace}</span>
            </div>
          )}
        </div>
      </div>

      {/* ArgoCD Status */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-lg font-medium mb-4">ArgoCD Status</h3>
        <div className="space-y-3">
          {card.argocdAppName ? (
            <>
              <div className="flex justify-between items-center">
                <span className="text-gray-400">Application</span>
                <span className="font-mono text-sm">{card.argocdAppName}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-400">Sync Status</span>
                <Badge variant="secondary">Unknown</Badge>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-400">Health</span>
                <Badge variant="secondary">Unknown</Badge>
              </div>
            </>
          ) : (
            <p className="text-gray-500 text-sm">No ArgoCD application configured</p>
          )}
        </div>
      </div>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function LogsTab(_props: { cardId: string }) {
  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <h3 className="text-lg font-medium mb-4">Logs</h3>
      <div className="bg-gray-900 rounded-lg p-4 font-mono text-sm text-gray-400 h-96 overflow-y-auto">
        <p className="text-center py-12 text-gray-600">
          No logs available. Logs will appear when the loop is running.
        </p>
      </div>
    </div>
  );
}
