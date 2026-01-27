/**
 * Test API helper functions for setting up and tearing down test data
 * These helpers interact directly with the Ringmaster backend API
 */

const API_BASE_URL = 'http://localhost:8000/api';

interface TestProject {
  id: string;
  name: string;
  description: string;
  repo_url?: string;
  tech_stack?: string[];
  working_dir?: string;
  settings?: Record<string, unknown>;
}

interface TestTask {
  id: string;
  title: string;
  description?: string;
  status: string;
  priority: string;
  type: string;
  project_id: string;
}

interface TestWorker {
  id: string;
  name: string;
  type: string;
  command: string;
  status: string;
  capabilities?: string[];
}

/**
 * Create a test project via API
 */
export async function createTestProject(overrides: Partial<TestProject> = {}): Promise<TestProject> {
  const response = await fetch(`${API_BASE_URL}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: overrides.name || `E2E Test Project ${Date.now()}`,
      description: overrides.description || 'A test project for E2E validation',
      repo_url: overrides.repo_url || '',
      tech_stack: overrides.tech_stack || ['python', 'react'],
      working_dir: overrides.working_dir,
      settings: overrides.settings,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to create test project: ${response.statusText}`);
  }

  return (await response.json()) as TestProject;
}

/**
 * Create a test task via API
 */
export async function createTestTask(projectId: string, overrides: Partial<TestTask> = {}): Promise<TestTask> {
  const response = await fetch(`${API_BASE_URL}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: overrides.title || `Test Task ${Date.now()}`,
      description: overrides.description || 'A test task for E2E validation',
      status: overrides.status || 'draft',
      priority: overrides.priority || 'P2',
      type: overrides.type || 'task',
      project_id: projectId,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to create test task: ${response.statusText} - ${errorText}`);
  }

  return (await response.json()) as TestTask;
}

/**
 * Create a test worker via API
 */
export async function createTestWorker(overrides: Partial<TestWorker> = {}): Promise<TestWorker> {
  const response = await fetch(`${API_BASE_URL}/workers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: overrides.name || `e2e-test-worker-${Date.now()}`,
      type: overrides.type || 'generic',
      command: overrides.command || 'echo',
      status: overrides.status || 'idle',
      capabilities: overrides.capabilities || ['python', 'typescript'],
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to create test worker: ${response.statusText} - ${errorText}`);
  }

  return (await response.json()) as TestWorker;
}

/**
 * Delete a test project via API
 */
export async function deleteTestProject(projectId: string): Promise<void> {
  await fetch(`${API_BASE_URL}/projects/${projectId}`, {
    method: 'DELETE',
  });
}

/**
 * Delete a test task via API
 */
export async function deleteTestTask(taskId: string): Promise<void> {
  await fetch(`${API_BASE_URL}/tasks/${taskId}`, {
    method: 'DELETE',
  });
}

/**
 * Delete a test worker via API
 */
export async function deleteTestWorker(workerId: string): Promise<void> {
  await fetch(`${API_BASE_URL}/workers/${workerId}`, {
    method: 'DELETE',
  });
}

/**
 * Delete all test projects (those with 'E2E' in the name)
 */
export async function cleanupTestProjects(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/projects`);
  if (!response.ok) return;

  const projects = (await response.json()) as TestProject[];
  const testProjects = projects.filter((p) => p.name.includes('E2E') || p.name.includes('e2e'));

  await Promise.all(
    testProjects.map((p) =>
      fetch(`${API_BASE_URL}/projects/${p.id}`, { method: 'DELETE' })
    )
  );
}

/**
 * Delete all test workers (those with 'e2e' in the name)
 */
export async function cleanupTestWorkers(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/workers`);
  if (!response.ok) return;

  const workers = (await response.json()) as TestWorker[];
  const testWorkers = workers.filter((w) => w.name.includes('e2e') || w.name.includes('E2E'));

  await Promise.all(
    testWorkers.map((w) =>
      fetch(`${API_BASE_URL}/workers/${w.id}`, { method: 'DELETE' })
    )
  );
}

/**
 * Setup test data - creates a project with tasks and workers
 */
export async function setupTestData(): Promise<{
  project: TestProject;
  tasks: TestTask[];
  workers: TestWorker[];
}> {
  const project = await createTestProject();

  // Create some tasks in different states
  const tasks = await Promise.all([
    createTestTask(project.id, { title: 'Draft Task', status: 'draft', priority: 'P2' }),
    createTestTask(project.id, { title: 'Ready Task', status: 'ready', priority: 'P1' }),
    createTestTask(project.id, { title: 'In Progress Task', status: 'in_progress', priority: 'P0' }),
  ]);

  // Create some test workers
  const workers = await Promise.all([
    createTestWorker({ name: 'e2e-worker-idle', status: 'idle' }),
    createTestWorker({ name: 'e2e-worker-busy', status: 'busy' }),
  ]);

  return { project, tasks, workers };
}

/**
 * Teardown test data - cleans up all E2E test data
 */
export async function teardownTestData(): Promise<void> {
  await Promise.all([
    cleanupTestProjects(),
    cleanupTestWorkers(),
  ]);
}

/**
 * Wait for backend API to be healthy
 */
export async function waitForBackend(timeout = 30000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      const response = await fetch(`${API_BASE_URL.replace('/api', '')}/health`);
      if (response.ok) {
        return;
      }
    } catch {
      // Backend not ready yet
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Backend health check timed out after ${timeout}ms`);
}
