import { cn } from '../../lib/utils';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'secondary' | 'success' | 'warning' | 'destructive' | 'outline';
  size?: 'xs' | 'sm' | 'md';
  className?: string;
}

export function Badge({
  children,
  variant = 'default',
  size = 'sm',
  className,
}: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium',
        {
          // Variants
          'bg-purple-600 text-white': variant === 'default',
          'bg-gray-600 text-gray-100': variant === 'secondary',
          'bg-green-600 text-white': variant === 'success',
          'bg-yellow-600 text-white': variant === 'warning',
          'bg-red-600 text-white': variant === 'destructive',
          'border border-gray-600 text-gray-300': variant === 'outline',
          // Sizes
          'px-1.5 py-0.5 text-xs': size === 'xs',
          'px-2 py-0.5 text-xs': size === 'sm',
          'px-2.5 py-1 text-sm': size === 'md',
        },
        className
      )}
    >
      {children}
    </span>
  );
}
