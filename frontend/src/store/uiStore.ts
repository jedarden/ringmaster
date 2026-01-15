import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

type KanbanView = 'board' | 'list';
type Theme = 'light' | 'dark' | 'system';

interface UIStore {
  // State
  sidebarCollapsed: boolean;
  kanbanView: KanbanView;
  theme: Theme;
  selectedProjectId: string | null;
  showNewCardDialog: boolean;
  showNewProjectDialog: boolean;

  // Actions
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setKanbanView: (view: KanbanView) => void;
  setTheme: (theme: Theme) => void;
  setSelectedProject: (projectId: string | null) => void;
  setShowNewCardDialog: (show: boolean) => void;
  setShowNewProjectDialog: (show: boolean) => void;
}

export const useUIStore = create<UIStore>()(
  devtools(
    persist(
      (set) => ({
        sidebarCollapsed: false,
        kanbanView: 'board',
        theme: 'dark',
        selectedProjectId: null,
        showNewCardDialog: false,
        showNewProjectDialog: false,

        toggleSidebar: () =>
          set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
        setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
        setKanbanView: (kanbanView) => set({ kanbanView }),
        setTheme: (theme) => set({ theme }),
        setSelectedProject: (selectedProjectId) => set({ selectedProjectId }),
        setShowNewCardDialog: (showNewCardDialog) => set({ showNewCardDialog }),
        setShowNewProjectDialog: (showNewProjectDialog) =>
          set({ showNewProjectDialog }),
      }),
      { name: 'ringmaster-ui' }
    ),
    { name: 'ui-store' }
  )
);
