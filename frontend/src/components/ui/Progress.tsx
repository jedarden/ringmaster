import { cn } from '../../lib/utils';

export interface ProgressProps {
  value: number;
  max?: number;
  variant?: 'default' | 'success' | 'warning' | 'destructive';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  showLabel?: boolean;
}

export function Progress({
  value,
  max = 100,
  variant = 'default',
  size = 'md',
  className,
  showLabel = false,
}: ProgressProps) {
  const percentage = Math.min(100, Math.max(0, (value / max) * 100));

  return (
    <div className={cn('w-full', className)}>
      <div
        className={cn('w-full rounded-full bg-gray-700', {
          'h-1': size === 'sm',
          'h-2': size === 'md',
          'h-3': size === 'lg',
        })}
      >
        <div
          className={cn('rounded-full transition-all duration-300', {
            'h-1': size === 'sm',
            'h-2': size === 'md',
            'h-3': size === 'lg',
            'bg-purple-600': variant === 'default',
            'bg-green-600': variant === 'success',
            'bg-yellow-600': variant === 'warning',
            'bg-red-600': variant === 'destructive',
          })}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {showLabel && (
        <div className="mt-1 text-xs text-gray-400 text-right">
          {Math.round(percentage)}%
        </div>
      )}
    </div>
  );
}
