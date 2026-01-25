import type {
  Card,
  Project,
  LoopState,
  LoopConfig,
  Attempt,
  CardError,
  ApiResponse,
  Trigger,
  ActiveLoopsResponse,
} from '../types';

const BASE_URL = import.meta.env.VITE_API_URL || '/api';

class ApiError extends Error {
  code: string;
  details?: unknown;

  constructor(error: { code: string; message: string; details?: unknown }) {
    super(error.message);
    this.code = error.code;
    this.details = error.details;
    this.name = 'ApiError';
  }
}

class ApiClient {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const response = await fetch(`${BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        error: { code: 'UNKNOWN', message: 'Request failed' },
      }));
      throw new ApiError(errorData.error);
    }

    // Handle 204 No Content (used by DELETE operations)
    if (response.status === 204) {
      return undefined as T;
    }

    // Parse JSON response
    const result: ApiResponse<T> = await response.json();
    return result.data;
  }

  // Cards
  async getCards(params?: {
    projectId?: string;
    state?: string;
    limit?: number;
    offset?: number;
  }): Promise<Card[]> {
    const searchParams = new URLSearchParams();
    if (params?.projectId) searchParams.set('project_id', params.projectId);
    if (params?.state) searchParams.set('state', params.state);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    const query = searchParams.toString();
    return this.request<Card[]>(`/cards${query ? `?${query}` : ''}`);
  }

  async getCard(id: string): Promise<Card> {
    return this.request<Card>(`/cards/${id}`);
  }

  async createCard(card: {
    projectId: string;
    title: string;
    description?: string;
    taskPrompt: string;
    labels?: string[];
    priority?: number;
  }): Promise<Card> {
    return this.request<Card>('/cards', {
      method: 'POST',
      body: JSON.stringify(card),
    });
  }

  async updateCard(
    id: string,
    updates: Partial<{
      title: string;
      description: string;
      taskPrompt: string;
      labels: string[];
      priority: number;
    }>
  ): Promise<Card> {
    return this.request<Card>(`/cards/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    });
  }

  async transitionCard(
    id: string,
    trigger: Trigger,
    data?: Record<string, unknown>
  ): Promise<{ card: Card; actions: string[] }> {
    return this.request<{ card: Card; actions: string[] }>(
      `/cards/${id}/transition`,
      {
        method: 'POST',
        body: JSON.stringify({ trigger, data }),
      }
    );
  }

  // Projects
  async getProjects(): Promise<Project[]> {
    return this.request<Project[]>('/projects');
  }

  async getProject(id: string): Promise<Project> {
    return this.request<Project>(`/projects/${id}`);
  }

  async createProject(project: {
    name: string;
    repositoryUrl: string;
    repositoryPath?: string;
    description?: string;
    techStack?: string[];
    codingConventions?: string;
    defaultBranch?: string;
  }): Promise<Project> {
    return this.request<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(project),
    });
  }

  async deleteProject(id: string): Promise<void> {
    return this.request<void>(`/projects/${id}`, {
      method: 'DELETE',
    });
  }

  // Loops
  async getLoopState(cardId: string): Promise<LoopState | null> {
    try {
      return await this.request<LoopState>(`/cards/${cardId}/loop`);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'NOT_FOUND') {
        return null;
      }
      throw e;
    }
  }

  async startLoop(
    cardId: string,
    config?: Partial<LoopConfig>
  ): Promise<LoopState> {
    // Backend returns { loopId, cardId, state } but we need just the state
    const response = await this.request<{ loopId: string; cardId: string; state: LoopState }>(
      `/cards/${cardId}/loop/start`,
      {
        method: 'POST',
        body: JSON.stringify({ config }),
      }
    );
    return response.state;
  }

  async pauseLoop(cardId: string): Promise<LoopState> {
    return this.request<LoopState>(`/cards/${cardId}/loop/pause`, {
      method: 'POST',
    });
  }

  async resumeLoop(cardId: string): Promise<LoopState> {
    return this.request<LoopState>(`/cards/${cardId}/loop/resume`, {
      method: 'POST',
    });
  }

  async stopLoop(cardId: string): Promise<LoopState> {
    return this.request<LoopState>(`/cards/${cardId}/loop/stop`, {
      method: 'POST',
    });
  }

  async getAllLoops(): Promise<ActiveLoopsResponse> {
    return this.request<ActiveLoopsResponse>('/loops');
  }

  // Attempts
  async getAttempts(cardId: string): Promise<Attempt[]> {
    return this.request<Attempt[]>(`/cards/${cardId}/attempts`);
  }

  // Errors
  async getErrors(cardId: string): Promise<CardError[]> {
    return this.request<CardError[]>(`/cards/${cardId}/errors`);
  }

  async resolveError(cardId: string, errorId: string): Promise<void> {
    return this.request<void>(`/cards/${cardId}/errors/${errorId}/resolve`, {
      method: 'POST',
    });
  }
}

export const api = new ApiClient();
export { ApiError };
