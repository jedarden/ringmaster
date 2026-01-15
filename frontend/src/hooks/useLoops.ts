import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useLoopStore } from '../store/loopStore';
import type { LoopConfig } from '../types';
import { useEffect } from 'react';

export function useLoopState(cardId: string | undefined) {
  const setLoopState = useLoopStore((s) => s.setLoopState);

  const query = useQuery({
    queryKey: ['loops', cardId],
    queryFn: () => api.getLoopState(cardId!),
    enabled: !!cardId,
    refetchInterval: (query) => {
      // Refresh every 5 seconds while loop is running
      const data = query.state.data;
      if (data?.status === 'running') {
        return 5000;
      }
      return false;
    },
  });

  // Sync to store
  useEffect(() => {
    if (cardId && query.data !== undefined) {
      setLoopState(cardId, query.data);
    }
  }, [cardId, query.data, setLoopState]);

  return query;
}

export function useAllLoops() {
  const loopStore = useLoopStore();

  const query = useQuery({
    queryKey: ['loops'],
    queryFn: () => api.getAllLoops(),
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  // Sync all loops to store
  useEffect(() => {
    if (query.data) {
      // Clear and re-set all loops
      loopStore.clearAllLoops();
      query.data.forEach((loop) => {
        loopStore.setLoopState(loop.cardId, loop);
      });
    }
  }, [query.data, loopStore]);

  return query;
}

export function useStartLoop() {
  const queryClient = useQueryClient();
  const setLoopState = useLoopStore((s) => s.setLoopState);

  return useMutation({
    mutationFn: ({
      cardId,
      config,
    }: {
      cardId: string;
      config?: Partial<LoopConfig>;
    }) => api.startLoop(cardId, config),
    onSuccess: (loopState, { cardId }) => {
      queryClient.setQueryData(['loops', cardId], loopState);
      queryClient.invalidateQueries({ queryKey: ['loops'] });
      queryClient.invalidateQueries({ queryKey: ['cards', cardId] });
      setLoopState(cardId, loopState);
    },
  });
}

export function usePauseLoop() {
  const queryClient = useQueryClient();
  const setLoopState = useLoopStore((s) => s.setLoopState);

  return useMutation({
    mutationFn: (cardId: string) => api.pauseLoop(cardId),
    onSuccess: (loopState, cardId) => {
      queryClient.setQueryData(['loops', cardId], loopState);
      setLoopState(cardId, loopState);
    },
  });
}

export function useResumeLoop() {
  const queryClient = useQueryClient();
  const setLoopState = useLoopStore((s) => s.setLoopState);

  return useMutation({
    mutationFn: (cardId: string) => api.resumeLoop(cardId),
    onSuccess: (loopState, cardId) => {
      queryClient.setQueryData(['loops', cardId], loopState);
      setLoopState(cardId, loopState);
    },
  });
}

export function useStopLoop() {
  const queryClient = useQueryClient();
  const setLoopState = useLoopStore((s) => s.setLoopState);

  return useMutation({
    mutationFn: (cardId: string) => api.stopLoop(cardId),
    onSuccess: (_, cardId) => {
      queryClient.setQueryData(['loops', cardId], null);
      queryClient.invalidateQueries({ queryKey: ['loops'] });
      queryClient.invalidateQueries({ queryKey: ['cards', cardId] });
      setLoopState(cardId, null);
    },
  });
}
