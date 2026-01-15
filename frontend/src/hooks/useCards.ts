import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useCardStore } from '../store/cardStore';
import type { Card, Trigger, CardState } from '../types';
import { useEffect } from 'react';

export function useCards(projectId?: string | null) {
  const setCards = useCardStore((s) => s.setCards);
  const setLoading = useCardStore((s) => s.setLoading);

  const query = useQuery({
    queryKey: ['cards', { projectId }],
    queryFn: () => api.getCards({ projectId: projectId || undefined }),
    staleTime: 30_000,
  });

  // Sync to store
  useEffect(() => {
    if (query.data) {
      setCards(query.data);
    }
    setLoading(query.isLoading);
  }, [query.data, query.isLoading, setCards, setLoading]);

  return query;
}

export function useCard(cardId: string | undefined) {
  return useQuery({
    queryKey: ['cards', cardId],
    queryFn: () => api.getCard(cardId!),
    enabled: !!cardId,
  });
}

export function useCreateCard() {
  const queryClient = useQueryClient();
  const addCard = useCardStore((s) => s.addCard);

  return useMutation({
    mutationFn: api.createCard.bind(api),
    onSuccess: (newCard: Card) => {
      queryClient.invalidateQueries({ queryKey: ['cards'] });
      queryClient.setQueryData(['cards', newCard.id], newCard);
      addCard(newCard);
    },
  });
}

export function useUpdateCard() {
  const queryClient = useQueryClient();
  const updateCard = useCardStore((s) => s.updateCard);

  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: Partial<Card> }) =>
      api.updateCard(id, updates),
    onSuccess: (updatedCard) => {
      queryClient.invalidateQueries({ queryKey: ['cards'] });
      queryClient.setQueryData(['cards', updatedCard.id], updatedCard);
      updateCard(updatedCard);
    },
  });
}

export function useTransitionCard() {
  const queryClient = useQueryClient();
  const updateCard = useCardStore((s) => s.updateCard);

  return useMutation({
    mutationFn: ({
      cardId,
      trigger,
      data,
    }: {
      cardId: string;
      trigger: Trigger;
      data?: Record<string, unknown>;
    }) => api.transitionCard(cardId, trigger, data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['cards'] });
      queryClient.setQueryData(['cards', result.card.id], result.card);
      updateCard(result.card);
    },
  });
}

// Helper to get transition trigger for drag-and-drop
export function getTransitionTrigger(
  fromState: CardState,
  toState: CardState
): Trigger | null {
  const transitions: Record<string, Trigger> = {
    'draft->planning': 'StartPlanning',
    'planning->coding': 'StartCoding',
    'coding->code_review': 'RequestReview',
    'code_review->testing': 'ReviewApproved',
    'code_review->coding': 'ReviewRejected',
    'testing->build_queue': 'TestsPassed',
    'testing->error_fixing': 'TestsFailed',
    'build_queue->building': 'BuildStarted',
    'building->build_success': 'BuildSucceeded',
    'building->build_failed': 'BuildFailed',
    'build_success->deploy_queue': 'QueueDeploy',
    'deploy_queue->deploying': 'DeployStarted',
    'deploying->verifying': 'DeployCompleted',
    'verifying->completed': 'VerificationPassed',
    'verifying->error_fixing': 'VerificationFailed',
    'error_fixing->coding': 'ErrorFixed',
  };

  const key = `${fromState}->${toState}`;
  return transitions[key] || null;
}
