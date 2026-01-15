import { Play, Pause, Square, Settings } from 'lucide-react';
import { Button } from '../ui/Button';
import { useStartLoop, usePauseLoop, useResumeLoop, useStopLoop } from '../../hooks/useLoops';
import { useLoopStore } from '../../store/loopStore';

interface LoopControlsProps {
  cardId: string;
}

export function LoopControls({ cardId }: LoopControlsProps) {
  const loopState = useLoopStore((s) => s.getLoopState(cardId));
  const startLoop = useStartLoop();
  const pauseLoop = usePauseLoop();
  const resumeLoop = useResumeLoop();
  const stopLoop = useStopLoop();

  const isRunning = loopState?.status === 'running';
  const isPaused = loopState?.status === 'paused';
  const isActive = isRunning || isPaused;
  const isLoading =
    startLoop.isPending ||
    pauseLoop.isPending ||
    resumeLoop.isPending ||
    stopLoop.isPending;

  const handleStart = () => {
    startLoop.mutate({ cardId });
  };

  const handlePause = () => {
    pauseLoop.mutate(cardId);
  };

  const handleResume = () => {
    resumeLoop.mutate(cardId);
  };

  const handleStop = () => {
    stopLoop.mutate(cardId);
  };

  return (
    <div className="flex items-center gap-2">
      {!isActive ? (
        <Button
          onClick={handleStart}
          disabled={isLoading}
          variant="primary"
          size="sm"
        >
          <Play className="w-4 h-4 mr-1" />
          Start Loop
        </Button>
      ) : (
        <>
          {isRunning ? (
            <Button
              onClick={handlePause}
              disabled={isLoading}
              variant="secondary"
              size="sm"
            >
              <Pause className="w-4 h-4 mr-1" />
              Pause
            </Button>
          ) : (
            <Button
              onClick={handleResume}
              disabled={isLoading}
              variant="primary"
              size="sm"
            >
              <Play className="w-4 h-4 mr-1" />
              Resume
            </Button>
          )}

          <Button
            onClick={handleStop}
            disabled={isLoading}
            variant="destructive"
            size="sm"
          >
            <Square className="w-4 h-4 mr-1" />
            Stop
          </Button>
        </>
      )}

      <Button variant="ghost" size="icon" className="h-8 w-8">
        <Settings className="w-4 h-4" />
      </Button>
    </div>
  );
}
