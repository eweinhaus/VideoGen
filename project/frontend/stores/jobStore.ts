import { create } from "zustand"
import { getJob } from "@/lib/api"
import type { Job } from "@/types/job"
import type { JobResponse } from "@/types/api"

interface JobState {
  currentJob: Job | null
  jobs: Job[]
  isLoading: boolean
  error: string | null
  setCurrentJob: (job: Job | null) => void
  updateJob: (jobId: string, updates: Partial<Job>) => void
  fetchJob: (jobId: string) => Promise<void>
  fetchJobs: () => Promise<void>
  clearCurrentJob: () => void
}

function jobResponseToJob(response: JobResponse): Job {
  return {
    id: response.id,
    status: response.status,
    currentStage: response.current_stage,
    progress: response.progress,
    videoUrl: response.video_url,
    errorMessage: response.error_message,
    createdAt: response.created_at,
    updatedAt: response.updated_at,
    estimatedRemaining: response.estimated_remaining,
    totalCost: response.total_cost,
    stages: response.stages,
  }
}

export const jobStore = create<JobState>((set, get) => ({
  currentJob: null,
  jobs: [],
  isLoading: false,
  error: null,

  setCurrentJob: (job: Job | null) => {
    set({ currentJob: job })
  },

  updateJob: (jobId: string, updates: Partial<Job>) => {
    const { currentJob, jobs } = get()
    if (currentJob?.id === jobId) {
      set({ currentJob: { ...currentJob, ...updates } })
    }
    const updatedJobs = jobs.map((job) =>
      job.id === jobId ? { ...job, ...updates } : job
    )
    set({ jobs: updatedJobs })
  },

  fetchJob: async (jobId: string) => {
    set({ isLoading: true, error: null })
    try {
      const response = await getJob(jobId)
      const job = jobResponseToJob(response)
      set({ currentJob: job, isLoading: false })
    } catch (error: any) {
      set({
        isLoading: false,
        error: error.message || "Failed to fetch job",
      })
      throw error
    }
  },

  fetchJobs: async () => {
    set({ isLoading: true, error: null })
    try {
      // TODO: Implement GET /api/v1/jobs endpoint
      // For now, this is a placeholder
      set({ isLoading: false })
    } catch (error: any) {
      set({
        isLoading: false,
        error: error.message || "Failed to fetch jobs",
      })
      throw error
    }
  },

  clearCurrentJob: () => {
    set({ currentJob: null })
  },
}))

