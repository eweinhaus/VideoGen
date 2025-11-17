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
  // Handle missing or null fields gracefully
  return {
    id: response.id || "",
    status: response.status || "queued",
    currentStage: response.current_stage ?? null,
    progress: response.progress ?? 0,
    videoUrl: response.video_url ?? null,
    errorMessage: response.error_message ?? null,
    createdAt: response.created_at || new Date().toISOString(),
    updatedAt: response.updated_at || new Date().toISOString(),
    estimatedRemaining: response.estimated_remaining ?? undefined,
    totalCost: response.total_cost ?? undefined,
    stages: response.stages ?? {},
    audioData: response.audio_data ?? undefined,
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
      console.log("🔍 Fetching job:", jobId)
      const response = await getJob(jobId)
      console.log("✅ Job response received:", response)
      console.log("🔍 Job stages in response:", response.stages)
      if (response.stages) {
        Object.keys(response.stages).forEach(stageName => {
          const stage = response.stages[stageName]
          console.log(`🔍 Stage ${stageName}:`, {
            status: stage.status,
            hasMetadata: !!stage.metadata,
            metadata: stage.metadata
          })
        })
      }
      
      // Validate response has required fields
      if (!response || !response.id) {
        throw new Error("Invalid job response: missing id field")
      }
      
      const job = jobResponseToJob(response)
      console.log("✅ Job converted:", job)
      console.log("🔍 Job stages after conversion:", job.stages)
      set({ currentJob: job, isLoading: false })
    } catch (error: any) {
      console.error("❌ Failed to fetch job:", error)
      console.error("Error details:", {
        message: error.message,
        statusCode: error.statusCode,
        retryable: error.retryable,
        stack: error.stack
      })
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

