import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { Project } from '../types';

interface CreateProjectInput {
  name: string;
  repositoryUrl: string;
  repositoryPath?: string;
  description?: string;
  techStack?: string[];
  codingConventions?: string;
}

export function useProjects() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.getProjects(),
    staleTime: 60_000,
  });

  const createMutation = useMutation({
    mutationFn: (input: CreateProjectInput) => api.createProject(input),
    onSuccess: (newProject: Project) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      queryClient.setQueryData(['projects', newProject.id], newProject);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (projectId: string) => api.deleteProject(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
  });

  return {
    projects: query.data || [],
    isLoading: query.isLoading,
    error: query.error,
    createProject: createMutation.mutateAsync,
    deleteProject: deleteMutation.mutateAsync,
    isCreating: createMutation.isPending,
    isDeleting: deleteMutation.isPending,
  };
}

export function useProject(projectId: string | undefined) {
  return useQuery({
    queryKey: ['projects', projectId],
    queryFn: () => api.getProject(projectId!),
    enabled: !!projectId,
  });
}
