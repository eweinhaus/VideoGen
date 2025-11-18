import { create } from "zustand"
import { getJob } from "@/lib/api"
import type { Job } from "@/types/job"
import type { JobResponse } from "@/types/api"

// Import getJob function for background fetching

interface JobState {
  currentJob: Job | null
  jobs: Job[]
  isLoading: boolean
  error: string | null
  setCurrentJob: (job: Job | null) => void
  updateJob: (jobId: string, updates: Partial<Job>) => void
  fetchJob: (jobId: string, options?: { timeout?: number; allowPartial?: boolean }) => Promise<void>
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

  fetchJob: async (jobId: string, options?: { timeout?: number; allowPartial?: boolean }) => {
    const { timeout = 15000, allowPartial = true } = options || {}
    
    // If we already have this job in store, use it immediately (don't block rendering)
    const { currentJob } = get()
    if (currentJob?.id === jobId && allowPartial) {
      console.log("✅ Using cached job data:", jobId)
      // Still fetch in background to update, but don't block
      set({ isLoading: false })
    } else {
      set({ isLoading: true, error: null })
    }
    
    try {
      console.log("🔍 Fetching job:", jobId, "timeout:", timeout)
      
      // getJob already has timeout built-in via AbortController, so just call it directly
      // The timeout parameter is passed to the request function which handles it
      const response = await getJob(jobId, timeout)
      
      console.log("✅ Job response received:", response)
      console.log("🔍 Job stages in response:", response.stages)
      if (response.stages) {
        Object.keys(response.stages).forEach(stageName => {
          const stage = response.stages?.[stageName]
          if (stage) {
            console.log(`🔍 Stage ${stageName}:`, {
              status: stage.status,
              hasMetadata: !!stage.metadata,
              metadata: stage.metadata
            })
          }
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
      
      // If we have cached data and this is a timeout/network error, keep using cached data
      const { currentJob: cachedJob } = get()
      const isTimeoutOrConnectionError = error.message?.includes("timeout") || 
                                         error.message?.includes("Connection") ||
                                         error.message?.includes("AbortError")
      
      if (cachedJob?.id === jobId && allowPartial && isTimeoutOrConnectionError) {
        console.log("⚠️ Using cached job data due to fetch error:", error.message)
        set({ isLoading: false, error: null }) // Don't show error, use cached data
        // Continue fetching in background with longer timeout (don't await)
        getJob(jobId, 300000).then((response) => {
          if (response && response.id) {
            const job = jobResponseToJob(response)
            set({ currentJob: job })
            console.log("✅ Background fetch succeeded, updated job data")
          }
        }).catch((bgError) => {
          console.error("❌ Background fetch also failed:", bgError)
        })
        return // Exit early, using cached data
      }
      
      // Even if we don't have cached data, for timeout/connection errors, 
      // create a minimal job object so the page can render while we fetch in background
      // This prevents the page from hanging or showing errors immediately
      if (isTimeoutOrConnectionError && allowPartial) {
        console.log("⚠️ Initial fetch timed out, creating minimal job object and continuing in background:", error.message)
        
        // Create minimal job object so page can render
        const minimalJob: Job = {
          id: jobId,
          status: "processing", // Assume processing until we know otherwise
          currentStage: null,
          progress: 0,
          videoUrl: null,
          errorMessage: null,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          stages: {},
        }
        
        set({ currentJob: minimalJob, isLoading: false, error: null })
        
        // Continue fetching in background with longer timeout
        getJob(jobId, 300000).then((response) => {
          if (response && response.id) {
            const job = jobResponseToJob(response)
            set({ currentJob: job })
            console.log("✅ Background fetch succeeded, updated job data")
          }
        }).catch((bgError) => {
          console.error("❌ Background fetch also failed:", bgError)
          // Only show error if background fetch also fails
          set({ error: bgError.message || "Failed to fetch job" })
        })
        return // Exit early, allow page to render with minimal job
      }
      
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

