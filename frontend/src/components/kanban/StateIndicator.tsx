import { cn } from '../../lib/utils';
import type { CardState } from '../../types';

interface StateConfig {
  name: string;
  color: string;
  bgColor: string;
}

export const STATE_CONFIG: Record<CardState, StateConfig> = {
  draft: { name: 'Draft', color: 'text-gray-400', bgColor: 'bg-gray-600' },
  planning: { name: 'Planning', color: 'text-blue-400', bgColor: 'bg-blue-600' },
  coding: { name: 'Coding', color: 'text-purple-400', bgColor: 'bg-purple-600' },
  code_review: { name: 'Code Review', color: 'text-yellow-400', bgColor: 'bg-yellow-600' },
  testing: { name: 'Testing', color: 'text-orange-400', bgColor: 'bg-orange-600' },
  build_queue: { name: 'Build Queue', color: 'text-cyan-400', bgColor: 'bg-cyan-600' },
  building: { name: 'Building', color: 'text-cyan-400', bgColor: 'bg-cyan-700' },
  build_success: { name: 'Build Success', color: 'text-green-400', bgColor: 'bg-green-600' },
  build_failed: { name: 'Build Failed', color: 'text-red-400', bgColor: 'bg-red-600' },
  deploy_queue: { name: 'Deploy Queue', color: 'text-indigo-400', bgColor: 'bg-indigo-600' },
  deploying: { name: 'Deploying', color: 'text-indigo-400', bgColor: 'bg-indigo-700' },
  verifying: { name: 'Verifying', color: 'text-teal-400', bgColor: 'bg-teal-600' },
  completed: { name: 'Completed', color: 'text-green-400', bgColor: 'bg-green-600' },
  error_fixing: { name: 'Error Fixing', color: 'text-red-400', bgColor: 'bg-red-600' },
  archived: { name: 'Archived', color: 'text-gray-500', bgColor: 'bg-gray-700' },
  failed: { name: 'Failed', color: 'text-red-500', bgColor: 'bg-red-700' },
};

interface StateIndicatorProps {
  state: CardState;
  size?: 'sm' | 'md';
  showDot?: boolean;
  className?: string;
}

export function StateIndicator({
  state,
  size = 'md',
  showDot = true,
  className,
}: StateIndicatorProps) {
  const config = STATE_CONFIG[state] || STATE_CONFIG.draft;

  return (
    <div
      className={cn(
        'flex items-center gap-1.5',
        {
          'text-xs': size === 'sm',
          'text-sm': size === 'md',
        },
        className
      )}
    >
      {showDot && (
        <span
          className={cn('rounded-full', config.bgColor, {
            'h-2 w-2': size === 'sm',
            'h-2.5 w-2.5': size === 'md',
          })}
        />
      )}
      <span className={config.color}>{config.name}</span>
    </div>
  );
}

// Columns to show in Kanban board (simplified view)
export const KANBAN_COLUMNS: { state: CardState; title: string }[] = [
  { state: 'draft', title: 'Draft' },
  { state: 'planning', title: 'Planning' },
  { state: 'coding', title: 'Coding' },
  { state: 'code_review', title: 'Review' },
  { state: 'testing', title: 'Testing' },
  { state: 'building', title: 'Building' },
  { state: 'deploying', title: 'Deploying' },
  { state: 'verifying', title: 'Verifying' },
  { state: 'completed', title: 'Completed' },
  { state: 'error_fixing', title: 'Error Fixing' },
];
