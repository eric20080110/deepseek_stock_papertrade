import { create } from 'zustand'
import type { EvolutionTask, GenerationResult, ViewType, TaskConfig } from '../types/evolution'

interface IndividualProgress {
  generation: number
  current: number
  total: number
}

interface TaskState {
  tasks: EvolutionTask[]
  activeTaskId: string | null
  dbStatusVersion: number
  retryConfig: TaskConfig | null
  selectedAnalysisTaskId: string | null
  currentView: ViewType
  generationHistory: GenerationResult[]
  wsStatus: 'idle' | 'disconnected' | 'connecting' | 'connected' | 'reconnecting'
  apiStatus: 'unknown' | 'ok' | 'error'
  selectedIndividualId: string | null
  selectedStrategy: string | null
  seedParams: Record<string, any> | null
  individualProgress: IndividualProgress | null

  setTasks: (tasks: EvolutionTask[]) => void
  setApiStatus: (status: TaskState['apiStatus']) => void
  addTask: (task: EvolutionTask) => void
  updateTask: (taskId: string, updates: Partial<EvolutionTask>) => void
  setActiveTaskId: (id: string | null) => void
  setSelectedAnalysisTaskId: (id: string | null) => void
  setCurrentView: (view: ViewType) => void
  addGeneration: (gen: GenerationResult) => void
  setWsStatus: (status: TaskState['wsStatus']) => void
  setSelectedIndividualId: (id: string | null) => void
  setSelectedStrategy: (id: string | null) => void
  setSeedParams: (params: Record<string, any> | null) => void
  clearGenerationHistory: () => void
  setIndividualProgress: (progress: IndividualProgress | null) => void
  triggerDbStatusRefresh: () => void
  setRetryConfig: (config: TaskConfig | null) => void
}

export const useTaskStore = create<TaskState>((set) => ({
  tasks: [],
  activeTaskId: null,
  dbStatusVersion: 0,
  retryConfig: null,
  selectedAnalysisTaskId: null,
  currentView: 'queue',
  generationHistory: [],
  wsStatus: 'idle',
  apiStatus: 'unknown',
  selectedIndividualId: null,
  selectedStrategy: null,
  seedParams: null,
  individualProgress: null,

  setTasks: (tasks) => set({ tasks }),
  setApiStatus: (apiStatus) => set({ apiStatus }),
  addTask: (task) => set((s) => ({ tasks: [task, ...s.tasks] })),
  updateTask: (taskId, updates) =>
    set((s) => ({
      tasks: s.tasks.map((t) =>
        t.task_id === taskId ? { ...t, ...updates } : t
      ),
    })),
  setActiveTaskId: (id) => set({ activeTaskId: id }),
  setSelectedAnalysisTaskId: (id) => set({ selectedAnalysisTaskId: id }),
  setCurrentView: (view) => set({ currentView: view }),
  addGeneration: (gen) =>
    set((s) => ({
      generationHistory: [...s.generationHistory, gen],
    })),
  setWsStatus: (status) => set({ wsStatus: status }),
  setSelectedIndividualId: (id) => set({ selectedIndividualId: id }),
  setSelectedStrategy: (id) => set({ selectedStrategy: id }),
  setSeedParams: (params) => set({ seedParams: params }),
  clearGenerationHistory: () => set({ generationHistory: [], individualProgress: null }),
  setIndividualProgress: (progress) => set({ individualProgress: progress }),
  triggerDbStatusRefresh: () => set((s) => ({ dbStatusVersion: s.dbStatusVersion + 1 })),
  setRetryConfig: (config) => set({ retryConfig: config }),
}))
