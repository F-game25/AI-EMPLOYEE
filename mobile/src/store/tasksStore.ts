import { create } from 'zustand'
import { api } from '../api/secureClient'

export interface Task {
  id:        string
  title:     string
  status:    string
  agent:     string
  progress:  number
  result?:   string
  error?:    string
  created_at?: number
  elapsed_ms?: number
}

interface TasksState {
  tasks:     Task[]
  isLoading: boolean
  error:     string | null

  fetchTasks:       () => Promise<void>
  submitTask:       (input: string) => Promise<void>
  updateTaskFromWs: (task: Partial<Task> & { id: string }) => void
}

export const useTasksStore = create<TasksState>((set, get) => ({
  tasks:     [],
  isLoading: false,
  error:     null,

  fetchTasks: async () => {
    set({ isLoading: true, error: null })
    try {
      const res = await api.getActiveTasks()
      set({ tasks: (res.tasks as Task[]) || [], isLoading: false })
    } catch (e: unknown) {
      set({ isLoading: false, error: (e as { message?: string }).message || 'Failed to load tasks' })
    }
  },

  submitTask: async (input: string) => {
    set({ error: null })
    try {
      await api.post('/api/tasks/run', { input })
      // Refresh list after short delay so the new task appears
      setTimeout(() => get().fetchTasks(), 800)
    } catch (e: unknown) {
      set({ error: (e as { message?: string }).message || 'Failed to submit task' })
      throw e
    }
  },

  updateTaskFromWs: (incoming) => {
    set(s => {
      const exists = s.tasks.some(t => t.id === incoming.id)
      if (exists) {
        return { tasks: s.tasks.map(t => t.id === incoming.id ? { ...t, ...incoming } : t) }
      }
      // New task arrived via WS — prepend it
      return { tasks: [incoming as Task, ...s.tasks] }
    })
  },
}))
